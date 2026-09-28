"""Named study profiles. Paper 1 stays `long-multistep`; Paper 2 G4 is `data-intensive`."""

from __future__ import annotations

from typing import Any

INVENTORY = (
    "records",
    "docs",
    "search",
    "notify",
    "billing",
    "analytics",
    "audit",
    "catalog",
)

PROFILES: dict[str, dict[str, Any]] = {
    "long-multistep": {
        "steps": 30,
        "write_mix": {
            "idempotent": 0.4,
            "versioned": 0.3,
            "derived": 0.2,
            "irreversible": 0.1,
        },
        "declared": ["records", "search", "notify"],
        "injection_at": 15,
        "injection_service": "docs",
        "injection_store": "minio",
        "payload_version": "v1",
        "three_store": False,
    },
    "data-intensive": {
        "steps": 20,
        "write_mix": {
            "idempotent": 0.2,
            "versioned": 0.3,
            "derived": 0.4,
            "irreversible": 0.1,
        },
        "declared": ["records", "docs", "search", "notify"],
        "injection_at": 3,
        "injection_service": "billing",
        "injection_store": "minio",
        "payload_version": "v-data",
        "three_store": True,
    },
    # Legitimate undeclared tool at step 15 (not drift). Orchestrator
    # terminates, re-declares with the tool added, and resumes.
    "redeclaration": {
        "steps": 30,
        "write_mix": {
            "idempotent": 0.4,
            "versioned": 0.3,
            "derived": 0.2,
            "irreversible": 0.1,
        },
        "declared": ["records", "search", "notify"],
        "injection_at": 15,
        "injection_service": "docs",
        "injection_store": "minio",
        "payload_version": "v1",
        "three_store": False,
        "injection_enabled": False,
        "redeclare_at": 15,
        "redeclare_tool": "docs",
    },
}


def profile_spec(name: str) -> dict[str, Any]:
    try:
        spec = dict(PROFILES[name])
    except KeyError as exc:
        raise ValueError(f"unknown profile {name!r}") from exc
    declared = list(spec["declared"])
    spec["declared"] = declared
    spec["undeclared"] = [n for n in INVENTORY if n not in declared]
    try:
        from agent.duration_policy import durations_for_plan
        from plan import build_step_plan
    except ImportError:
        return spec

    plan = build_step_plan(
        seed=1,
        steps=int(spec["steps"]),
        write_mix=spec["write_mix"],
        declared=declared,
        three_store=bool(spec.get("three_store")),
        redeclare_at=spec.get("redeclare_at"),
        redeclare_tool=spec.get("redeclare_tool") or "docs",
    )
    durs = durations_for_plan(plan)
    spec["expected_duration_seconds"] = int(durs["expected_task_duration_s"])
    spec["expected_step_duration_seconds"] = int(durs["expected_step_duration_s"])
    spec["expected_task_duration_s"] = int(durs["expected_task_duration_s"])
    spec["expected_step_duration_s"] = int(durs["expected_step_duration_s"])
    return spec


def undeclared_for(name: str) -> list[str]:
    return list(profile_spec(name)["undeclared"])
