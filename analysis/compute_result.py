"""Build result.json from the six artefacts. Study-design §5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from metrics import (
    credential_ratio,
    reachable_set,
    rollback_completeness,
    verification_overhead,
)


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def compute_result(
    run_dir: Path | str,
    meta: dict[str, Any],
    baseline_spans: pd.DataFrame | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    probe = _read(run_dir / "probe.parquet")
    flows = _read(run_dir / "flows.parquet")
    spans = _read(run_dir / "spans.parquet")
    lineage = _read(run_dir / "lineage.parquet")
    groundtruth = _read(run_dir / "groundtruth.parquet")
    svid = _read(run_dir / "svid.parquet")

    reached = sorted(reachable_set(flows, probe))
    rb = rollback_completeness(lineage, groundtruth)
    rho_enum = rb.pop("rho_enum")
    baseline = baseline_spans if baseline_spans is not None else pd.DataFrame()
    overhead = verification_overhead(spans, baseline)
    # Drop helper keys not in the result schema.
    overhead_out = {
        "absolute_seconds": overhead["absolute_seconds"],
        "relative": overhead["relative"],
        "verify_ms": overhead["verify_ms"],
        "total_ms": overhead["total_ms"],
    }
    ratio = credential_ratio(svid, spans)
    if ratio != ratio:  # NaN
        ratio = None

    return {
        "schema_version": "1.0.0",
        "run_id": meta["run_id"],
        "profile": meta.get("profile", "long-multistep"),
        "mode": meta["mode"],
        "seed": meta["seed"],
        "started_at": meta["started_at"],
        "finished_at": meta["finished_at"],
        "wall_clock_seconds": meta["wall_clock_seconds"],
        "declaration": meta["declaration"],
        "steps_completed": meta["steps_completed"],
        "write_counts": meta["write_counts"],
        "metrics": {
            "reachable_set_size": len(reached),
            "reachable_services": reached,
            "credential_ratio": ratio,
            "rollback_completeness": rb,
            "rho_enum": rho_enum,
            "verification_overhead": overhead_out,
        },
        "policy_propagation_ms": meta.get("policy_propagation_ms", []),
        "artefacts": {
            "probe": "probe.parquet",
            "flows": "flows.parquet",
            "spans": "spans.parquet",
            "lineage": "lineage.parquet",
            "groundtruth": "groundtruth.parquet",
            "svid": "svid.parquet",
        },
    }


def dumps(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2) + "\n"
