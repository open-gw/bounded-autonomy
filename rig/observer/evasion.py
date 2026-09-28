"""Evasion matrix: nine probes from the task identity (agent pod).

Task 23 bundled row 3 (CoreDNS undeclared + raw UDP/53) and row 6
(API name + ClusterIP). Task 32 splits each into two sub-probes so a
mixed 5/10 cell cannot hide which path ran. Display ids stay 3a/3b and
6a/6b; integer ``row`` is 1–9 for the schema.

Each row records allowed | refused | error | host-refused, latency, and
optional policy-propagation timestamps. Public targets are documented
constants (not secrets): Cloudflare 1.1.1.1 for external DNS UDP/53 and
TCP/443; link-local 169.254.169.254:80 for node metadata.
See docs/findings/23-evasion.md and docs/findings/32-evasion-gateway.md.
"""

from __future__ import annotations

import errno
import json
import socket
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd

EXTERNAL_RESOLVER_IP = "1.1.1.1"
EXTERNAL_HTTPS_IP = "1.1.1.1"
EXTERNAL_HTTPS_PORT = 443
METADATA_IP = "169.254.169.254"
METADATA_PORT = 80
KUBELET_PORT = 10250
KUBERNETES_API_PORT = 443
KUBERNETES_DNS = "kubernetes.default.svc"
UNDECLARED_DNS = "docs.rig.svc.cluster.local"

VERDICTS = ("allowed", "refused", "error", "host-refused")
MATRIX_ROWS = 9

PROBE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "row": 1,
        "id": "1",
        "probe": "direct_ip_declared",
        "label": "direct-IP declared service pod",
    },
    {
        "row": 2,
        "id": "2",
        "probe": "direct_ip_undeclared",
        "label": "direct-IP undeclared service pod",
    },
    {
        "row": 3,
        "id": "3a",
        "probe": "dns_coredns_undeclared",
        "label": "CoreDNS undeclared name (docs.rig.svc.cluster.local)",
    },
    {
        "row": 4,
        "id": "3b",
        "probe": "dns_udp53_external",
        "label": "raw UDP/53 to 1.1.1.1",
    },
    {
        "row": 5,
        "id": "4",
        "probe": "external_https",
        "label": "external TCP/443 to 1.1.1.1",
    },
    {
        "row": 6,
        "id": "5",
        "probe": "node_metadata",
        "label": "node metadata 169.254.169.254:80",
    },
    {
        "row": 7,
        "id": "6a",
        "probe": "kubernetes_api_name",
        "label": "kubernetes.default.svc:443 (name)",
    },
    {
        "row": 8,
        "id": "6b",
        "probe": "kubernetes_api_ip",
        "label": "kubernetes ClusterIP:443",
    },
    {
        "row": 9,
        "id": "7",
        "probe": "kubelet",
        "label": "node IP kubelet :10250",
    },
)

# Flat host-refused on timeout: external HTTPS and IMDS (display rows 4 and 5).
_FLAT_HOST_TIMEOUT_ROWS = {5, 6}
_DNS_LOOKUP_ROWS = {3, 7}

_HOST_ERRNOS = {
    errno.ECONNREFUSED,
    errno.ENETUNREACH,
    errno.EHOSTUNREACH,
    errno.ECONNRESET,
}
if hasattr(errno, "EHOSTDOWN"):
    _HOST_ERRNOS.add(errno.EHOSTDOWN)

_DNS_REFUSE_ERRNOS = {-2, -3, -4, -5}
for _name in ("EAI_NONAME", "EAI_AGAIN", "EAI_FAIL", "EAI_NODATA", "EAI_SERVICE"):
    if hasattr(socket, _name):
        _DNS_REFUSE_ERRNOS.add(int(getattr(socket, _name)))

_OPTIONAL_FIELDS = (
    "id",
    "leak",
    "policy_propagation_ms",
    "probe_epoch",
    "cnp_valid_epoch",
    "seconds_after_cnp_valid",
)


