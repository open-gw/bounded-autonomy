"""Cluster driver: live probe, live verify via Tempo, in-process rollback artefacts."""

from __future__ import annotations

import base64
import json
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from controller.cnp import render_cnp
from harness.simulator import INVENTORY, _spiffe, _task_id, run_local
from observer.tempo import fetch_spans
from plan import build_step_plan
from agent.orchestrator import pick_from_injection, pick_tool
from harness.payloads import load_payload
from weights import reachable_weight

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / ".tools"
CTX = "k3d-bounded-autonomy"
NS = "rig"
DECLARED = ["records", "search", "notify"]
FLAT_TTL_SECONDS = 86400
SERVICE_PORTS = {
    "records": 8081,
    "docs": 8082,
    "search": 8083,
    "notify": 8084,
    "billing": 8085,
    "analytics": 8086,
    "audit": 8087,
    "catalog": 8088,
}


def _kubectl(*args: str, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    bin_path = TOOLS / "kubectl"
    cmd = [str(bin_path), "--context", CTX, *args]
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def _apply_yaml(doc: str) -> None:
    proc = _kubectl("apply", "-f", "-", input_text=doc, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"kubectl apply failed:\n{proc.stderr}\n{proc.stdout}\n---\n{doc}")


def _jwt_claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    pad = "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload + pad))


def _ensure_agent(task_id: str, mode: str) -> str:
    _kubectl("-n", NS, "delete", "pod", "agent", "--ignore-not-found", "--wait=true", check=False)
    spec: dict[str, Any] = {
        "restartPolicy": "Always",
        "containers": [
            {
                "name": "agent",
                "image": "ba-runtime:paper1",
                "imagePullPolicy": "IfNotPresent",
                "command": ["sleep", "infinity"],
                "env": [
                    {
                        "name": "OTEL_EXPORTER_OTLP_ENDPOINT",
                        "value": "http://otel-collector:4318",
                    },
                    {
                        "name": "PYTHONPATH",
                        "value": "/app:/app/rig:/app/analysis",
                    },
                ],
            }
        ],
    }
    if mode == "flat":
        spec["serviceAccountName"] = "agent"
        spec["automountServiceAccountToken"] = False
        spec["volumes"] = [
            {
                "name": "sa-token",
                "projected": {
                    "sources": [
                        {
                            "serviceAccountToken": {
                                "path": "token",
                                "expirationSeconds": FLAT_TTL_SECONDS,
                                "audience": "rig",
                            }
                        }
                    ]
                },
            }
        ]
        spec["containers"][0]["volumeMounts"] = [
            {
                "name": "sa-token",
                "mountPath": "/var/run/secrets/rig",
                "readOnly": True,
            }
        ]
    doc = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "agent",
            "namespace": NS,
            "labels": {
                "app.kubernetes.io/name": "agent",
                "bounded-autonomy.io/task-id": task_id,
            },
        },
        "spec": spec,
    }
    _apply_yaml(yaml.safe_dump(doc))
    _kubectl("-n", NS, "wait", "--for=condition=Ready", "pod/agent", "--timeout=120s")
    _kubectl(
        "-n", NS, "label", "pod", "agent",
        f"bounded-autonomy.io/task-id={task_id}", "--overwrite", check=False,
    )
    return "agent"


def _wait_cnp(task_id: str, timeout: float = 60.0) -> float:
    t0 = time.time()
    deadline = t0 + timeout
    while time.time() < deadline:
        listing = _kubectl("-n", NS, "get", "cnp", "-o", "json", check=False)
        try:
            items = json.loads(listing.stdout or "{}").get("items") or []
        except json.JSONDecodeError:
            items = []
        ready = False
        for item in items:
            labels = (item.get("metadata") or {}).get("labels") or {}
            if labels.get("bounded-autonomy.io/task-id") != task_id:
                continue
            if labels.get("bounded-autonomy.io/role") != "egress":
                continue
            conds = (item.get("status") or {}).get("conditions") or []
            ready = any(c.get("type") == "Valid" and str(c.get("status")) == "True" for c in conds)
        if ready:
            return (time.time() - t0) * 1000.0
        time.sleep(0.2)
    raise RuntimeError(f"CNP for {task_id} did not become Valid")


