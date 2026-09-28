"""Declared task/step duration from Task 26 p95s. No 1800 s default."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "rig" / "agent" / "duration_policy.yaml"


def load_policy(path: Path | None = None) -> dict[str, Any]:
    doc = yaml.safe_load((path or POLICY_PATH).read_text())
    if not isinstance(doc, dict):
        raise ValueError("duration_policy.yaml is not a mapping")
    return doc


def step_budget_ms(tool: str, policy: Mapping[str, Any] | None = None) -> float:
    pol = dict(policy or load_policy())
    floor = float(pol["floor_ms"])
    mult = float(pol["p95_multiplier"])
    p95s = pol.get("p95_ms") or {}
    p95 = p95s.get(tool)
    if p95 is None:
        return floor
    return max(floor, float(p95) * mult)


def _ceil_seconds(ms: float) -> int:
    if ms <= 0:
        raise ValueError("duration budget must be positive")
    return int(math.ceil(ms / 1000.0))


def durations_for_plan(
    plan: Sequence[Any],
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-step budgets from the seeded plan; task duration = sum × slack."""
    pol = dict(policy or load_policy())
    slack = float(pol["task_slack"])
    min_ttl = int(pol["spire_min_jwt_ttl_seconds"])
    budgets = [step_budget_ms(getattr(step, "tool"), pol) for step in plan]
    if not budgets:
        raise ValueError("empty step plan; cannot declare a duration")
    task_ms = sum(budgets) * slack
    step_ms = max(budgets)
    task_s = _ceil_seconds(task_ms)
    step_s = _ceil_seconds(step_ms)
    return {
        "step_budget_ms": budgets,
        "expected_task_duration_s": task_s,
        "expected_step_duration_s": step_s,
        "task_budget_ms": task_ms,
        "step_budget_max_ms": step_ms,
        "spire_min_jwt_ttl_seconds": min_ttl,
        "floor_ms": float(pol["floor_ms"]),
        "p95_multiplier": float(pol["p95_multiplier"]),
        "task_slack": slack,
    }


def grant_jwt_ttl_seconds(requested: int, policy: Mapping[str, Any] | None = None) -> int:
    pol = dict(policy or load_policy())
    minimum = int(pol["spire_min_jwt_ttl_seconds"])
    req = int(requested)
    if req <= 0:
        raise ValueError("JWT TTL request must be a positive duration")
    return max(req, minimum)


def requested_jwt_ttl_seconds(*, granularity: str, task_s: int, step_s: int) -> int:
    if granularity == "step":
        return int(step_s)
    return int(task_s)