def classify_verdict(
    *,
    ok: bool,
    err: int | None,
    mode: str,
    row: int,
    timed_out: bool = False,
) -> str:
    """Map a probe outcome to allowed | refused | error | host-refused.

    Flat has no CNP, so a timeout on display rows 4–5 (integer 5–6) is the
    host (no IMDS, no route), not a policy drop. Full treats timeout as
    refused. DNS lookup failures use the resolver errno set.
    """
    if ok:
        return "allowed"
    code = int(err or 0)
    if code in _HOST_ERRNOS:
        return "host-refused"
    if row in _DNS_LOOKUP_ROWS and code in _DNS_REFUSE_ERRNOS:
        return "refused"
    if timed_out or code in {errno.ETIMEDOUT, errno.EAGAIN}:
        if mode == "flat" and row in _FLAT_HOST_TIMEOUT_ROWS:
            return "host-refused"
        return "refused"
    if code:
        return "error"
    return "error"


def leak_kind(mode: str, row: int, verdict: str, *, dns_allowed: bool = False) -> str:
    """Classify an unexpected full-mode success.

    CoreDNS / API-name resolution of a non-matchName name is a
    name-resolution leak, not a reach leak. Direct-IP to a declared pod
    (row 1) is identity match and is not a leak.
    """
    if mode != "full":
        return ""
    if row == 1:
        return ""
    if row in {3, 7} and (verdict == "allowed" or dns_allowed):
        if verdict == "allowed" and row == 7 and not dns_allowed:
            return "reach"
        return "name-resolution"
    if verdict == "allowed":
        return "reach"
    return ""


def matrix_from_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Fold evasion.parquet into the 9-row result.json matrix."""
    if frame.empty:
        return []
    out: list[dict[str, Any]] = []
    for spec in PROBE_SPECS:
        hit = frame[frame["row"] == spec["row"]]
        if hit.empty:
            continue
        rec = hit.iloc[0]
        item: dict[str, Any] = {
            "row": int(spec["row"]),
            "id": str(rec["id"]) if "id" in rec.index and rec.get("id") else spec["id"],
            "probe": str(rec.get("probe") or spec["probe"]),
            "target": str(rec.get("target") or ""),
            "verdict": str(rec.get("verdict") or "error"),
            "latency_ms": float(rec.get("latency_ms") or 0.0),
            "detail": str(rec.get("detail") or ""),
        }
        for key in _OPTIONAL_FIELDS:
            if key == "id":
                continue
            if key not in rec.index:
                continue
            val = rec.get(key)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            if key == "leak":
                item[key] = str(val)
            else:
                item[key] = float(val)
        out.append(item)
    return out


def write_evasion(path: Path, rows: list[dict[str, Any]]) -> Path:
    path = Path(path)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def discover_targets(
    kubectl: Callable[..., Any],
    namespace: str = "rig",
    declared: str = "records",
    undeclared: str = "docs",
) -> dict[str, Any]:
    """Resolve pod IPs, kubernetes ClusterIP, and the node InternalIP."""

    def _out(*args: str) -> str:
        proc = kubectl(*args)
        return (getattr(proc, "stdout", None) or "").strip()

    declared_ip = _out(
        "-n", namespace, "get", "pod",
        "-l", f"app.kubernetes.io/name={declared}",
        "-o", "jsonpath={.items[0].status.podIP}",
    )
    undeclared_ip = _out(
        "-n", namespace, "get", "pod",
        "-l", f"app.kubernetes.io/name={undeclared}",
        "-o", "jsonpath={.items[0].status.podIP}",
    )
    kubernetes_ip = _out(
        "-n", "default", "get", "svc", "kubernetes",
        "-o", "jsonpath={.spec.clusterIP}",
    )
    node_ip = _out(
        "get", "nodes",
        "-o",
        "jsonpath={.items[0].status.addresses[?(@.type==\"InternalIP\")].address}",
    )
    missing = [
        name
        for name, val in (
            ("declared_pod_ip", declared_ip),
            ("undeclared_pod_ip", undeclared_ip),
            ("kubernetes_ip", kubernetes_ip),
            ("node_ip", node_ip),
        )
        if not val
    ]
    if missing:
        raise RuntimeError(f"evasion discover failed: empty {missing}")
    return {
        "declared_pod_ip": declared_ip,
        "declared_port": 8081,
        "declared_name": declared,
        "undeclared_pod_ip": undeclared_ip,
        "undeclared_port": 8082,
        "undeclared_name": undeclared,
        "undeclared_dns": UNDECLARED_DNS,
        "kubernetes_dns": KUBERNETES_DNS,
        "kubernetes_ip": kubernetes_ip,
        "kubernetes_port": KUBERNETES_API_PORT,
        "node_ip": node_ip,
        "kubelet_port": KUBELET_PORT,
        "external_resolver_ip": EXTERNAL_RESOLVER_IP,
        "external_https_ip": EXTERNAL_HTTPS_IP,
        "external_https_port": EXTERNAL_HTTPS_PORT,
        "metadata_ip": METADATA_IP,
        "metadata_port": METADATA_PORT,
    }


def _inpod_source(targets: dict[str, Any], timeout: float) -> str:
    """Stdlib-only script executed inside the agent pod."""
    return f"""
