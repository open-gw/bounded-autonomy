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
    step_cost_split,
    verification_overhead,
)
try:
    from identity.svid import residual_seconds
except ImportError:
    from rig.identity.svid import residual_seconds
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
    evasion = _read(run_dir / "evasion.parquet")
    gateway = _read(run_dir / "gateway.parquet")

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
    breach = [str(s) for s in (meta.get("breach_services") or [])]
    intersection = sorted(set(breach) & set(reached))
    variant = meta.get("variant") or (meta.get("declaration") or {}).get("variant")
    task_end = meta.get("task_end_epoch")
    if task_end is None:
        task_end = epochs["T_end_epoch"]
    policy_removed = meta.get("policy_removed_at_epoch")
    if (
        meta.get("mode") == "full"
        and policy_removed is None
        and meta.get("segment_q_ms") is not None
        and task_end is not None
    ):
        policy_removed = float(task_end) + float(meta["segment_q_ms"]) / 1000.0
    entry_deleted = meta.get("entry_deleted_at_epoch")
    cred_kind = "sa-token"
    if not svid.empty and "credential_kind" in svid.columns and svid["credential_kind"].notna().any():
        cred_kind = str(svid["credential_kind"].dropna().iloc[0])
    residual: dict[str, float | None] = {
        "residual_svid_seconds": None,
        "residual_policy_seconds": None,
    }
    if meta.get("mode") == "full" and epochs["tau_not_after_epoch"] is not None and task_end is not None:
        residual = residual_seconds(
            exp=float(epochs["tau_not_after_epoch"]),
            task_end=float(task_end),
            policy_removed_at=None if policy_removed is None else float(policy_removed),
        )
    derivation = {
        "formula": "credential_ratio = tau_seconds / T_seconds",
        "tau_definition": "exp - iat (SVID TTL); not issue-to-delete; not registration-entry deletion",
        "tau_seconds": epochs["tau_seconds"],
        "T_seconds": epochs["T_seconds"],
        "credential_kind": cred_kind,
    }

    try:
        from observer.evasion import matrix_from_rows as _evasion_matrix
    except ImportError:
        from rig.observer.evasion import matrix_from_rows as _evasion_matrix

    artefacts = {
        "probe": "probe.parquet",
        "flows": "flows.parquet",
        "spans": "spans.parquet",
        "lineage": "lineage.parquet",
        "groundtruth": "groundtruth.parquet",
        "svid": "svid.parquet",
    }
    evasion_matrix = None
    if not evasion.empty:
        artefacts["evasion"] = "evasion.parquet"
        evasion_matrix = _evasion_matrix(evasion)
    if not gateway.empty or (run_dir / "gateway.parquet").exists():
        artefacts["gateway"] = "gateway.parquet"

    result = {
        "schema_version": "1.0.0",
        "run_id": meta["run_id"],
        "profile": meta.get("profile", "long-multistep"),
        "mode": meta["mode"],
        "seed": meta["seed"],
        **({"variant": variant} if variant else {}),
        **({"gateway_bypass": True} if meta.get("gateway_bypass") else {}),
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
            "credential_ratio_derivation": derivation,
            "tau_seconds": epochs["tau_seconds"],
            "T_seconds": epochs["T_seconds"],
            "tau_issued_epoch": epochs["tau_issued_epoch"],
            "tau_not_after_epoch": epochs["tau_not_after_epoch"],
            "T_start_epoch": epochs["T_start_epoch"],
            "T_end_epoch": epochs["T_end_epoch"],
            "residual_svid_seconds": residual["residual_svid_seconds"],
            "residual_policy_seconds": residual["residual_policy_seconds"],
            "entry_deleted_at_epoch": None if entry_deleted is None else float(entry_deleted),
            "policy_removed_at_epoch": None if policy_removed is None else float(policy_removed),
            "task_end_epoch": None if task_end is None else float(task_end),
            "credential_kind": cred_kind,
            "rollback_completeness": rb,
            "rho_enum": rho_enum,
            "verification_overhead": overhead_out,
            "segment_p_ms": meta.get("segment_p_ms"),
            "segment_q_ms": meta.get("segment_q_ms"),
            "step_ratio_mean": None if not step_ratios else sum(step_ratios) / len(step_ratios),
            "step_ratio_max": None if not step_ratios else max(step_ratios),
            "d_ms_mean": None if not d_ms else sum(d_ms) / len(d_ms),
            "d_ms_max": None if not d_ms else max(d_ms),
            **(
                {
                    "breach_services": breach,
                    "breach_intersection": intersection,
                    "breach_intersection_size": len(intersection),
                }
                if breach or variant or meta.get("mode") in ("gateway-only", "gateway-bypass") or meta.get("gateway_bypass")
                else {}
            ),
        },
        "policy_propagation_ms": meta.get("policy_propagation_ms", []),
        "artefacts": artefacts,
    }
    if evasion_matrix:
        result["evasion_matrix"] = evasion_matrix
    if meta.get("redeclaration_cost_ms") is not None:
        result["redeclaration_cost_ms"] = float(meta["redeclaration_cost_ms"])
        result["steps_reexecuted"] = int(meta.get("steps_reexecuted") or 0)
        committed = meta.get("writes_committed_before_termination")
        if committed is not None:
            result["writes_committed_before_termination"] = bool(committed)
    probe_flag = meta.get("probe_enabled")
    if probe_flag is False:
        result["observer"] = {"probe": False}
    elif probe_flag is True and (meta.get("step_boundaries") or meta.get("step_split")):
        result["observer"] = {"probe": True}
    boundaries = list(meta.get("step_boundaries") or [])
    if boundaries or meta.get("step_split"):
        result["step_cost_split"] = step_cost_split(
            boundaries, probe_enabled=bool(probe_flag if probe_flag is not None else True)
        )
    return result


def dumps(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2) + "\n"
