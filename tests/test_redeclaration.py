"""Task 28: legitimate re-declaration and per-step cost split."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonschema import Draft202012Validator, FormatChecker

from agent.orchestrator import UndeclaredTool, pick_tool
from harness.simulator import run_local
from plan import build_step_plan
from profiles import profile_spec
from tables import _is_redeclaration, _is_step_split, _task_results, table_redeclaration, table_step_split
from validate_manifest import extra_errors, extra_errors_result, load_inventory, validate_manifest

ROOT = Path(__file__).resolve().parents[1]
RESULT_SCHEMA = json.loads((ROOT / "schemas" / "result.schema.json").read_text())


def test_redeclaration_plan_names_docs_at_step_15():
    spec = profile_spec("redeclaration")
    plan = build_step_plan(
        seed=1,
        steps=spec["steps"],
        write_mix=spec["write_mix"],
        declared=spec["declared"],
        redeclare_at=spec["redeclare_at"],
        redeclare_tool=spec["redeclare_tool"],
    )
    assert plan[14].index == 15
    assert plan[14].tool == "docs"
    assert plan[14].tool not in spec["declared"]
    with pytest.raises(UndeclaredTool) as exc:
        pick_tool(plan[14].instruction, list(spec["declared"]), None)
    assert exc.value.tool == "docs"


def test_redeclaration_simulator_records_cost_and_keeps_writes(tmp_path: Path):
    result = run_local(
        mode="full",
        seed=1,
        out_dir=tmp_path / "redecl",
        profile="redeclaration",
        injection=False,
    )
    assert result["profile"] == "redeclaration"
    assert result["steps_completed"] == 30
    assert result["redeclaration_cost_ms"] is not None
    assert result["redeclaration_cost_ms"] >= 0
    assert result["steps_reexecuted"] == 0
    assert result["writes_committed_before_termination"] is True
    assert "docs" in result["declaration"]["services"]
    Draft202012Validator(RESULT_SCHEMA, format_checker=FormatChecker()).validate(result)
    assert extra_errors_result(result) == []


def test_probe_off_reachable_set_from_flows_only(tmp_path: Path):
    result = run_local(
        mode="full",
        seed=1,
        out_dir=tmp_path / "noprobe",
        injection=False,
        probe_enabled=False,
        granularity="step",
        step_split=True,
    )
    assert result["observer"]["probe"] is False
    probe = __import__("pandas").read_parquet(tmp_path / "noprobe" / "probe.parquet")
    assert probe.empty or not bool(probe["success"].any()) if "success" in probe.columns else True
    assert result["metrics"]["reachable_set_size"] >= 1
    split = result["step_cost_split"]
    assert split["probe_enabled"] is False
    assert split["totals"]["probe_ms"] == 0.0
    assert split["reconcile_error_pct"] <= 5.0
    Draft202012Validator(RESULT_SCHEMA, format_checker=FormatChecker()).validate(result)


def test_step_split_probe_on_has_probe_time(tmp_path: Path):
    result = run_local(
        mode="full",
        seed=2,
        out_dir=tmp_path / "split",
        injection=False,
        probe_enabled=True,
        granularity="step",
        step_split=True,
    )
    split = result["step_cost_split"]
    assert split["probe_enabled"] is True
    assert split["totals"]["probe_ms"] > 0
    assert split["totals"]["svid_reissue_ms"] > 0
    assert split["totals"]["propagation_ms"] > 0
    accounted = (
        split["totals"]["propagation_ms"]
        + split["totals"]["svid_reissue_ms"]
        + split["totals"]["probe_ms"]
        + split["totals"]["other_ms"]
    )
    assert abs(accounted - split["totals"]["boundary_ms"]) / split["totals"]["boundary_ms"] * 100 <= 5.0
    Draft202012Validator(RESULT_SCHEMA, format_checker=FormatChecker()).validate(result)


def test_paper1_tables_ignore_redeclaration_and_step_split():
    rows = [
        {
            "profile": "long-multistep",
            "declaration": {"granularity": "task"},
            "run_id": "long-multistep-full-seed1",
        },
        {
            "profile": "redeclaration",
            "declaration": {"granularity": "task"},
            "run_id": "redeclaration-full-seed1",
            "redeclaration_cost_ms": 120.0,
            "steps_reexecuted": 0,
            "writes_committed_before_termination": True,
            "source": "cluster",
            "seed": 1,
        },
        {
            "profile": "long-multistep",
            "declaration": {"granularity": "step"},
            "run_id": "long-multistep-full-step-split-seed1",
            "step_cost_split": {
                "probe_enabled": True,
                "boundaries": [],
                "totals": {
                    "propagation_ms": 10,
                    "svid_reissue_ms": 8,
                    "probe_ms": 20,
                    "other_ms": 2,
                    "boundary_ms": 40,
                },
                "reconcile_error_pct": 0.0,
            },
            "observer": {"probe": True},
            "source": "cluster",
            "seed": 1,
        },
    ]
    task = _task_results(rows)
    assert len(task) == 1
    assert not _is_redeclaration(task[0])
    assert _is_redeclaration(rows[1])
    assert _is_step_split(rows[2])
    md = table_redeclaration(rows)
    assert "120.0" in md
    split_md = table_step_split(rows)
    assert "propagation" in split_md


def test_redeclaration_manifest_requires_injection_off():
    errors = validate_manifest(ROOT / "runs" / "manifests" / "redeclaration-full.yaml")
    assert errors == []
    import yaml

    doc = yaml.safe_load((ROOT / "runs" / "manifests" / "redeclaration-full.yaml").read_text())
    doc["spec"]["injection"]["enabled"] = True
    assert any("injection.enabled" in e for e in extra_errors(doc, load_inventory()))