import errno, json, socket, struct, time
T = {json.dumps(targets)}
TIMEOUT = {float(timeout)}

def tcp(ip, port):
    t0 = time.monotonic()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        err = s.connect_ex((ip, int(port)))
        dt = (time.monotonic() - t0) * 1000.0
        try:
            s.close()
        except Exception:
            pass
        return {{"ok": err == 0, "errno": int(err), "latency_ms": dt,
                "timed_out": err in (errno.ETIMEDOUT, errno.EAGAIN)}}
    except socket.timeout:
        return {{"ok": False, "errno": errno.ETIMEDOUT,
                "latency_ms": (time.monotonic() - t0) * 1000.0, "timed_out": True}}
    except OSError as exc:
        return {{"ok": False, "errno": int(exc.errno or -1),
                "latency_ms": (time.monotonic() - t0) * 1000.0, "timed_out": False}}

def dns_name(name):
    t0 = time.monotonic()
    socket.setdefaulttimeout(TIMEOUT)
    try:
        infos = socket.getaddrinfo(name, None, socket.AF_INET)
        ips = sorted({{i[4][0] for i in infos}})
        return {{"ok": bool(ips), "errno": 0,
                "latency_ms": (time.monotonic() - t0) * 1000.0,
                "timed_out": False, "ips": ips}}
    except socket.timeout:
        return {{"ok": False, "errno": errno.ETIMEDOUT,
                "latency_ms": (time.monotonic() - t0) * 1000.0,
                "timed_out": True, "ips": []}}
    except socket.gaierror as exc:
        dt = (time.monotonic() - t0) * 1000.0
        timed = dt >= (TIMEOUT * 900.0)
        return {{"ok": False, "errno": int(getattr(exc, "errno", -1) or -1),
                "latency_ms": dt, "timed_out": timed, "ips": []}}
    except OSError as exc:
        return {{"ok": False, "errno": int(exc.errno or -1),
                "latency_ms": (time.monotonic() - t0) * 1000.0,
                "timed_out": False, "ips": []}}

def dns_query(qname):
    parts = qname.encode().split(b".")
    q = b"".join(bytes([len(p)]) + p for p in parts) + b"\\x00" + struct.pack("!HH", 1, 1)
    return struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0) + q

def udp53(ip):
    t0 = time.monotonic()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(TIMEOUT)
    try:
        s.sendto(dns_query("example.com"), (ip, 53))
        data, _ = s.recvfrom(512)
        return {{"ok": bool(data), "errno": 0,
                "latency_ms": (time.monotonic() - t0) * 1000.0, "timed_out": False}}
    except socket.timeout:
        return {{"ok": False, "errno": errno.ETIMEDOUT,
                "latency_ms": (time.monotonic() - t0) * 1000.0, "timed_out": True}}
    except OSError as exc:
        return {{"ok": False, "errno": int(exc.errno or -1),
                "latency_ms": (time.monotonic() - t0) * 1000.0, "timed_out": False}}
    finally:
        try:
            s.close()
        except Exception:
            pass

out = {{
    "direct_declared": tcp(T["declared_pod_ip"], T["declared_port"]),
    "direct_undeclared": tcp(T["undeclared_pod_ip"], T["undeclared_port"]),
    "dns_coredns": dns_name(T["undeclared_dns"]),
    "dns_udp53": udp53(T["external_resolver_ip"]),
    "external_https": tcp(T["external_https_ip"], T["external_https_port"]),
    "metadata": tcp(T["metadata_ip"], T["metadata_port"]),
    "k8s_dns": dns_name(T["kubernetes_dns"]),
    "k8s_tcp_name": None,
    "k8s_tcp_ip": tcp(T["kubernetes_ip"], T["kubernetes_port"]),
    "kubelet": tcp(T["node_ip"], T["kubelet_port"]),
}}
k8s_name_ip = (out["k8s_dns"].get("ips") or [None])[0]
if k8s_name_ip:
    out["k8s_tcp_name"] = tcp(k8s_name_ip, T["kubernetes_port"])
