"""Synthetic ten-run fixture set. Correct answers known by construction.

full: |S|=3, rho_rev=1.0 for idempotent/versioned, derived quarantined, irreversible escalated
flat: |S|=8, same rollback numbers (procedure is independent of the segment), lower verify_ms
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "fixtures" / "results"
DECLARED = ["records", "search", "notify"]
ALL = [
    "records",
    "docs",
    "search",
    "notify",
    "billing",
    "analytics",
    "audit",
    "catalog",
]


def _result(mode: str, seed: int) -> dict:
    start = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=seed)
    wall = 240.0 + seed * 3 + (18.0 if mode == "full" else 0.0)
    verify_ms = 40.0 + seed * 2 if mode == "flat" else 160.0 + seed * 4
    total_ms = 3000.0 + seed * 50 if mode == "flat" else 3300.0 + seed * 50
    relative = None if mode == "flat" else (total_ms - (3000.0 + seed * 50)) / (3000.0 + seed * 50)
    reachable = ALL if mode == "flat" else list(DECLARED)
    t0 = 1_747_440_000.0 + seed * 60
    tau = 86_400.0 if mode == "flat" else wall
    t1 = t0 + wall
    run_id = f"long-multistep-{mode}-seed{seed}"
    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "profile": "long-multistep",
        "mode": mode,
        "seed": seed,
        "started_at": start.isoformat().replace("+00:00", "Z"),
        "finished_at": (start + timedelta(seconds=wall)).isoformat().replace("+00:00", "Z"),
        "wall_clock_seconds": wall,
        "declaration": {
            "task_id": f"task-seed{seed}",
            "spiffe_id": f"spiffe://rig/task/task-seed{seed}",
            "services": list(DECLARED),
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
            "reachable_set_size": len(reachable),
            "reachable_services": reachable,
            "reachable_weight": 14 if mode == "flat" else 7,
            "credential_ratio": tau / wall,
            "tau_seconds": tau,
            "T_seconds": wall,
            "tau_issued_epoch": t0,
            "tau_not_after_epoch": t0 + tau,
            "T_start_epoch": t0,
            "T_end_epoch": t1,
            "rollback_completeness": {
                "idempotent": {"rho_rev": 1.0, "n": 12, "restored": 12},
                "versioned": {"rho_rev": 1.0, "n": 9, "restored": 9},
                "derived": {"rho_rev": None, "n": 6, "quarantined": 6},
                "irreversible": {"rho_rev": 0.0, "n": 3, "escalated": 3},
            },
            "rho_enum": 1.0,
            "verification_overhead": {
                "absolute_seconds": 0.0 if mode == "flat" else (verify_ms - (40.0 + seed * 2)) / 1000.0,
                "relative": 0.0 if mode == "flat" else relative,
                "verify_ms": verify_ms,
                "total_ms": total_ms,
            },
            "segment_p_ms": 0.0 if mode == "flat" else 10.0 + seed,
            "segment_q_ms": 0.0 if mode == "flat" else 5.0 + seed,
            "step_ratio_mean": None,
            "step_ratio_max": None,
            "d_ms_mean": None if mode == "flat" else 10.0 + seed,
            "d_ms_max": None if mode == "flat" else 12.0 + seed,
        },
        "policy_propagation_ms": [] if mode == "flat" else [10.0 + seed, 12.0 + seed],
        "source": "simulator",
        "artefacts": {
            "probe": "probe.parquet",
            "flows": "flows.parquet",
            "spans": "spans.parquet",
            "lineage": "lineage.parquet",
            "groundtruth": "groundtruth.parquet",
            "svid": "svid.parquet",
        },
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for mode in ("flat", "full"):
        for seed in range(1, 6):
            doc = _result(mode, seed)
            dest = OUT / doc["run_id"]
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "result.json").write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote 10 result.json files under {OUT}")


if __name__ == "__main__":
    main()
