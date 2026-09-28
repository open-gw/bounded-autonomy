"""Schema tests. Known-good manifests pass; missing/out-of-range/write-mix fail."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from validate_manifest import extra_errors, extra_errors_result, load_inventory, validate_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "runs" / "manifests"
RESULT_SCHEMA = json.loads((ROOT / "schemas" / "result.schema.json").read_text())


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((MANIFESTS / name).read_text())


def test_example_manifests_validate():
    for name in (
        "long-multistep-flat.yaml",
        "long-multistep-full.yaml",
        "long-multistep-full-step.yaml",
        "long-multistep-k1-full.yaml",
        "long-multistep-k3-full.yaml",
        "long-multistep-k5-full.yaml",
        "long-multistep-k7-full.yaml",
        "data-intensive-full.yaml",
        "long-multistep-gateway-only.yaml",
        "long-multistep-gateway-bypass.yaml",
        "long-multistep-full-bypass.yaml",
        "redeclaration-full.yaml",
        "long-multistep-full-step-noprobe.yaml",
        "long-multistep-full-step-split.yaml",
    ):
        path = MANIFESTS / name
        if not path.exists():
            continue
        errors = validate_manifest(path)
        assert errors == [], errors


def test_declared_count_must_match_declared_len():
    doc = _load_yaml("long-multistep-k1-full.yaml")
    doc["spec"]["services"]["declared_count"] = 3
    errors = extra_errors(doc, load_inventory())
    assert any("declared_count" in e for e in errors)


def test_variant_must_match_frozen_declared_list():
    doc = _load_yaml("long-multistep-k5-full.yaml")
    doc["spec"]["services"]["declared"] = ["records", "search", "notify", "billing", "catalog"]
    doc["spec"]["services"]["undeclared"] = ["docs", "analytics", "audit"]
    errors = extra_errors(doc, load_inventory())
    assert any("variant k5" in e for e in errors)


def test_write_mix_must_sum_to_one():
    doc = _load_yaml("long-multistep-full.yaml")
    doc["spec"]["write_mix"]["idempotent"] = 0.5
    errors = extra_errors(doc, load_inventory())
    assert any("write_mix sums" in e for e in errors)


def test_write_mix_one_is_accepted():
    doc = _load_yaml("long-multistep-full.yaml")
    errors = extra_errors(doc, load_inventory())
    assert errors == []


def test_missing_expected_duration_fails_extra_schema():
    doc = _load_yaml("long-multistep-full.yaml")
    doc["spec"]["expected_duration_seconds"] = 0
    errors = extra_errors(doc, load_inventory())
    assert any("expected_duration_seconds" in e for e in errors)


def test_missing_field_fails():
    doc = _load_yaml("long-multistep-full.yaml")
    del doc["spec"]["seed"]
    validator = Draft202012Validator(
        json.loads((ROOT / "schemas" / "manifest.schema.json").read_text())
    )
    messages = [e.message for e in validator.iter_errors(doc)]
    assert any("seed" in m for m in messages)


def test_out_of_range_seed_fails():
    doc = _load_yaml("long-multistep-full.yaml")
    doc["spec"]["seed"] = -1
    validator = Draft202012Validator(
        json.loads((ROOT / "schemas" / "manifest.schema.json").read_text())
    )
    messages = [e.message for e in validator.iter_errors(doc)]
    assert messages


def test_declared_undeclared_must_cover_inventory():
    doc = _load_yaml("long-multistep-full.yaml")
    doc["spec"]["services"]["undeclared"] = ["docs", "billing", "analytics", "audit", "ghost"]
    errors = extra_errors(doc, load_inventory())
    assert any("inventory" in e for e in errors)


def test_injection_target_must_be_undeclared():
    doc = _load_yaml("long-multistep-full.yaml")
    doc["spec"]["injection"]["undeclared_service"] = "records"
    errors = extra_errors(doc, load_inventory())
    assert any("undeclared_service" in e for e in errors)


def _result_template() -> dict:
    return {
        "schema_version": "1.0.0",
        "run_id": "long-multistep-full-seed1",
        "profile": "long-multistep",
        "mode": "full",
        "seed": 1,
        "source": "simulator",
        "started_at": "2026-09-21T12:00:00Z",
        "finished_at": "2026-09-21T12:05:00Z",
        "wall_clock_seconds": 300.0,
        "declaration": {
            "task_id": "task-1",
            "spiffe_id": "spiffe://rig/task/task-1",
            "services": ["records", "search", "notify"],
            "expected_duration_seconds": 1800,
            "granularity": "task",
        },
        "steps_completed": 30,
        "write_counts": {
            "idempotent": 12,
            "versioned": 9,
            "derived": 6,
            "irreversible": 3,
        },
        "metrics": {
            "reachable_set_size": 3,
            "reachable_services": ["notify", "records", "search"],
            "reachable_weight": 7,
            "credential_ratio": 150.0,
            "credential_ratio_derivation": {
                "formula": "credential_ratio = tau_seconds / T_seconds",
                "tau_definition": "exp - iat (SVID TTL); not issue-to-delete; not registration-entry deletion",
                "tau_seconds": 1800.0,
                "T_seconds": 12.0,
                "credential_kind": "jwt-svid",
            },
            "tau_seconds": 1800.0,
            "T_seconds": 12.0,
            "tau_issued_epoch": 1000.0,
            "tau_not_after_epoch": 2800.0,
            "T_start_epoch": 1000.0,
            "T_end_epoch": 1012.0,
            "residual_svid_seconds": 1788.0,
            "residual_policy_seconds": 0.363,
            "entry_deleted_at_epoch": 1012.0,
            "policy_removed_at_epoch": 1012.363,
            "task_end_epoch": 1012.0,
            "credential_kind": "jwt-svid",
            "rollback_completeness": {
                "idempotent": {"rho_rev": 1.0, "n": 12, "restored": 12},
                "versioned": {"rho_rev": 1.0, "n": 9, "restored": 9},
                "derived": {"rho_rev": None, "n": 6, "quarantined": 6},
                "irreversible": {"rho_rev": 0.0, "n": 3, "escalated": 3},
            },
            "rho_enum": 1.0,
            "verification_overhead": {
                "absolute_seconds": 0.12,
                "relative": 0.04,
                "verify_ms": 180.0,
                "total_ms": 4200.0,
            },
            "segment_p_ms": 12.0,
            "segment_q_ms": 4.0,
            "step_ratio_mean": None,
            "step_ratio_max": None,
            "d_ms_mean": 12.0,
            "d_ms_max": 18.0,
        },
        "policy_propagation_ms": [12.0, 18.0],
        "artefacts": {
            "probe": "probe.parquet",
            "flows": "flows.parquet",
            "spans": "spans.parquet",
            "lineage": "lineage.parquet",
            "groundtruth": "groundtruth.parquet",
            "svid": "svid.parquet",
        },
    }


def test_gateway_bypass_not_combinable_with_flat():
    doc = _load_yaml("long-multistep-flat.yaml")
    doc["spec"]["gateway_bypass"] = True
    errors = extra_errors(doc, load_inventory())
    assert any("gateway_bypass" in e for e in errors)


def test_result_template_validates():
    validator = Draft202012Validator(RESULT_SCHEMA, format_checker=FormatChecker())
    validator.validate(_result_template())


def test_result_missing_metric_fails():
    doc = _result_template()
    del doc["metrics"]["rho_enum"]
    validator = Draft202012Validator(RESULT_SCHEMA)
    assert list(validator.iter_errors(doc))


def test_result_bad_spiffe_fails():
    doc = _result_template()
    doc["declaration"]["spiffe_id"] = "not-a-spiffe"
    validator = Draft202012Validator(RESULT_SCHEMA)
    assert list(validator.iter_errors(doc))


def _evasion_matrix() -> list[dict]:
    probes = [
        "direct_ip_declared",
        "direct_ip_undeclared",
        "dns",
        "external_https",
        "node_metadata",
        "kubernetes_api",
        "kubelet",
    ]
    verdicts = ["allowed", "refused", "refused", "refused", "refused", "refused", "refused"]
    return [
        {
            "row": i + 1,
            "probe": probes[i],
            "target": f"t{i}",
            "verdict": verdicts[i],
            "latency_ms": 1.5,
            "detail": "",
        }
        for i in range(7)
    ]


def test_result_with_evasion_matrix_validates():
    doc = _result_template()
    doc["evasion_matrix"] = _evasion_matrix()
    doc["artefacts"]["evasion"] = "evasion.parquet"
    validator = Draft202012Validator(RESULT_SCHEMA, format_checker=FormatChecker())
    validator.validate(doc)
    assert extra_errors_result(doc) == []


def test_evasion_matrix_wrong_length_fails_extra_schema():
    doc = _result_template()
    doc["evasion_matrix"] = _evasion_matrix()[:3]
    doc["artefacts"]["evasion"] = "evasion.parquet"
    errors = extra_errors_result(doc)
    assert any("length" in e or "1–7" in e or "1-7" in e for e in errors)


def test_evasion_bad_verdict_fails_schema():
    doc = _result_template()
    matrix = _evasion_matrix()
    matrix[0]["verdict"] = "dropped"
    doc["evasion_matrix"] = matrix
    doc["artefacts"]["evasion"] = "evasion.parquet"
    validator = Draft202012Validator(RESULT_SCHEMA)
    assert list(validator.iter_errors(doc))
