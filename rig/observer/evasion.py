"""Evasion matrix: seven probes from the task identity (agent pod).

Each row records allowed | refused | error | host-refused and latency.
Public targets are documented constants (not secrets): Cloudflare 1.1.1.1
for external DNS UDP/53 and TCP/443; link-local 169.254.169.254:80 for
node metadata. See docs/findings/23-evasion.md.
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

PROBE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "row": 1,
        "probe": "direct_ip_declared",
        "label": "direct-IP declared service pod",
    },
    {
        "row": 2,
        "probe": "direct_ip_undeclared",
        "label": "direct-IP undeclared service pod",
    },
    {
        "row": 3,
        "probe": "dns",
        "label": "DNS undeclared via CoreDNS + raw UDP/53 to 1.1.1.1",
    },
    {
        "row": 4,
        "probe": "external_https",
        "label": "external TCP/443 to 1.1.1.1",
    },
    {
        "row": 5,
        "probe": "node_metadata",
        "label": "node metadata 169.254.169.254:80",
    },
    {
        "row": 6,
        "probe": "kubernetes_api",
        "label": "kubernetes.default.svc:443 and ClusterIP",
    },
    {
        "row": 7,
        "probe": "kubelet",
        "label": "node IP kubelet :10250",
    },
)

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


def classify_verdict(
    *,
    ok: bool,
    err: int | None,
    mode: str,
    row: int,
    timed_out: bool = False,
) -> str:
    """Map a probe outcome to allowed | refused | error | host-refused.

    Flat has no CNP, so a timeout on rows 4–5 is the host (no IMDS, no
    route), not a policy drop. Full treats timeout as refused.
    """
    if ok:
        return "allowed"
    code = int(err or 0)
    if code in _HOST_ERRNOS:
        return "host-refused"
    if row == 3 and code in _DNS_REFUSE_ERRNOS:
        return "refused"
    if timed_out or code in {errno.ETIMEDOUT, errno.EAGAIN}:
        if mode == "flat" and row in {4, 5}:
            return "host-refused"
        return "refused"
    if code:
        return "error"
    return "error"


def matrix_from_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Fold evasion.parquet into the 7-row result.json matrix."""
    if frame.empty:
        return []
    out: list[dict[str, Any]] = []
    for spec in PROBE_SPECS:
        hit = frame[frame["row"] == spec["row"]]
        if hit.empty:
            continue
        rec = hit.iloc[0]
        out.append(
            {
                "row": int(spec["row"]),
                "probe": str(rec.get("probe") or spec["probe"]),
                "target": str(rec.get("target") or ""),
                "verdict": str(rec.get("verdict") or "error"),
                "latency_ms": float(rec.get("latency_ms") or 0.0),
                "detail": str(rec.get("detail") or ""),
            }
        )
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


def _combine_dns(coredns: dict[str, Any], udp: dict[str, Any], mode: str) -> tuple[str, float, str]:
    """Row 3 verdict is the CoreDNS undeclared lookup (acceptance signal).

    External UDP/53 is recorded in detail. Combined latency is the sum.
    """
    v_dns = classify_verdict(
        ok=bool(coredns.get("ok")),
        err=coredns.get("errno"),
        mode=mode,
        row=3,
        timed_out=bool(coredns.get("timed_out")),
    )
    v_udp = classify_verdict(
        ok=bool(udp.get("ok")),
        err=udp.get("errno"),
        mode=mode,
        row=3,
        timed_out=bool(udp.get("timed_out")),
    )
    latency = float(coredns.get("latency_ms") or 0.0) + float(udp.get("latency_ms") or 0.0)
    detail = (
        f"coredns_undeclared={v_dns} ips={coredns.get('ips') or []}; "
        f"udp53_{EXTERNAL_RESOLVER_IP}={v_udp}"
    )
    return v_dns, latency, detail


def _combine_k8s(
    name_dns: dict[str, Any],
    name_tcp: dict[str, Any],
    ip_tcp: dict[str, Any],
    mode: str,
) -> tuple[str, float, str]:
    """Row 6: allowed if any path connected; refused if none did."""
    parts = []
    verdicts = []
    latency = 0.0
    v_dns = classify_verdict(
        ok=bool(name_dns.get("ok")),
        err=name_dns.get("errno"),
        mode=mode,
        row=6,
        timed_out=bool(name_dns.get("timed_out")),
    )
    parts.append(f"dns={v_dns}")
    latency += float(name_dns.get("latency_ms") or 0.0)
    for label, att in (
        ("tcp_name", name_tcp),
        ("tcp_clusterip", ip_tcp),
    ):
        if att.get("skipped"):
            parts.append(f"{label}=skipped")
            continue
        v = classify_verdict(
            ok=bool(att.get("ok")),
            err=att.get("errno"),
            mode=mode,
            row=6,
            timed_out=bool(att.get("timed_out")),
        )
        verdicts.append(v)
        latency += float(att.get("latency_ms") or 0.0)
        parts.append(f"{label}={v}")
    if any(v == "allowed" for v in verdicts):
        verdict = "allowed"
    elif verdicts and all(v == "refused" for v in verdicts):
        verdict = "refused"
    elif verdicts and all(v == "host-refused" for v in verdicts):
        verdict = "host-refused"
    elif verdicts and all(v in {"refused", "host-refused"} for v in verdicts):
        verdict = "refused" if mode == "full" else "host-refused"
    else:
        verdict = "error"
    return verdict, latency, "; ".join(parts)


