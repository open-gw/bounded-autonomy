"""Evasion matrix unit tests (no cluster)."""

from __future__ import annotations

import errno

import pandas as pd

from observer.evasion import (
    assemble_rows,
    classify_verdict,
    leak_kind,
    matrix_from_rows,
    write_evasion,
)


def _ok() -> dict:
    return {"ok": True, "errno": 0, "latency_ms": 1.0, "timed_out": False}


def _timeout() -> dict:
    return {"ok": False, "errno": errno.ETIMEDOUT, "latency_ms": 2000.0, "timed_out": True}


def _refused() -> dict:
    return {"ok": False, "errno": errno.ECONNREFUSED, "latency_ms": 2.0, "timed_out": False}


def test_classify_allowed_and_policy_timeout():
    assert classify_verdict(ok=True, err=0, mode="full", row=1) == "allowed"
    assert classify_verdict(ok=False, err=errno.ETIMEDOUT, mode="full", row=2, timed_out=True) == "refused"
    assert classify_verdict(ok=False, err=errno.ECONNREFUSED, mode="flat", row=5) == "host-refused"
    assert classify_verdict(ok=False, err=-2, mode="full", row=3) == "refused"


def test_classify_flat_rows_4_5_timeout_is_host():
    # Display rows 4/5 (integer 5/6): external HTTPS and IMDS.
    assert classify_verdict(ok=False, err=errno.ETIMEDOUT, mode="flat", row=5, timed_out=True) == "host-refused"
    assert classify_verdict(ok=False, err=errno.ETIMEDOUT, mode="flat", row=6, timed_out=True) == "host-refused"
    assert classify_verdict(ok=False, err=errno.ETIMEDOUT, mode="full", row=5, timed_out=True) == "refused"


def _targets() -> dict:
    return {
        "declared_pod_ip": "10.42.0.10",
        "declared_port": 8081,
        "declared_name": "records",
        "undeclared_pod_ip": "10.42.0.11",
        "undeclared_port": 8082,
        "undeclared_name": "docs",
        "undeclared_dns": "docs.rig.svc.cluster.local",
        "kubernetes_dns": "kubernetes.default.svc",
        "kubernetes_ip": "10.43.0.1",
        "kubernetes_port": 443,
        "node_ip": "172.18.0.2",
        "kubelet_port": 10250,
        "external_resolver_ip": "1.1.1.1",
        "external_https_ip": "1.1.1.1",
        "external_https_port": 443,
        "metadata_ip": "169.254.169.254",
        "metadata_port": 80,
    }


def test_assemble_full_acceptance_shape():
    attempts = {
        "direct_declared": _ok(),
        "direct_undeclared": _timeout(),
        "dns_coredns": {**_timeout(), "ips": []},
        "dns_udp53": _timeout(),
        "external_https": _timeout(),
        "metadata": _timeout(),
        "k8s_dns": {**_timeout(), "ips": []},
        "k8s_tcp_name": {**_timeout(), "skipped": True},
        "k8s_tcp_ip": _timeout(),
        "kubelet": _timeout(),
    }
    rows = assemble_rows(attempts, _targets(), "full")
    assert [r["row"] for r in rows] == list(range(1, 10))
    assert rows[0]["verdict"] == "allowed"
    assert all(r["verdict"] == "refused" for r in rows[1:])
    assert "docs.rig.svc.cluster.local" in rows[2]["target"]
    assert "1.1.1.1" in rows[3]["target"]
    assert "1.1.1.1" in rows[4]["target"]
    assert rows[2]["id"] == "3a" and rows[3]["id"] == "3b"
    assert rows[6]["id"] == "6a" and rows[7]["id"] == "6b"


def test_assemble_flat_rows_1_3_6_7_allowed():
    attempts = {
        "direct_declared": _ok(),
        "direct_undeclared": _ok(),
        "dns_coredns": {**_ok(), "ips": ["10.42.0.11"]},
        "dns_udp53": _ok(),
        "external_https": _timeout(),
        "metadata": _timeout(),
        "k8s_dns": {**_ok(), "ips": ["10.43.0.1"]},
        "k8s_tcp_name": _ok(),
        "k8s_tcp_ip": _ok(),
        "kubelet": _ok(),
    }
    rows = assemble_rows(attempts, _targets(), "flat")
    by_row = {r["row"]: r["verdict"] for r in rows}
    assert by_row[1] == "allowed"
    assert by_row[2] == "allowed"
    assert by_row[3] == "allowed"
    assert by_row[4] == "allowed"
    assert by_row[5] == "host-refused"
    assert by_row[6] == "host-refused"
    assert by_row[7] == "allowed"
    assert by_row[8] == "allowed"
    assert by_row[9] == "allowed"


def test_matrix_from_rows_roundtrip(tmp_path):
    rows = assemble_rows(
        {
            "direct_declared": _ok(),
            "direct_undeclared": _refused(),
            "dns_coredns": {**_timeout(), "ips": []},
            "dns_udp53": _timeout(),
            "external_https": _timeout(),
            "metadata": _timeout(),
            "k8s_dns": {**_timeout(), "ips": []},
            "k8s_tcp_name": {"ok": False, "errno": -1, "latency_ms": 0.0, "timed_out": False, "skipped": True},
            "k8s_tcp_ip": _timeout(),
            "kubelet": _timeout(),
        },
        _targets(),
        "full",
    )
    path = write_evasion(tmp_path / "evasion.parquet", rows)
    frame = pd.read_parquet(path)
    matrix = matrix_from_rows(frame)
    assert len(matrix) == 9
    assert matrix[0]["verdict"] == "allowed"
    assert {m["row"] for m in matrix} == set(range(1, 10))


def test_coredns_allowed_in_full_is_name_resolution_leak():
    attempts = {
        "direct_declared": _ok(),
        "direct_undeclared": _timeout(),
        "dns_coredns": {**_ok(), "ips": ["10.42.0.11"]},
        "dns_udp53": _timeout(),
        "external_https": _timeout(),
        "metadata": _timeout(),
        "k8s_dns": {**_ok(), "ips": ["10.43.0.1"]},
        "k8s_tcp_name": _timeout(),
        "k8s_tcp_ip": _timeout(),
        "kubelet": _timeout(),
    }
    rows = assemble_rows(attempts, _targets(), "full")
    by_row = {r["row"]: r for r in rows}
    assert by_row[3]["verdict"] == "allowed"
    assert by_row[3]["leak"] == "name-resolution"
    assert by_row[4]["verdict"] == "refused"
    assert by_row[4]["leak"] == ""
    assert by_row[7]["leak"] == "name-resolution"
    assert by_row[8]["verdict"] == "refused"
    assert leak_kind("full", 1, "allowed") == ""
    assert leak_kind("full", 3, "allowed") == "name-resolution"
