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
try:
    from weights import load_weights, reachable_weight as _rw
except ImportError:
    from rig.weights import load_weights, reachable_weight as _rw


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def _epochs(svid: pd.DataFrame, spans: pd.DataFrame) -> dict[str, float | None]:
    issued = not_after = t0 = t1 = None
    if not svid.empty and "issued_at_epoch" in svid.columns:
        issued = float(pd.to_numeric(svid["issued_at_epoch"], errors="coerce").max())
        not_after = float(pd.to_numeric(svid["not_after_epoch"], errors="coerce").max())
    if not spans.empty:
        runs = spans[spans.get("name", pd.Series(dtype=str)) == "run"] if "name" in spans.columns else pd.DataFrame()
        if not runs.empty and "start_epoch" in runs.columns:
            t0 = float(pd.to_numeric(runs["start_epoch"], errors="coerce").min())
            t1 = float(pd.to_numeric(runs["end_epoch"], errors="coerce").max())
    tau = None if issued is None or not_after is None else not_after - issued
    t_sec = None if t0 is None or t1 is None else t1 - t0
    return {
        "tau_seconds": tau,
        "T_seconds": t_sec,
        "tau_issued_epoch": issued,
        "tau_not_after_epoch": not_after,
        "T_start_epoch": t0,
        "T_end_epoch": t1,
    }


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
    overhead_out = {
        "absolute_seconds": overhead["absolute_seconds"],
        "relative": overhead["relative"],
        "verify_ms": overhead["verify_ms"],
        "total_ms": overhead["total_ms"],
    }
    ratio = credential_ratio(svid, spans)
    if ratio != ratio:  # NaN
        ratio = None
    epochs = _epochs(svid, spans)
    step_ratios = [float(x) for x in (meta.get("step_ratios") or [])]
    d_ms = [float(x) for x in (meta.get("policy_propagation_ms") or [])]
    weight = meta.get("reachable_weight")
    if weight is None:
        weight = _rw(reached, load_weights())

    return {
        "schema_version": "1.0.0",
        "run_id": meta["run_id"],
        "profile": meta.get("profile", "long-multistep"),
        "mode": meta["mode"],
        "seed": meta["seed"],
        "started_at": meta["started_at"],
        "finished_at": meta["finished_at"],
        "wall_clock_seconds": meta["wall_clock_seconds"],
        "source": meta.get("source", "simulator"),
        "declaration": meta["declaration"],
        "steps_completed": meta["steps_completed"],
        "write_counts": meta["write_counts"],
        "metrics": {
            "reachable_set_size": len(reached),
            "reachable_services": reached,
            "reachable_weight": int(weight),
            "credential_ratio": ratio,
            "tau_seconds": epochs["tau_seconds"],
            "T_seconds": epochs["T_seconds"],
            "tau_issued_epoch": epochs["tau_issued_epoch"],
            "tau_not_after_epoch": epochs["tau_not_after_epoch"],
            "T_start_epoch": epochs["T_start_epoch"],
            "T_end_epoch": epochs["T_end_epoch"],
            "rollback_completeness": rb,
            "rho_enum": rho_enum,
            "verification_overhead": overhead_out,
            "segment_p_ms": meta.get("segment_p_ms"),
            "segment_q_ms": meta.get("segment_q_ms"),
            "step_ratio_mean": None if not step_ratios else sum(step_ratios) / len(step_ratios),
            "step_ratio_max": None if not step_ratios else max(step_ratios),
            "d_ms_mean": None if not d_ms else sum(d_ms) / len(d_ms),
            "d_ms_max": None if not d_ms else max(d_ms),
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
