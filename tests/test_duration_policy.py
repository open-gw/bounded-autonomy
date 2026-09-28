"""Task 31 duration policy: Task 26 p95s, no 1800 s default."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent.duration_policy import (
    durations_for_plan,
    grant_jwt_ttl_seconds,
    load_policy,
    requested_jwt_ttl_seconds,
    step_budget_ms,
)
from plan import build_step_plan
from profiles import profile_spec

ROOT = Path(__file__).resolve().parents[1]


def test_policy_yaml_records_task26_p95s():
    pol = load_policy()
    assert pol["floor_ms"] == 500
    assert pol["p95_multiplier"] == 3.0
    assert pol["task_slack"] == 1.5
    assert pol["spire_min_jwt_ttl_seconds"] == 1
    assert pol["source"]["campaign"] == "task26"
    p95 = pol["p95_ms"]
    assert p95["records"] == pytest.approx(0.1997494)
    assert p95["search"] == pytest.approx(0.2233414)
    assert p95["notify"] == pytest.approx(0.98716235)
    raw = yaml.safe_load((ROOT / "rig" / "agent" / "duration_policy.yaml").read_text())
    assert raw["p95_ms"]["records"] == p95["records"]


def test_step_budget_floors_at_500ms():
    pol = load_policy()
    for tool in ("records", "search", "notify"):
        assert step_budget_ms(tool, pol) == 500.0
    assert step_budget_ms("docs", pol) == 500.0


def test_long_multistep_task_duration_from_plan():
    plan = build_step_plan(1)
    durs = durations_for_plan(plan)
    assert durs["expected_step_duration_s"] == 1
    assert durs["expected_task_duration_s"] == 23
    spec = profile_spec("long-multistep")
    assert spec["expected_duration_seconds"] == 23
    assert spec["expected_step_duration_seconds"] == 1
    assert spec.get("expected_duration_seconds") != 1800


def test_grant_rounds_up_to_spire_min():
    assert grant_jwt_ttl_seconds(1) == 1
    assert grant_jwt_ttl_seconds(23) == 23
    with pytest.raises(ValueError):
        grant_jwt_ttl_seconds(0)
    assert requested_jwt_ttl_seconds(granularity="task", task_s=23, step_s=1) == 23
    assert requested_jwt_ttl_seconds(granularity="step", task_s=23, step_s=1) == 1