def _apply_declaration(task_id: str, services: list[str], granularity: str) -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    svc_yaml = "\n".join(f"    - name: {name}" for name in services)
    _apply_yaml(
        f"""
apiVersion: bounded-autonomy.io/v1
kind: TaskDeclaration
metadata:
  name: {task_id}
  namespace: {NS}
spec:
  taskId: {task_id}
  expectedDurationSeconds: 1800
  createdAt: "{created}"
  granularity: {granularity}
  services:
{svc_yaml}
"""
    )
    spec = {
        "taskId": task_id,
        "expectedDurationSeconds": 1800,
        "services": [{"name": name} for name in services],
        "namespace": NS,
    }
    rendered = render_cnp(task_id, NS, spec)
    docs = [rendered["egress"], *rendered["ingress"]]
    _apply_yaml("---\n".join(yaml.safe_dump(doc) for doc in docs))
    return created


def _set_mode_policy(mode: str, task_id: str, services: list[str], granularity: str) -> float:
    _kubectl("-n", NS, "delete", "cnp", "--all", "--ignore-not-found", check=False)
    _kubectl("-n", NS, "delete", "td", "--all", "--ignore-not-found", check=False)
    if mode == "flat":
        time.sleep(2)
        return 0.0
    _apply_declaration(task_id, services, granularity)
    return _wait_cnp(task_id)


def _cluster_ip(service: str) -> str:
    proc = _kubectl("-n", NS, "get", "svc", service, "-o", "jsonpath={.spec.clusterIP}")
    ip = (proc.stdout or "").strip()
    if not ip:
        raise RuntimeError(f"no ClusterIP for {service}: {proc.stderr}")
    return ip


def _probe_service(pod: str, service: str) -> bool:
    port = SERVICE_PORTS[service]
    ip = _cluster_ip(service)
    code = (
        "import socket,sys; "
        f"s=socket.socket(); s.settimeout(3); "
        f"ok=s.connect_ex(('{ip}',{port}))==0; "
        "s.close(); sys.exit(0 if ok else 1)"
    )
    for _ in range(3):
        proc = _kubectl("-n", NS, "exec", pod, "--", "python", "-c", code, check=False)
        if proc.returncode == 0:
            return True
        time.sleep(1)
    return False


