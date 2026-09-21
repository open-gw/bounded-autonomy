"""Pure metric functions over Parquet/JSON inputs. Study-design §4.

No cluster access. Callers pass pandas DataFrames (or DataFrame-like objects
with the documented columns).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd

WRITE_CLASSES = ("idempotent", "versioned", "derived", "irreversible")
FORWARDED = "FORWARDED"
VERIFY_SPAN = "verify"


def _frame(obj: pd.DataFrame | Iterable[Mapping[str, Any]], columns: list[str]) -> pd.DataFrame:
    if isinstance(obj, pd.DataFrame):
        df = obj.copy()
    else:
        df = pd.DataFrame(list(obj))
    for col in columns:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
    return df


def reachable_set(
    flows: pd.DataFrame | Iterable[Mapping[str, Any]],
    probe: pd.DataFrame | Iterable[Mapping[str, Any]],
) -> set[str]:
    """Services the task identity actually touched.

    A service is reachable if any probe row has success=True or any Hubble
    flow to it has verdict FORWARDED.
    """
    probe_df = _frame(probe, ["step", "service", "success"])
    flows_df = _frame(flows, ["source_spiffe", "destination_service", "verdict"])

    from_probe = set()
    if not probe_df.empty:
        ok = probe_df["success"].astype(bool)
        from_probe = set(probe_df.loc[ok, "service"].dropna().astype(str))

    from_flows = set()
    if not flows_df.empty:
        fwd = flows_df["verdict"].astype(str).str.upper() == FORWARDED
        from_flows = set(
            flows_df.loc[fwd, "destination_service"].dropna().astype(str)
        )
    return from_probe | from_flows


def credential_ratio(
    svid_records: pd.DataFrame | Iterable[Mapping[str, Any]],
    spans: pd.DataFrame | Iterable[Mapping[str, Any]],
) -> float:
    """τ / T. τ is credential lifetime, T is the OTel root-span duration.

    Epoch columns issued_at_epoch / not_after_epoch and a span named `run`
    with start_epoch / end_epoch are preferred. Falls back to unique
    SPIFFE IDs over unique task IDs when those columns are absent.
    """
    svid_df = _frame(
        svid_records,
        [
            "task_id",
            "spiffe_id",
            "issued_at",
            "not_after",
            "issued_at_epoch",
            "not_after_epoch",
        ],
    )
    spans_df = _frame(spans, ["task_id", "name", "start_epoch", "end_epoch", "duration_ms"])
    tau = None
    if not svid_df.empty and svid_df["issued_at_epoch"].notna().any():
        issued = pd.to_numeric(svid_df["issued_at_epoch"], errors="coerce")
        ended = pd.to_numeric(svid_df["not_after_epoch"], errors="coerce")
        tau = float((ended - issued).max())
    t_seconds = None
    if not spans_df.empty:
        runs = spans_df[spans_df["name"] == "run"]
        if not runs.empty and "start_epoch" in runs.columns and runs["start_epoch"].notna().any():
            t_seconds = float(
                pd.to_numeric(runs["end_epoch"], errors="coerce").max()
                - pd.to_numeric(runs["start_epoch"], errors="coerce").min()
            )
        elif not runs.empty:
            t_seconds = float(pd.to_numeric(runs["duration_ms"], errors="coerce").fillna(0).sum()) / 1000.0
    if tau is not None and t_seconds is not None and t_seconds > 0:
        return tau / t_seconds
    n_svids = svid_df["spiffe_id"].dropna().nunique() if not svid_df.empty else 0
    n_tasks = spans_df["task_id"].dropna().nunique() if not spans_df.empty else 0
    if n_tasks == 0:
        return float("nan")
    return float(n_svids) / float(n_tasks)


def verify_duration_variance(spans: pd.DataFrame | Iterable[Mapping[str, Any]]) -> float:
    spans_df = _frame(spans, ["name", "duration_ms"])
    verify = spans_df[spans_df["name"] == VERIFY_SPAN]
    if verify.empty:
        return 0.0
    return float(pd.to_numeric(verify["duration_ms"], errors="coerce").nunique())



def _match_key(row: Mapping[str, Any]) -> tuple:
    return (
        str(row.get("task_id", "")),
        str(row.get("store", "")),
        str(row.get("key", "")),
        str(row.get("step", "")),
    )


def rollback_completeness(
    lineage: pd.DataFrame | Iterable[Mapping[str, Any]],
    groundtruth: pd.DataFrame | Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Per-class rho_rev plus rho_enum.

    groundtruth rows carry optional `restored_matches_before` (bool) after
    the procedure has run. If absent, `attestation_action` is used:
      restored | quarantined | escalated.
    """
    lin_df = _frame(
        lineage,
        ["task_id", "step", "write_class", "store", "operation", "is_write"],
    )
    gt_df = _frame(
        groundtruth,
        [
            "task_id",
            "step",
            "write_class",
            "store",
            "operation",
            "key",
            "before",
            "after",
            "restored_matches_before",
            "attestation_action",
        ],
    )

    writes_lin = lin_df
    if "is_write" in lin_df.columns and lin_df["is_write"].notna().any():
        writes_lin = lin_df[lin_df["is_write"].fillna(False).astype(bool)]
    elif "write_class" in lin_df.columns:
        writes_lin = lin_df[lin_df["write_class"].notna()]

    n_lin = int(len(writes_lin))
    n_gt = int(len(gt_df))
    rho_enum: float | None = None if n_gt == 0 else n_lin / n_gt

    out: dict[str, dict[str, Any]] = {"rho_enum": rho_enum}
    for cls in WRITE_CLASSES:
        subset = gt_df[gt_df["write_class"] == cls] if not gt_df.empty else gt_df
        n = int(len(subset))
        if cls in ("idempotent", "versioned"):
            if n == 0:
                out[cls] = {"rho_rev": None, "n": 0, "restored": 0}
                continue
            if "restored_matches_before" in subset.columns and subset[
                "restored_matches_before"
            ].notna().any():
                flag = pd.to_numeric(
                    subset["restored_matches_before"], errors="coerce"
                ).fillna(0)
                restored = int(flag.astype(bool).sum())
            else:
                restored = int((subset["attestation_action"] == "restored").sum())
            out[cls] = {"rho_rev": restored / n, "n": n, "restored": restored}
        elif cls == "derived":
            quarantined = (
                int((subset["attestation_action"] == "quarantined").sum()) if n else 0
            )
            out[cls] = {"rho_rev": None, "n": n, "quarantined": quarantined}
        else:
            escalated = (
                int((subset["attestation_action"] == "escalated").sum()) if n else 0
            )
            rho = 0.0 if n else None
            out[cls] = {"rho_rev": rho, "n": n, "escalated": escalated}
    return out


