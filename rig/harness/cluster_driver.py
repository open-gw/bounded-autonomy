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

from controller.cnp import render_cnp, render_pod_spire_entry, render_spire_entry
from controller.gateway import apply_gateway_routes
from harness.simulator import INVENTORY, _spiffe, _task_id, run_local
from identity.svid import (
    DEFAULT_STEP_JWT_TTL_SECONDS,
    DEFAULT_TASK_JWT_TTL_SECONDS,
    JWT_AUDIENCE,
    decode_jwt_claims,
    extract_jwt_token,
    parse_entry_ids,
    tau_from_claims,
)
from observer.evasion import run_evasion, write_evasion
from observer.tempo import fetch_spans
from plan import DEFAULT_DECLARED, build_step_plan
from agent.orchestrator import pick_from_injection, pick_tool
from harness.payloads import load_payload
from profiles import profile_spec
from sweep import INJECTION_SERVICE, declared_services
from modes import (
    GATEWAY_NS,
    deploys_gateway_policy,
    run_id_for,
    uses_flat_credential,
    uses_segment,
)
from weights import reachable_weight

SPIRE_NS = "spire"
SPIRE_PARENT = "spiffe://rig/spire/agent/k8s_psat/bounded-autonomy/k3d-bounded-autonomy-server-0"
SPIRE_SOCKET = "/run/spire/sockets/server.sock"

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / ".tools"
CTX = "k3d-bounded-autonomy"
NS = "rig"
DECLARED = list(DEFAULT_DECLARED)
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


def _ensure_agent(task_id: str, mode: str, pod_name: str = "agent") -> str:
    _kubectl("-n", NS, "delete", "pod", pod_name, "--ignore-not-found", "--wait=true", check=False)
    still = _kubectl("-n", NS, "get", "pod", pod_name, "-o", "name", check=False)
    if (still.stdout or "").strip():
        _kubectl(
            "-n", NS, "delete", "pod", pod_name,
            "--ignore-not-found", "--wait=true",
            "--force", "--grace-period=0",
            check=False,
        )
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
    spec["serviceAccountName"] = "agent"
    if uses_flat_credential(mode):
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
            "name": pod_name,
            "namespace": NS,
            "labels": {
                "app.kubernetes.io/name": "agent",
                "bounded-autonomy.io/task-id": task_id,
            },
        },
        "spec": spec,
    }
    last_err: Exception | None = None
    for _ in range(5):
        try:
            _apply_yaml(yaml.safe_dump(doc))
            last_err = None
            break
        except RuntimeError as exc:
            last_err = exc
            if "AlreadyExists" not in str(exc):
                raise
            time.sleep(1)
            _kubectl(
                "-n", NS, "delete", "pod", pod_name,
                "--ignore-not-found", "--wait=true",
                "--force", "--grace-period=0",
                check=False,
            )
    if last_err is not None:
        raise last_err
    _kubectl("-n", NS, "wait", "--for=condition=Ready", f"pod/{pod_name}", "--timeout=120s")
    _kubectl(
        "-n", NS, "label", "pod", pod_name,
        f"bounded-autonomy.io/task-id={task_id}", "--overwrite", check=False,
    )
    return pod_name


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


def _apply_declaration(
    task_id: str,
    services: list[str],
    granularity: str,
    *,
    expected_duration: int = DEFAULT_TASK_JWT_TTL_SECONDS,
    expected_step_duration: int = DEFAULT_STEP_JWT_TTL_SECONDS,
    segment_enabled: bool = True,
) -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    svc_yaml = "\n".join(f"    - name: {name}" for name in services)
    segment = "true" if segment_enabled else "false"
    _apply_yaml(
        f"""
apiVersion: bounded-autonomy.io/v1
kind: TaskDeclaration
metadata:
  name: {task_id}
  namespace: {NS}
spec:
  taskId: {task_id}
  expectedDurationSeconds: {int(expected_duration)}
  expectedStepDurationSeconds: {int(expected_step_duration)}
  createdAt: "{created}"
  granularity: {granularity}
  segmentEnabled: {segment}
  services:
{svc_yaml}
"""
    )
    spec = {
        "taskId": task_id,
        "expectedDurationSeconds": int(expected_duration),
        "expectedStepDurationSeconds": int(expected_step_duration),
        "granularity": granularity,
        "segmentEnabled": segment_enabled,
        "services": [{"name": name} for name in services],
        "namespace": NS,
    }
    if segment_enabled:
        rendered = render_cnp(task_id, NS, spec)
        docs = [rendered["egress"], *rendered["ingress"]]
        _apply_yaml("---\n".join(yaml.safe_dump(doc) for doc in docs))
        _ensure_spire_task_entry(spec)
    _apply_gateway_from_host(spec)
    return created


