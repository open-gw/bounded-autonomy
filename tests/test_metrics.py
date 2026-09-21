"""Metric unit tests. Answers known by construction."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from metrics import (
    credential_ratio,
    reachable_set,
    rollback_completeness,
    verification_overhead,
)


def test_reachable_set_union_of_probe_and_forwarded_flows():
    probe = pd.DataFrame(
        [
            {"step": 1, "service": "records", "success": True},
            {"step": 1, "service": "docs", "success": False},
            {"step": 1, "service": "search", "success": True},
            {"step": 1, "service": "notify", "success": False},
        ]
    )
    flows = pd.DataFrame(
        [
            {
                "source_spiffe": "spiffe://rig/task/t1",
                "destination_service": "notify",
                "verdict": "FORWARDED",
            },
            {
                "source_spiffe": "spiffe://rig/task/t1",
                "destination_service": "billing",
                "verdict": "DROPPED",
            },
        ]
    )
    got = reachable_set(flows, probe)
    assert got == {"records", "search", "notify"}
    assert len(got) == 3


def test_reachable_set_flat_all_eight():
    names = [
        "records",
        "docs",
        "search",
        "notify",
        "billing",
        "analytics",
        "audit",
        "catalog",
    ]
    probe = pd.DataFrame(
        [{"step": 1, "service": n, "success": True} for n in names]
    )
    assert reachable_set(pd.DataFrame(), probe) == set(names)
    assert len(reachable_set([], probe)) == 8


def test_credential_ratio_one_svid_per_task():
    svid = pd.DataFrame(
        [
            {
                "task_id": "t1",
                "spiffe_id": "spiffe://rig/task/t1",
                "issued_at": "2026-01-01T00:00:00Z",
                "not_after": "2026-01-01T00:30:00Z",
            },
            {
                "task_id": "t2",
                "spiffe_id": "spiffe://rig/task/t2",
                "issued_at": "2026-01-01T00:31:00Z",
                "not_after": "2026-01-01T01:00:00Z",
            },
        ]
    )
    spans = pd.DataFrame(
        [
            {"task_id": "t1", "name": "orchestrator.step"},
            {"task_id": "t1", "name": "verify"},
            {"task_id": "t2", "name": "orchestrator.step"},
        ]
    )
    assert credential_ratio(svid, spans) == 1.0


def test_credential_ratio_nan_without_tasks():
    assert math.isnan(credential_ratio([], []))


def test_rollback_completeness_known_construction():
    lineage = pd.DataFrame(
        [
            {"task_id": "t1", "step": i, "write_class": cls, "store": store, "is_write": True}
            for i, (cls, store) in enumerate(
                [("idempotent", "postgres")] * 4
                + [("versioned", "postgres")] * 3
                + [("derived", "qdrant")] * 2
                + [("irreversible", "notify-log")] * 1,
                start=1,
            )
        ]
    )
    rows = []
    step = 1
    for cls, n, action, extra in (
        ("idempotent", 4, "restored", True),
        ("versioned", 3, "restored", True),
        ("derived", 2, "quarantined", False),
        ("irreversible", 1, "escalated", False),
    ):
        for _ in range(n):
            rows.append(
                {
                    "task_id": "t1",
                    "step": step,
                    "write_class": cls,
                    "store": "postgres",
                    "key": f"k{step}",
                    "before": "old",
                    "after": "new",
                    "restored_matches_before": extra if cls in ("idempotent", "versioned") else None,
                    "attestation_action": action,
                }
            )
            step += 1
    gt = pd.DataFrame(rows)
    got = rollback_completeness(lineage, gt)
    assert got["rho_enum"] == 1.0
    assert got["idempotent"] == {"rho_rev": 1.0, "n": 4, "restored": 4}
    assert got["versioned"] == {"rho_rev": 1.0, "n": 3, "restored": 3}
    assert got["derived"]["rho_rev"] is None
    assert got["derived"]["quarantined"] == 2
    assert got["irreversible"] == {"rho_rev": 0.0, "n": 1, "escalated": 1}


def test_rho_enum_detects_missing_lineage():
    lineage = pd.DataFrame(
        [{"task_id": "t1", "step": 1, "write_class": "idempotent", "is_write": True}]
    )
    gt = pd.DataFrame(
        [
            {"task_id": "t1", "step": 1, "write_class": "idempotent", "attestation_action": "restored", "restored_matches_before": True, "key": "a"},
            {"task_id": "t1", "step": 2, "write_class": "idempotent", "attestation_action": "restored", "restored_matches_before": True, "key": "b"},
        ]
    )
    got = rollback_completeness(lineage, gt)
    assert got["rho_enum"] == 0.5


def test_verification_overhead_relative_to_baseline():
    spans = pd.DataFrame(
        [
            {"name": "verify", "duration_ms": 40, "mode": "full"},
            {"name": "tool.call", "duration_ms": 100, "mode": "full"},
        ]
    )
    baseline = pd.DataFrame(
        [
            {"name": "verify", "duration_ms": 10, "mode": "flat"},
            {"name": "tool.call", "duration_ms": 90, "mode": "flat"},
        ]
    )
    got = verification_overhead(spans, baseline)
    assert got["verify_ms"] == 40
    assert got["absolute_seconds"] == pytest.approx(0.03)
    assert got["relative"] == pytest.approx(0.4)  # (140-100)/100