def verification_overhead(
    spans: pd.DataFrame | Iterable[Mapping[str, Any]],
    baseline_spans: pd.DataFrame | Iterable[Mapping[str, Any]],
) -> dict[str, float | None]:
    """Compare verify-span cost of a run against a same-seed baseline."""
    spans_df = _frame(spans, ["name", "duration_ms", "mode"])
    base_df = _frame(baseline_spans, ["name", "duration_ms", "mode"])

    def _sum(df: pd.DataFrame, name: str | None = None) -> float:
        if df.empty:
            return 0.0
        work = df if name is None else df[df["name"] == name]
        if work.empty or "duration_ms" not in work.columns:
            return 0.0
        return float(pd.to_numeric(work["duration_ms"], errors="coerce").fillna(0).sum())

    verify_ms = _sum(spans_df, VERIFY_SPAN)
    base_verify_ms = _sum(base_df, VERIFY_SPAN)
    total_ms = _sum(spans_df)
    base_total_ms = _sum(base_df)
    relative = None if base_total_ms == 0 else (total_ms - base_total_ms) / base_total_ms
    return {
        "absolute_seconds": (verify_ms - base_verify_ms) / 1000.0,
        "relative": relative,
        "verify_ms": verify_ms,
        "total_ms": total_ms,
        "baseline_verify_ms": base_verify_ms,
        "baseline_total_ms": base_total_ms,
    }