def cluster_probe(mode: str, seed: int, pod: str, task_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    spiffe = _spiffe(task_id)
    probe_rows: list[dict[str, Any]] = []
    flow_rows: list[dict[str, Any]] = []
    for svc in INVENTORY:
        ok = _probe_service(pod, svc)
        probe_rows.append({"step": 0, "service": svc, "success": ok})
        if ok:
            flow_rows.append(
                {
                    "source_spiffe": spiffe,
                    "destination_service": svc,
                    "verdict": "FORWARDED",
                }
            )
    return probe_rows, flow_rows


def _exec_worker(args: list[str]) -> dict[str, Any]:
    proc = _kubectl(
        "-n", NS, "exec", "agent", "--",
        "python", "-m", "harness.live_worker", *args,
        check=False,
    )
    text = (proc.stdout or "").strip().splitlines()
    if not text:
        raise RuntimeError(f"live_worker empty: {proc.stderr}")
    return json.loads(text[-1])


def _flat_token_epochs(pod: str) -> tuple[float, float]:
    proc = _kubectl(
        "-n", NS, "exec", pod, "--", "cat", "/var/run/secrets/rig/token", check=False
    )
    token = (proc.stdout or "").strip()
    if not token:
        now = time.time()
        return now, now + FLAT_TTL_SECONDS
    claims = _jwt_claims(token)
    return float(claims.get("iat") or time.time()), float(claims.get("exp") or (time.time() + FLAT_TTL_SECONDS))


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _wait_tcp(host: str, port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        sock = socket.socket()
        sock.settimeout(0.4)
        try:
            if sock.connect_ex((host, port)) == 0:
                return
        finally:
            sock.close()
        time.sleep(0.1)
    raise RuntimeError(f"port-forward {host}:{port} did not become ready")


def _tempo_from_controller(
    task_id: str,
    *,
    start: float | None = None,
    end: float | None = None,
) -> pd.DataFrame:
    """Pull spans from Tempo on the host via kubectl port-forward.

    The query client is the tree that produced the run (not the in-cluster
    image), so start/end and OTLP parsing stay in lockstep with this commit.
    Pass this run's time window so a retry cannot ingest leftover traces
    that reused the same ``task_id``.
    """
    port = _free_port()
    proc = subprocess.Popen(
        [
            str(TOOLS / "kubectl"),
            "--context",
            CTX,
            "-n",
            NS,
            "port-forward",
            "svc/tempo",
            f"{port}:3200",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_tcp("127.0.0.1", port)
        kwargs: dict[str, Any] = {}
        if start is not None:
            kwargs["start"] = int(start)
        if end is not None:
            kwargs["end"] = int(end)
        return fetch_spans(task_id=task_id, tempo=f"http://127.0.0.1:{port}", **kwargs)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _delete_segment(task_id: str) -> float:
    t0 = time.time()
    _kubectl("-n", NS, "delete", "td", task_id, "--ignore-not-found", check=False)
    _kubectl("-n", NS, "delete", "cnp", "-l", f"bounded-autonomy.io/task-id={task_id}", check=False)
    deadline = t0 + 30
    while time.time() < deadline:
        listing = _kubectl("-n", NS, "get", "cnp", "-l", f"bounded-autonomy.io/task-id={task_id}", "-o", "name", check=False)
        if not (listing.stdout or "").strip():
            return (time.time() - t0) * 1000.0
        time.sleep(0.2)
    return (time.time() - t0) * 1000.0


def run_cluster(
    *,
    mode: str,
    seed: int,
    out_dir: Path,
    baseline_spans: pd.DataFrame | None = None,
    granularity: str = "task",
) -> dict[str, Any]:
    task_id = _task_id(seed, mode) if granularity == "task" else f"long-multistep-{mode}-step-seed{seed}"
    spiffe = _spiffe(task_id)
    result = run_local(
        mode=mode,
        seed=seed,
        out_dir=out_dir,
        injection=True,
        baseline_spans=baseline_spans,
        granularity=granularity,
        task_id=task_id,
    )
    pod = _ensure_agent(task_id, mode)
    step_d: list[float] = []
    step_ratios: list[float] = []
    task_start = time.time()
    p_ms = _set_mode_policy(mode, task_id, list(DECLARED), granularity)
    if granularity == "step" and mode == "full":
        plan = build_step_plan(seed)
        payload = load_payload("v1", seed)
        last = None
        for step in plan:
            tool = pick_tool(step.instruction, list(DECLARED), last)
            if step.index == 15:
                tool = pick_from_injection(payload, list(DECLARED))
            d_ms = 0.0
            issued = time.time()
            if tool in DECLARED:
                _apply_declaration(task_id, [tool], "step")
                d_ms = _wait_cnp(task_id)
            ready = time.time()
            step_d.append(d_ms)
            _exec_worker([
                "--mode", mode, "--seed", str(seed),
                "--task-id", task_id, "--spiffe-id", spiffe,
                "--only-step", str(step.index), "--no-root",
            ])
            ended = time.time()
            tau_step = max(ended - issued, 1e-6)
            t_step = max(ended - ready, 1e-6)
            step_ratios.append(tau_step / t_step)
            last = {"forced_tool": tool}
        worker = {"start_epoch": task_start, "end_epoch": time.time()}
    else:
        worker = _exec_worker([
            "--mode", mode, "--seed", str(seed),
            "--task-id", task_id, "--spiffe-id", spiffe,
        ])
    task_end = time.time()
    probe_rows, flow_rows = cluster_probe(mode, seed, pod, task_id)
    if mode == "full" and granularity == "step":
        _apply_declaration(task_id, list(DECLARED), "task")
        _wait_cnp(task_id)
        probe_rows, flow_rows = cluster_probe(mode, seed, pod, task_id)
    q_ms = _delete_segment(task_id) if mode == "full" else 0.0
    pd.DataFrame(probe_rows).to_parquet(out_dir / "probe.parquet", index=False)
    pd.DataFrame(flow_rows).to_parquet(out_dir / "flows.parquet", index=False)

    if mode == "flat":
        issued_epoch, not_after_epoch = _flat_token_epochs(pod)
        cred_kind = "sa-token"
    else:
        issued_epoch = float(worker.get("start_epoch") or task_start)
        not_after_epoch = float(task_end)
        cred_kind = "svid"
    t_start = float(worker.get("start_epoch") or task_start)
    t_end = float(worker.get("end_epoch") or task_end)
    pd.DataFrame(
        [
            {
                "task_id": task_id,
                "spiffe_id": spiffe if mode == "full" else "system:serviceaccount:rig:agent",
                "issued_at": datetime.fromtimestamp(issued_epoch, timezone.utc).isoformat(),
                "not_after": datetime.fromtimestamp(not_after_epoch, timezone.utc).isoformat(),
                "issued_at_epoch": issued_epoch,
                "not_after_epoch": not_after_epoch,
                "credential_kind": cred_kind,
                "spire_entry": mode == "full",
            }
        ]
    ).to_parquet(out_dir / "svid.parquet", index=False)

    time.sleep(3)
    spans = _tempo_from_controller(
        task_id,
        start=task_start - 5,
        end=time.time() + 30,
    )
    n_verify = (
        int((spans["name"] == "verify").sum())
        if not spans.empty and "name" in spans.columns
        else 0
    )
    if n_verify < 2:
        raise RuntimeError(f"Tempo returned {n_verify} verify spans for {task_id}")
    run_rows = [
        {
            "name": "run",
            "duration_ms": (t_end - t_start) * 1000.0,
            "mode": mode,
            "task_id": task_id,
            "start_epoch": t_start,
            "end_epoch": t_end,
            "export": "tempo",
        }
    ]
    if "run" not in set(spans["name"].astype(str)):
        spans = pd.concat([spans, pd.DataFrame(run_rows)], ignore_index=True)
    spans.to_parquet(out_dir / "spans.parquet", index=False)

    from analysis.compute_result import compute_result as _compute

    meta = json.loads((out_dir / "result.json").read_text())
    reached = sorted({r["service"] for r in probe_rows if r["success"]})
    result = _compute(
        out_dir,
        {
            "run_id": task_id,
            "profile": meta["profile"],
            "mode": mode,
            "seed": seed,
            "started_at": datetime.fromtimestamp(t_start, timezone.utc).isoformat().replace("+00:00", "Z"),
            "finished_at": datetime.fromtimestamp(t_end, timezone.utc).isoformat().replace("+00:00", "Z"),
            "wall_clock_seconds": t_end - t_start,
            "declaration": {
                **meta["declaration"],
                "task_id": task_id,
                "spiffe_id": spiffe,
                "granularity": granularity,
            },
            "steps_completed": meta["steps_completed"],
            "write_counts": meta["write_counts"],
            "policy_propagation_ms": step_d if step_d else ([p_ms] if p_ms else []),
            "source": "cluster",
            "segment_p_ms": p_ms,
            "segment_q_ms": q_ms,
            "step_ratios": step_ratios,
            "reachable_weight": reachable_weight(reached),
        },
        baseline_spans=baseline_spans,
    )
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