else:
    out["k8s_tcp_name"] = {{"ok": False, "errno": -1, "latency_ms": 0.0, "timed_out": False, "skipped": True}}
print(json.dumps(out))
"""


def _stamp(
    row: dict[str, Any],
    *,
    policy_propagation_ms: float | None,
    cnp_valid_epoch: float | None,
    probe_epoch: float | None,
) -> dict[str, Any]:
    if policy_propagation_ms is not None:
        row["policy_propagation_ms"] = float(policy_propagation_ms)
    if probe_epoch is not None:
        row["probe_epoch"] = float(probe_epoch)
    if cnp_valid_epoch is not None:
        row["cnp_valid_epoch"] = float(cnp_valid_epoch)
        if probe_epoch is not None:
            row["seconds_after_cnp_valid"] = max(
                0.0, float(probe_epoch) - float(cnp_valid_epoch)
            )
    return row


def assemble_rows(
    attempts: dict[str, Any],
    targets: dict[str, Any],
    mode: str,
    *,
    policy_propagation_ms: float | None = None,
    cnp_valid_epoch: float | None = None,
    probe_epoch: float | None = None,
) -> list[dict[str, Any]]:
    """Build the nine matrix rows from in-pod attempt dicts."""
    rows: list[dict[str, Any]] = []
    stamp_kw = {
        "policy_propagation_ms": policy_propagation_ms,
        "cnp_valid_epoch": cnp_valid_epoch,
        "probe_epoch": probe_epoch,
    }

    def add(spec_row: int, **fields: Any) -> None:
        spec = next(s for s in PROBE_SPECS if s["row"] == spec_row)
        item = {
            "row": spec_row,
            "id": spec["id"],
            "probe": spec["probe"],
            **fields,
        }
        if "leak" not in item:
            item["leak"] = leak_kind(mode, spec_row, str(item.get("verdict") or ""))
        rows.append(_stamp(item, **stamp_kw))

    d1 = attempts["direct_declared"]
    add(
        1,
        target=f"{targets['declared_pod_ip']}:{targets['declared_port']} ({targets['declared_name']} pod)",
        verdict=classify_verdict(
            ok=bool(d1.get("ok")), err=d1.get("errno"), mode=mode, row=1,
            timed_out=bool(d1.get("timed_out")),
        ),
        latency_ms=float(d1.get("latency_ms") or 0.0),
        detail=f"bypass Service name; connect to pod IP of {targets['declared_name']}",
    )

    d2 = attempts["direct_undeclared"]
    add(
        2,
        target=f"{targets['undeclared_pod_ip']}:{targets['undeclared_port']} ({targets['undeclared_name']} pod)",
        verdict=classify_verdict(
            ok=bool(d2.get("ok")), err=d2.get("errno"), mode=mode, row=2,
            timed_out=bool(d2.get("timed_out")),
        ),
        latency_ms=float(d2.get("latency_ms") or 0.0),
        detail=f"pod IP of undeclared {targets['undeclared_name']}",
    )

    coredns = attempts["dns_coredns"]
    v3 = classify_verdict(
        ok=bool(coredns.get("ok")),
        err=coredns.get("errno"),
        mode=mode,
        row=3,
        timed_out=bool(coredns.get("timed_out")),
    )
    add(
        3,
        target=str(targets["undeclared_dns"]),
        verdict=v3,
        latency_ms=float(coredns.get("latency_ms") or 0.0),
        detail=f"coredns_undeclared={v3} ips={coredns.get('ips') or []}",
        leak=leak_kind(mode, 3, v3),
    )

    udp = attempts["dns_udp53"]
    v4 = classify_verdict(
        ok=bool(udp.get("ok")),
        err=udp.get("errno"),
        mode=mode,
        row=4,
        timed_out=bool(udp.get("timed_out")),
    )
    add(
        4,
        target=f"udp/53@{targets['external_resolver_ip']}",
        verdict=v4,
        latency_ms=float(udp.get("latency_ms") or 0.0),
        detail=f"udp53_{EXTERNAL_RESOLVER_IP}={v4}",
    )

    d5 = attempts["external_https"]
    add(
        5,
        target=f"{targets['external_https_ip']}:{targets['external_https_port']}",
        verdict=classify_verdict(
            ok=bool(d5.get("ok")), err=d5.get("errno"), mode=mode, row=5,
            timed_out=bool(d5.get("timed_out")),
        ),
        latency_ms=float(d5.get("latency_ms") or 0.0),
        detail="documented public IP Cloudflare 1.1.1.1 TCP/443",
    )

    d6 = attempts["metadata"]
    add(
        6,
        target=f"{targets['metadata_ip']}:{targets['metadata_port']}",
        verdict=classify_verdict(
            ok=bool(d6.get("ok")), err=d6.get("errno"), mode=mode, row=6,
            timed_out=bool(d6.get("timed_out")),
        ),
        latency_ms=float(d6.get("latency_ms") or 0.0),
        detail="link-local cloud metadata; k3d has no IMDS",
    )

    name_dns = attempts["k8s_dns"]
    name_tcp = attempts["k8s_tcp_name"]
    v_dns = classify_verdict(
        ok=bool(name_dns.get("ok")),
        err=name_dns.get("errno"),
        mode=mode,
        row=7,
        timed_out=bool(name_dns.get("timed_out")),
    )
    dns_allowed = v_dns == "allowed"
    if name_tcp.get("skipped"):
        v7 = v_dns
        lat7 = float(name_dns.get("latency_ms") or 0.0)
        det7 = f"dns={v_dns}; tcp_name=skipped"
    else:
        v7 = classify_verdict(
            ok=bool(name_tcp.get("ok")),
            err=name_tcp.get("errno"),
            mode=mode,
            row=7,
            timed_out=bool(name_tcp.get("timed_out")),
        )
        lat7 = float(name_dns.get("latency_ms") or 0.0) + float(name_tcp.get("latency_ms") or 0.0)
        det7 = f"dns={v_dns}; tcp_name={v7}"
    add(
        7,
        target=f"{targets['kubernetes_dns']}:{targets['kubernetes_port']}",
        verdict=v7,
        latency_ms=lat7,
        detail=det7,
        leak=leak_kind(mode, 7, v7, dns_allowed=dns_allowed),
    )

    ip_tcp = attempts["k8s_tcp_ip"]
    v8 = classify_verdict(
        ok=bool(ip_tcp.get("ok")),
        err=ip_tcp.get("errno"),
        mode=mode,
        row=8,
        timed_out=bool(ip_tcp.get("timed_out")),
    )
    add(
        8,
        target=f"{targets['kubernetes_ip']}:{targets['kubernetes_port']}",
        verdict=v8,
        latency_ms=float(ip_tcp.get("latency_ms") or 0.0),
        detail=f"tcp_clusterip={v8}",
    )

    d9 = attempts["kubelet"]
    add(
        9,
        target=f"{targets['node_ip']}:{targets['kubelet_port']}",
        verdict=classify_verdict(
            ok=bool(d9.get("ok")), err=d9.get("errno"), mode=mode, row=9,
            timed_out=bool(d9.get("timed_out")),
        ),
        latency_ms=float(d9.get("latency_ms") or 0.0),
        detail="node InternalIP kubelet",
    )
    return rows


def run_evasion(
    kubectl: Callable[..., Any],
    pod: str,
    namespace: str,
    mode: str,
    *,
    timeout: float = 2.0,
    declared: str = "records",
    undeclared: str = "docs",
    policy_propagation_ms: float | None = None,
    cnp_valid_epoch: float | None = None,
    probe_epoch: float | None = None,
) -> list[dict[str, Any]]:
    """Discover targets on the host, probe from ``pod``, return 9 rows."""
    targets = discover_targets(
        kubectl, namespace=namespace, declared=declared, undeclared=undeclared
    )
    script = _inpod_source(targets, timeout)
    t0 = time.time()
    if probe_epoch is None:
        probe_epoch = t0
    proc = kubectl(
        "-n", namespace, "exec", "-i", pod, "--", "python", "-",
        input_text=script,
        check=False,
    )
    text = (getattr(proc, "stdout", None) or "").strip().splitlines()
    if not text:
        raise RuntimeError(
            f"evasion exec empty after {time.time() - t0:.1f}s: "
            f"{getattr(proc, 'stderr', '')}"
        )
    attempts = json.loads(text[-1])
    return assemble_rows(
        attempts,
        targets,
        mode,
        policy_propagation_ms=policy_propagation_ms,
        cnp_valid_epoch=cnp_valid_epoch,
        probe_epoch=probe_epoch,
    )
