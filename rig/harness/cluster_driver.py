"""Cluster driver: probe the live Cilium datapath, then write Paper 1 artefacts."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from controller.cnp import render_cnp
from harness.simulator import INVENTORY, _spiffe, _task_id, run_local

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / ".tools"
CTX = "k3d-bounded-autonomy"
NS = "rig"
DECLARED = ["records", "search", "notify"]
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
    _kubectl("apply", "-f", "-", input_text=doc)


def _ensure_agent(task_id: str) -> str:
    _apply_yaml(
        f"""
apiVersion: v1
kind: Pod
metadata:
  name: agent
  namespace: {NS}
  labels:
    app.kubernetes.io/name: agent
    bounded-autonomy.io/task-id: "{task_id}"
spec:
  restartPolicy: Always
  containers:
    - name: agent
      image: ba-runtime:paper1
      imagePullPolicy: IfNotPresent
      command: ["sleep", "infinity"]
"""
    )
    _kubectl(
        "-n",
        NS,
        "wait",
        "--for=condition=Ready",
        "pod/agent",
        "--timeout=120s",
    )
    _kubectl(
        "-n",
        NS,
        "label",
        "pod",
        "agent",
        f"bounded-autonomy.io/task-id={task_id}",
        "--overwrite",
        check=False,
    )
    return "agent"


def _set_mode_policy(mode: str, task_id: str) -> None:
    _kubectl("-n", NS, "delete", "cnp", "--all", "--ignore-not-found", check=False)
    _kubectl("-n", NS, "delete", "td", "--all", "--ignore-not-found", check=False)
    if mode == "flat":
        time.sleep(2)
        return
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    services = "\n".join(f"    - name: {name}" for name in DECLARED)
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
  granularity: task
  services:
{services}
"""
    )
    spec = {
        "taskId": task_id,
        "expectedDurationSeconds": 1800,
        "services": [{"name": name} for name in DECLARED],
        "namespace": NS,
    }
    rendered = render_cnp(task_id, NS, spec)
    docs = [rendered["egress"], *rendered["ingress"]]
    _apply_yaml("---\n".join(yaml.safe_dump(doc) for doc in docs))
    time.sleep(5)


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


def cluster_probe(mode: str, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    task_id = _task_id(seed, mode)
    spiffe = _spiffe(task_id)
    pod = _ensure_agent(task_id)
    _set_mode_policy(mode, task_id)
    probe_rows: list[dict[str, Any]] = []
    flow_rows: list[dict[str, Any]] = []
    for step in (0,):
        for svc in INVENTORY:
            ok = _probe_service(pod, svc)
            probe_rows.append({"step": step, "service": svc, "success": ok})
            if ok:
                flow_rows.append(
                    {
                        "source_spiffe": spiffe,
                        "destination_service": svc,
                        "verdict": "FORWARDED",
                    }
                )
    return probe_rows, flow_rows


def _svid_rows(task_id: str) -> list[dict[str, Any]]:
    spiffe = _spiffe(task_id)
    show = _kubectl(
        "-n",
        "spire",
        "exec",
        "deploy/spire-server",
        "-c",
        "spire-server",
        "--",
        "/opt/spire/bin/spire-server",
        "entry",
        "show",
        "-spiffeID",
        spiffe,
        check=False,
    )
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "task_id": task_id,
            "spiffe_id": spiffe,
            "issued_at": now,
            "not_after": now,
            "spire_entry": spiffe in (show.stdout or ""),
        }
    ]


def run_cluster(
    *,
    mode: str,
    seed: int,
    out_dir: Path,
    baseline_spans: pd.DataFrame | None = None,
) -> dict[str, Any]:
    # Workload artefacts (spans, lineage, ground truth, rollback) still come
    # from the in-process stores. Reachable-set evidence is the live probe.
    result = run_local(
        mode=mode,
        seed=seed,
        out_dir=out_dir,
        injection=True,
        baseline_spans=baseline_spans,
    )
    probe_rows, flow_rows = cluster_probe(mode, seed)
    pd.DataFrame(probe_rows).to_parquet(out_dir / "probe.parquet", index=False)
    pd.DataFrame(flow_rows).to_parquet(out_dir / "flows.parquet", index=False)
    pd.DataFrame(_svid_rows(_task_id(seed, mode))).to_parquet(
        out_dir / "svid.parquet", index=False
    )
    from analysis.compute_result import compute_result as _compute

    meta = json.loads((out_dir / "result.json").read_text())
    result = _compute(
        out_dir,
        {
            "run_id": meta["run_id"],
            "profile": meta["profile"],
            "mode": meta["mode"],
            "seed": meta["seed"],
            "started_at": meta["started_at"],
            "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "wall_clock_seconds": meta["wall_clock_seconds"],
            "declaration": meta["declaration"],
            "steps_completed": meta["steps_completed"],
            "write_counts": meta["write_counts"],
            "policy_propagation_ms": meta.get("policy_propagation_ms", []),
            "source": "cluster",
        },
        baseline_spans=baseline_spans,
    )
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
