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
        "expected_duration_seconds": 1800,
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
        "expected_duration_seconds": 1800,
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
        "expected_duration_seconds": 1800,
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
    return spec


def undeclared_for(name: str) -> list[str]:
    return list(profile_spec(name)["undeclared"])