def _apply_undeclared_ingress_deny(task_id: str, declared: list[str]) -> None:
    """Close ingress on undeclared inventory services so |R| cannot leak via fail-open egress."""
    deny = [name for name in INVENTORY if name not in set(declared)]
    docs = []
    for svc in deny:
        docs.append(
            {
                "apiVersion": "cilium.io/v2",
                "kind": "CiliumNetworkPolicy",
                "metadata": {
                    "name": f"{task_id}-deny-ingress-{svc}"[:63],
                    "namespace": NS,
                    "labels": {
                        "bounded-autonomy.io/task-id": task_id,
                        "bounded-autonomy.io/role": "ingress-deny",
                        "bounded-autonomy.io/sweep": "true",
                    },
                },
                "spec": {
                    "endpointSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": svc,
                            "app.kubernetes.io/part-of": "bounded-autonomy",
                        }
                    },
                    "enableDefaultDeny": {"ingress": True},
                    "ingress": [],
                },
            }
        )
    if docs:
        _apply_yaml("---\n".join(yaml.safe_dump(doc) for doc in docs))


def _apply_gateway_from_host(spec: dict[str, Any]) -> None:
    port = _free_port()
    proc = subprocess.Popen(
        [
            str(TOOLS / "kubectl"),
            "--context",
            CTX,
            "-n",
            GATEWAY_NS,
            "port-forward",
            "svc/apisix-admin",
            f"{port}:9180",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_tcp("127.0.0.1", port)
        apply_gateway_routes(spec, base=f"http://127.0.0.1:{port}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _collect_gateway_logs(since: float) -> list[dict[str, Any]]:
    iso = datetime.fromtimestamp(since - 2, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proc = _kubectl(
        "-n", GATEWAY_NS, "logs", "-l", "app.kubernetes.io/name=apisix",
        f"--since-time={iso}", check=False,
    )
    rows: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        uri = str(row.get("uri") or "")
        request = str(row.get("request") or "")
        host = str(row.get("host") or "")
        if "/apisix/admin/" in request or "/apisix/admin/" in uri or "apisix-admin" in host:
            continue
        path = request.split()[1] if len(request.split()) > 1 else uri
        service = path.strip("/").split("/", 1)[0] if path else ""
        if service in ("apisix", "tools", ""):
            continue
        rows.append(
            {
                "time": row.get("time"),
                "client": row.get("client"),
                "host": host,
                "uri": uri,
                "request": request,
                "status": int(row.get("status") or 0),
                "upstream": row.get("upstream"),
                "service": service,
            }
        )
    return rows


def _set_mode_policy(
    mode: str,
    task_id: str,
    services: list[str],
    granularity: str,
    *,
    gateway_bypass: bool = False,
    isolate: bool = False,
) -> float:
    if isolate:
        listing = _kubectl("-n", NS, "get", "cnp", "-o", "name", check=False)
        for raw in (listing.stdout or "").split():
            short = raw.split("/")[-1]
            if "long-multistep-k" in short or "deny-ingress" in short:
                _kubectl("-n", NS, "delete", "cnp", short, "--ignore-not-found", check=False)
        _kubectl(
            "-n", NS, "delete", "cnp", "-l", "bounded-autonomy.io/sweep=true",
            "--ignore-not-found", check=False,
        )
        _kubectl("-n", NS, "delete", "td", task_id, "--ignore-not-found", check=False)
        _kubectl(
            "-n", NS, "delete", "cnp", "-l", f"bounded-autonomy.io/task-id={task_id}",
            "--ignore-not-found", check=False,
        )
    else:
        _kubectl("-n", NS, "delete", "cnp", "--all", "--ignore-not-found", check=False)
        _kubectl("-n", NS, "delete", "td", "--all", "--ignore-not-found", check=False)
    if mode == "flat":
        time.sleep(2)
        return 0.0
    segment = uses_segment(mode, gateway_bypass)
    _apply_declaration(task_id, services, granularity, segment_enabled=segment)
    if isolate and segment:
        _apply_undeclared_ingress_deny(task_id, services)
    if not segment:
        time.sleep(2)
        return 0.0
    return _wait_cnp(task_id)


def _spire_server_pod() -> str:
    proc = _kubectl(
        "-n", SPIRE_NS, "get", "pod",
        "-l", "app.kubernetes.io/name=spire-server",
        "-o", "jsonpath={.items[0].metadata.name}",
        check=False,
    )
    name = (proc.stdout or "").strip()
    if not name:
        raise RuntimeError(f"no SPIRE server pod: {proc.stderr}")
    return name


def _spire_exec(*args: str) -> str:
    proc = _kubectl(
        "-n", SPIRE_NS, "exec", _spire_server_pod(), "-c", "spire-server", "--",
        "/opt/spire/bin/spire-server", *args, "-socketPath", SPIRE_SOCKET,
        check=False,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def _ensure_spire_task_entry(spec: dict[str, Any]) -> None:
    _ensure_pod_x509_entry()
    entry = render_spire_entry(spec, SPIRE_PARENT)
    shown = _spire_exec("entry", "show", "-spiffeID", entry["spiffe_id"])
    ids = parse_entry_ids(shown)
    if ids:
        _spire_exec(
            "entry", "update",
            "-entryID", ids[0],
            "-spiffeID", entry["spiffe_id"],
            "-parentID", entry["parent_id"],
            "-x509SVIDTTL", str(entry["x509_svid_ttl"]),
            "-jwtSVIDTTL", str(entry["jwt_svid_ttl"]),
            *[a for sel in entry["selectors"] for a in ("-selector", sel)],
        )
        return
    _spire_exec(
        "entry", "create",
        "-spiffeID", entry["spiffe_id"],
        "-parentID", entry["parent_id"],
        "-x509SVIDTTL", str(entry["x509_svid_ttl"]),
        "-jwtSVIDTTL", str(entry["jwt_svid_ttl"]),
        *[a for sel in entry["selectors"] for a in ("-selector", sel)],
    )


def _ensure_pod_x509_entry() -> None:
    entry = render_pod_spire_entry(SPIRE_PARENT, NS)
    shown = _spire_exec("entry", "show", "-spiffeID", entry["spiffe_id"])
    if parse_entry_ids(shown):
        return
    _spire_exec(
        "entry", "create",
        "-spiffeID", entry["spiffe_id"],
        "-parentID", entry["parent_id"],
        "-x509SVIDTTL", str(entry["x509_svid_ttl"]),
        "-jwtSVIDTTL", str(entry["jwt_svid_ttl"]),
        *[a for sel in entry["selectors"] for a in ("-selector", sel)],
    )


def _mint_jwt_svid(spiffe_id: str, ttl: int) -> dict[str, Any]:
    """Mint a JWT-SVID. τ = exp − iat from the token claims."""
    last_err = ""
    for _ in range(8):
        text = _spire_exec(
            "jwt", "mint",
            "-spiffeID", spiffe_id,
            "-audience", JWT_AUDIENCE,
            "-ttl", f"{int(ttl)}s",
        )
        last_err = text
        try:
            token = extract_jwt_token(text)
            claims = decode_jwt_claims(token)
            tau = tau_from_claims(claims)
            return {
                "token": token,
                "claims": claims,
                "iat": tau["iat"],
                "exp": tau["exp"],
                "tau_seconds": tau["tau_seconds"],
                "spiffe_id": claims.get("sub") or spiffe_id,
            }
        except (ValueError, KeyError, IndexError):
            time.sleep(0.5)
    raise RuntimeError(f"jwt mint failed for {spiffe_id}: {last_err[:400]}")


def _delete_spire_entry(spiffe_id: str) -> float:
    """Delete the registration entry. Recorded as entry_deleted_at, not revocation."""
    shown = _spire_exec("entry", "show", "-spiffeID", spiffe_id)
    for entry_id in parse_entry_ids(shown):
        _spire_exec("entry", "delete", "-entryID", entry_id)
    return time.time()


def _cluster_ip(service: str) -> str:
    proc = _kubectl("-n", NS, "get", "svc", service, "-o", "jsonpath={.spec.clusterIP}")
    ip = (proc.stdout or "").strip()
    if not ip:
        raise RuntimeError(f"no ClusterIP for {service}: {proc.stderr}")
    return ip


def _probe_service(pod: str, service: str, timeout: float = 3.0, attempts: int = 3) -> bool:
    port = SERVICE_PORTS[service]
    ip = _cluster_ip(service)
    code = (
        "import socket,sys; "
        f"s=socket.socket(); s.settimeout({timeout}); "
        f"ok=s.connect_ex(('{ip}',{port}))==0; "
        "s.close(); sys.exit(0 if ok else 1)"
    )
    for _ in range(attempts):
        proc = _kubectl("-n", NS, "exec", pod, "--", "python", "-c", code, check=False)
        if proc.returncode == 0:
            return True
        time.sleep(0.2 if timeout < 1 else 1)
    return False


def cluster_probe(
    mode: str,
    seed: int,
    pod: str,
    task_id: str,
    *,
    timeout: float = 3.0,
    attempts: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    spiffe = _spiffe(task_id)
    probe_rows: list[dict[str, Any]] = []
    flow_rows: list[dict[str, Any]] = []
    for svc in INVENTORY:
        ok = _probe_service(pod, svc, timeout=timeout, attempts=attempts)
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


def _sync_worker_code(pod: str) -> None:
    """Copy host plan/worker into the agent pod so sweep variants match this tree."""
    pairs = (
        (ROOT / "rig" / "plan.py", f"{NS}/{pod}:/app/rig/plan.py"),
        (ROOT / "rig" / "profiles.py", f"{NS}/{pod}:/app/rig/profiles.py"),
        (ROOT / "rig" / "modes.py", f"{NS}/{pod}:/app/rig/modes.py"),
        (ROOT / "rig" / "harness" / "live_worker.py", f"{NS}/{pod}:/app/rig/harness/live_worker.py"),
        (
            ROOT / "rig" / "harness" / "payloads" / "v-data.yaml",
            f"{NS}/{pod}:/app/rig/harness/payloads/v-data.yaml",
        ),
    )
    for src, dest in pairs:
        if not src.exists():
            continue
        _kubectl("cp", str(src), dest, check=False)


def _exec_worker(args: list[str], pod: str = "agent") -> dict[str, Any]:
    proc = _kubectl(
        "-n", NS, "exec", pod, "--",
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
    variant: str | None = None,
    profile: str = "long-multistep",
    gateway_bypass: bool = False,
) -> dict[str, Any]:
    spec = profile_spec(profile)
    declared = declared_services(variant) if variant else list(spec["declared"])
    if granularity == "step":
        task_id = f"{profile}-{mode}-step-seed{seed}"
    elif variant:
        task_id = f"{profile}-{variant}-{mode}-seed{seed}"
    else:
        task_id = run_id_for(
            profile=profile, mode=mode, seed=seed, gateway_bypass=gateway_bypass
        )
    spiffe = _spiffe(task_id)
    result = run_local(
        mode=mode,
        seed=seed,
        out_dir=out_dir,
        injection=True,
        baseline_spans=baseline_spans,
        granularity=granularity,
        task_id=task_id,
        declared=declared,
        variant=variant,
        breach_services=[INJECTION_SERVICE if variant else spec["injection_service"]],
        profile=profile,
        gateway_bypass=gateway_bypass,
    )
    pod_name = "agent-sweep" if variant else "agent"
    pod = _ensure_agent(task_id, mode, pod_name=pod_name)
    _sync_worker_code(pod)
    step_d: list[float] = []
    step_ratios: list[float] = []
    svid_rows: list[dict[str, Any]] = []
    task_jwt: dict[str, Any] | None = None
    task_start = time.time()
    p_ms = _set_mode_policy(
        mode,
        task_id,
        list(declared),
        granularity,
        gateway_bypass=gateway_bypass,
        isolate=bool(variant),
    )
    if mode == "full":
        # DNS-proxy matchName attaches after CNP Valid; 2 s avoids a first-lookup blackhole.
        time.sleep(2)
    declared_arg = ",".join(declared)
    jwt_ttl = (
        DEFAULT_STEP_JWT_TTL_SECONDS
        if granularity == "step"
        else DEFAULT_TASK_JWT_TTL_SECONDS
    )
    if granularity == "step" and mode == "full":
        plan = build_step_plan(seed, declared=declared)
        payload = load_payload("v1", seed)
        last = None
        for step in plan:
            tool = pick_tool(step.instruction, list(declared), last)
            if step.index == 15:
                tool = pick_from_injection(payload, list(declared))
            d_ms = 0.0
            jwt = _mint_jwt_svid(spiffe, jwt_ttl)
            if task_jwt is None:
                task_jwt = jwt
            if tool in declared:
                _apply_declaration(task_id, [tool], "step")
                d_ms = _wait_cnp(task_id)
            step_start = time.time()
            step_d.append(d_ms)
            _exec_worker(
                [
                    "--mode", mode, "--seed", str(seed),
                    "--task-id", task_id, "--spiffe-id", spiffe,
                    "--only-step", str(step.index), "--no-root",
                    "--declared", declared_arg,
                    "--profile", profile,
                ],
                pod=pod,
            )
            step_end = time.time()
            tau_step = max(float(jwt["tau_seconds"]), 1e-6)
            t_step = max(step_end - step_start, 1e-6)
            step_ratios.append(tau_step / t_step)
            svid_rows.append(
                {
                    "task_id": task_id,
                    "step": step.index,
                    "spiffe_id": spiffe,
                    "issued_at": datetime.fromtimestamp(jwt["iat"], timezone.utc).isoformat(),
                    "not_after": datetime.fromtimestamp(jwt["exp"], timezone.utc).isoformat(),
                    "issued_at_epoch": jwt["iat"],
                    "not_after_epoch": jwt["exp"],
                    "step_start_epoch": step_start,
                    "step_end_epoch": step_end,
                    "credential_kind": "jwt-svid",
                    "spire_entry": True,
                }
            )
            last = {"forced_tool": tool}
        worker = {"start_epoch": task_start, "end_epoch": time.time()}
    else:
        if mode == "full":
            task_jwt = _mint_jwt_svid(spiffe, jwt_ttl)
        worker = _exec_worker(
            [
                "--mode", mode, "--seed", str(seed),
                "--task-id", task_id, "--spiffe-id", spiffe,
                "--declared", declared_arg,
                "--profile", profile,
            ] + (["--gateway-bypass"] if gateway_bypass else []),
            pod=pod,
        )
    task_end = time.time()
    if deploys_gateway_policy(mode, gateway_bypass):
        time.sleep(2)
    gw_rows = _collect_gateway_logs(task_start) if deploys_gateway_policy(mode, gateway_bypass) else []
    if gw_rows or deploys_gateway_policy(mode, gateway_bypass):
        pd.DataFrame(gw_rows).to_parquet(out_dir / "gateway.parquet", index=False)
    if variant:
        probe_rows, flow_rows = [], []
        for _ in range(4):
            _kubectl(
                "-n", NS, "label", "pod", pod,
                f"bounded-autonomy.io/task-id={task_id}", "--overwrite",
                check=False,
            )
            p_ms = _set_mode_policy(
                mode,
                task_id,
                list(declared),
                granularity,
                gateway_bypass=gateway_bypass,
                isolate=True,
            )
            probe_rows, flow_rows = cluster_probe(
                mode, seed, pod, task_id, timeout=0.4, attempts=2
            )
            reached_now = sorted({r["service"] for r in probe_rows if r["success"]})
            if reached_now == sorted(declared):
                break
    else:
        probe_rows, flow_rows = cluster_probe(mode, seed, pod, task_id)
    if mode == "full" and granularity == "step":
        _apply_declaration(task_id, list(declared), "task")
        _wait_cnp(task_id)
        probe_rows, flow_rows = cluster_probe(mode, seed, pod, task_id)
    evasion_rows = run_evasion(_kubectl, pod, NS, mode)
    write_evasion(out_dir / "evasion.parquet", evasion_rows)
    policy_removed_at: float | None = None
    entry_deleted_at: float | None = None
    if uses_segment(mode, gateway_bypass):
        q_ms = _delete_segment(task_id)
        # Residual (b) is segment collapse, not probe/evasion wall after task_end.
        policy_removed_at = float(task_end) + (q_ms / 1000.0)
        entry_deleted_at = _delete_spire_entry(spiffe)
    else:
        q_ms = 0.0
    pd.DataFrame(probe_rows).to_parquet(out_dir / "probe.parquet", index=False)
    pd.DataFrame(flow_rows).to_parquet(out_dir / "flows.parquet", index=False)

    if uses_flat_credential(mode):
        issued_epoch, not_after_epoch = _flat_token_epochs(pod)
        cred_kind = "sa-token"
    elif task_jwt is not None:
        issued_epoch = float(task_jwt["iat"])
        not_after_epoch = float(task_jwt["exp"])
        cred_kind = "jwt-svid"
    else:
        raise RuntimeError("full mode requires a minted JWT-SVID (τ = exp − iat)")
    t_start = float(worker.get("start_epoch") or task_start)
    t_end = float(worker.get("end_epoch") or task_end)
    if not svid_rows:
        svid_rows.append(
            {
                "task_id": task_id,
                "step": None,
                "spiffe_id": spiffe if mode == "full" else "system:serviceaccount:rig:agent",
                "issued_at": datetime.fromtimestamp(issued_epoch, timezone.utc).isoformat(),
                "not_after": datetime.fromtimestamp(not_after_epoch, timezone.utc).isoformat(),
                "issued_at_epoch": issued_epoch,
                "not_after_epoch": not_after_epoch,
                "step_start_epoch": t_start,
                "step_end_epoch": t_end,
                "credential_kind": cred_kind,
                "spire_entry": mode == "full",
            }
        )
    pd.DataFrame(svid_rows).to_parquet(out_dir / "svid.parquet", index=False)

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
            "variant": variant,
            "gateway_bypass": gateway_bypass,
            "started_at": datetime.fromtimestamp(t_start, timezone.utc).isoformat().replace("+00:00", "Z"),
            "finished_at": datetime.fromtimestamp(t_end, timezone.utc).isoformat().replace("+00:00", "Z"),
            "wall_clock_seconds": t_end - t_start,
            "declaration": {
                **meta["declaration"],
                "task_id": task_id,
                "spiffe_id": spiffe,
                "granularity": granularity,
                "services": list(declared),
                **(
                    {"declared_count": len(declared), "variant": variant}
                    if variant
                    else {}
                ),
            },
            "breach_services": [INJECTION_SERVICE],
            "steps_completed": meta["steps_completed"],
            "write_counts": meta["write_counts"],
            "policy_propagation_ms": step_d if step_d else ([p_ms] if p_ms else []),
            "source": "cluster",
            "segment_p_ms": p_ms,
            "segment_q_ms": q_ms,
            "step_ratios": step_ratios,
            "reachable_weight": reachable_weight(reached),
            "entry_deleted_at_epoch": entry_deleted_at,
            "policy_removed_at_epoch": policy_removed_at,
            "task_end_epoch": task_end,
        },
        baseline_spans=baseline_spans,
    )
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
