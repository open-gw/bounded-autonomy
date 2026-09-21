"""Schema tests. Known-good manifests pass; missing/out-of-range/write-mix fail."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from validate_manifest import extra_errors, load_inventory, validate_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "runs" / "manifests"
RESULT_SCHEMA = json.loads((ROOT / "schemas" / "result.schema.json").read_text())


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((MANIFESTS / name).read_text())


def test_example_manifests_validate():
    for name in ("long-multistep-flat.yaml", "long-multistep-full.yaml"):
        errors = validate_manifest(MANIFESTS / name)
        assert errors == [], errors


def test_write_mix_must_sum_to_one():
    doc = _load_yaml("long-multistep-full.yaml")
    doc["spec"]["write_mix"]["idempotent"] = 0.5
    errors = extra_errors(doc, load_inventory())
    assert any("write_mix sums" in e for e in errors)


def test_write_mix_one_is_accepted():
    doc = _load_yaml("long-multistep-full.yaml")
    errors = extra_errors(doc, load_inventory())
    assert errors == []


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
            "credential_ratio": 1.0,
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
