"""Rig unit tests: plan mix, CNP shape, lineage facet, local run acceptance."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from controller.cnp import TASK_LABEL, render_cnp, render_spire_entry, spiffe_for
from harness.simulator import run_local
from lineage.emitter import emit_run_event, spiffe_task_id
from plan import WRITE_CLASSES, build_step_plan, counts_from_mix


def test_step_plan_mix_is_12_9_6_3():
    mix = {"idempotent": 0.4, "versioned": 0.3, "derived": 0.2, "irreversible": 0.1}
    assert counts_from_mix(mix, 30) == {
        "idempotent": 12,
        "versioned": 9,
        "derived": 6,
        "irreversible": 3,
    }
    for seed in range(1, 6):
        plan = build_step_plan(seed)
        assert len(plan) == 30
        counts = Counter(s.write_class for s in plan)
        assert counts["idempotent"] == 12
        assert counts["versioned"] == 9
        assert counts["derived"] == 6
        assert counts["irreversible"] == 3
        assert {s.tool for s in plan} <= {"records", "search", "notify"}


def test_cnp_allows_only_declared_services():
    spec = {
        "taskId": "t1",
        "expectedDurationSeconds": 60,
        "services": [{"name": "records"}, {"name": "search"}, {"name": "notify"}],
    }
    rendered = render_cnp("decl-t1", "rig", spec)
    egress = rendered["egress"]
    assert egress["spec"]["endpointSelector"]["matchLabels"][TASK_LABEL] == "t1"
    dests = []
    for rule in egress["spec"]["egress"]:
        assert "authentication" not in rule
        endpoints = rule.get("toEndpoints") or []
        if not endpoints:
            continue
        labels = endpoints[0]["matchLabels"]
        if "app.kubernetes.io/name" in labels:
            dests.append(labels["app.kubernetes.io/name"])
    assert dests[:3] == ["records", "search", "notify"]
    assert "otel-collector" in dests
    ports = [
        rule["toPorts"][0]["ports"][0]["port"]
        for rule in egress["spec"]["egress"]
        if rule.get("toEndpoints")
        and rule["toEndpoints"][0]["matchLabels"].get("app.kubernetes.io/name") in {"records", "search", "notify"}
    ]
    assert ports == ["8081", "8083", "8084"]
    assert len(rendered["ingress"]) == 3
    for ingress in rendered["ingress"]:
        assert ingress["spec"]["enableDefaultDeny"] == {"ingress": True}
        selectors = [
            ep["matchLabels"]
            for rule in ingress["spec"]["ingress"]
            for ep in rule["fromEndpoints"]
        ]
        assert all(sel.get(TASK_LABEL) == "t1" for sel in selectors)
        for rule in ingress["spec"]["ingress"]:
            assert "authentication" not in rule
    entry = render_spire_entry(spec, "spiffe://rig/spire/agent")
    assert entry["spiffe_id"] == spiffe_for("t1")
    assert entry["x509_svid_ttl"] == 60


def test_task_facet_from_svid_not_header():
    event = emit_run_event(
        spiffe_id="spiffe://rig/task/abc",
        step=3,
        store="postgres",
        operation="insert",
        is_write=True,
        dataset="postgres.k",
    )
    facet = event["run"]["facets"]["task"]
    assert facet["task_id"] == "abc"
    assert facet["step"] == 3
    assert facet["write_class"] == "versioned"
    with pytest.raises(ValueError):
        spiffe_task_id("spiffe://evil/task/abc")


def test_local_full_clean_run(tmp_path: Path):
    result = run_local(
        mode="full", seed=1, out_dir=tmp_path / "full", injection=False
    )
    assert result["steps_completed"] == 30
    assert result["metrics"]["reachable_set_size"] == 3
    assert set(result["metrics"]["reachable_services"]) == {
        "records",
        "search",
        "notify",
    }
    counts = result["write_counts"]
    assert abs(counts["idempotent"] - 12) <= 1
    assert abs(counts["versioned"] - 9) <= 1
    assert abs(counts["derived"] - 6) <= 1
    assert abs(counts["irreversible"] - 3) <= 1
    rb = result["metrics"]["rollback_completeness"]
    assert rb["idempotent"]["rho_rev"] == 1.0
    assert rb["versioned"]["rho_rev"] == 1.0
    assert rb["derived"]["quarantined"] == rb["derived"]["n"]
    assert rb["irreversible"]["escalated"] == rb["irreversible"]["n"]
    for name in (
        "probe.parquet",
        "flows.parquet",
        "spans.parquet",
        "lineage.parquet",
        "groundtruth.parquet",
        "svid.parquet",
        "result.json",
    ):
        assert (tmp_path / "full" / name).exists()


def test_local_flat_vs_full_reachable(tmp_path: Path):
    full = run_local(mode="full", seed=2, out_dir=tmp_path / "full", injection=False)
    flat = run_local(mode="flat", seed=2, out_dir=tmp_path / "flat", injection=False)
    assert full["metrics"]["reachable_set_size"] == 3
    assert flat["metrics"]["reachable_set_size"] == 8


def test_drift_full_refuses_undeclared(tmp_path: Path):
    result = run_local(mode="full", seed=1, out_dir=tmp_path / "d", injection=True)
    assert "docs" not in result["metrics"]["reachable_services"]
    attest = (tmp_path / "d" / "attestation.json").read_text()
    assert "escalated" in attest


def test_rho_enum_detects_disabled_emitter(tmp_path: Path):
    result = run_local(
        mode="full",
        seed=1,
        out_dir=tmp_path / "short",
        injection=False,
        lineage_disabled_for="notify",
    )
    assert result["metrics"]["rho_enum"] is not None
    assert result["metrics"]["rho_enum"] < 1.0


def test_result_schema_on_local_run(tmp_path: Path):
    import json
    from pathlib import Path as P

    root = P(__file__).resolve().parents[1]
    schema = json.loads((root / "schemas" / "result.schema.json").read_text())
    result = run_local(mode="full", seed=3, out_dir=tmp_path / "s", injection=False)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