def assemble_rows(
    attempts: dict[str, Any],
    targets: dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    """Build the seven matrix rows from in-pod attempt dicts."""
    rows: list[dict[str, Any]] = []

    d1 = attempts["direct_declared"]
    rows.append(
        {
            "row": 1,
            "probe": "direct_ip_declared",
            "target": f"{targets['declared_pod_ip']}:{targets['declared_port']} ({targets['declared_name']} pod)",
            "verdict": classify_verdict(
                ok=bool(d1.get("ok")), err=d1.get("errno"), mode=mode, row=1,
                timed_out=bool(d1.get("timed_out")),
            ),
            "latency_ms": float(d1.get("latency_ms") or 0.0),
            "detail": f"bypass Service name; connect to pod IP of {targets['declared_name']}",
        }
    )

    d2 = attempts["direct_undeclared"]
    rows.append(
        {
            "row": 2,
            "probe": "direct_ip_undeclared",
            "target": f"{targets['undeclared_pod_ip']}:{targets['undeclared_port']} ({targets['undeclared_name']} pod)",
            "verdict": classify_verdict(
                ok=bool(d2.get("ok")), err=d2.get("errno"), mode=mode, row=2,
                timed_out=bool(d2.get("timed_out")),
            ),
            "latency_ms": float(d2.get("latency_ms") or 0.0),
            "detail": f"pod IP of undeclared {targets['undeclared_name']}",
        }
    )

    v3, lat3, det3 = _combine_dns(attempts["dns_coredns"], attempts["dns_udp53"], mode)
    rows.append(
        {
            "row": 3,
            "probe": "dns",
            "target": f"{targets['undeclared_dns']}; udp/53@{targets['external_resolver_ip']}",
            "verdict": v3,
            "latency_ms": lat3,
            "detail": det3,
        }
    )

    d4 = attempts["external_https"]
    rows.append(
        {
            "row": 4,
            "probe": "external_https",
            "target": f"{targets['external_https_ip']}:{targets['external_https_port']}",
            "verdict": classify_verdict(
                ok=bool(d4.get("ok")), err=d4.get("errno"), mode=mode, row=4,
                timed_out=bool(d4.get("timed_out")),
            ),
            "latency_ms": float(d4.get("latency_ms") or 0.0),
            "detail": "documented public IP Cloudflare 1.1.1.1 TCP/443",
        }
    )

    d5 = attempts["metadata"]
    rows.append(
        {
            "row": 5,
            "probe": "node_metadata",
            "target": f"{targets['metadata_ip']}:{targets['metadata_port']}",
            "verdict": classify_verdict(
                ok=bool(d5.get("ok")), err=d5.get("errno"), mode=mode, row=5,
                timed_out=bool(d5.get("timed_out")),
            ),
            "latency_ms": float(d5.get("latency_ms") or 0.0),
            "detail": "link-local cloud metadata; k3d has no IMDS",
        }
    )

    v6, lat6, det6 = _combine_k8s(
        attempts["k8s_dns"], attempts["k8s_tcp_name"], attempts["k8s_tcp_ip"], mode
    )
    rows.append(
        {
            "row": 6,
            "probe": "kubernetes_api",
            "target": f"{targets['kubernetes_dns']}:{targets['kubernetes_port']}+{targets['kubernetes_ip']}",
            "verdict": v6,
            "latency_ms": lat6,
            "detail": det6,
        }
    )

    d7 = attempts["kubelet"]
    rows.append(
        {
            "row": 7,
            "probe": "kubelet",
            "target": f"{targets['node_ip']}:{targets['kubelet_port']}",
            "verdict": classify_verdict(
                ok=bool(d7.get("ok")), err=d7.get("errno"), mode=mode, row=7,
                timed_out=bool(d7.get("timed_out")),
            ),
            "latency_ms": float(d7.get("latency_ms") or 0.0),
            "detail": "node InternalIP kubelet",
        }
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
) -> list[dict[str, Any]]:
    """Discover targets on the host, probe from ``pod``, return 7 rows."""
    targets = discover_targets(
        kubectl, namespace=namespace, declared=declared, undeclared=undeclared
    )
    script = _inpod_source(targets, timeout)
    t0 = time.time()
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
    return assemble_rows(attempts, targets, mode)
