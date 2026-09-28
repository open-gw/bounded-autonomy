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
    """τ / T. τ is SVID TTL (exp − iat), T is the OTel root-span duration.

    Epoch columns issued_at_epoch / not_after_epoch are the JWT-SVID (or
    projected SA-token) iat/exp. τ is not issue-to-delete and not
    registration-entry deletion. A span named `run` with start_epoch /
    end_epoch is preferred for T. Falls back to unique SPIFFE IDs over
    unique task IDs when those columns are absent.
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
        lin_c = writes_lin[writes_lin["write_class"] == cls] if not writes_lin.empty else writes_lin
        n_lin_c = int(len(lin_c))
        rho_enum_c: float | None = None if n == 0 else n_lin_c / n
        if cls in ("idempotent", "versioned"):
            if n == 0:
                out[cls] = {
                    "rho_rev": None,
                    "n": 0,
                    "restored": 0,
                    "rho_enum": rho_enum_c,
                    "rho_quarantined": 0.0,
                    "rho_escalated": 0.0,
                }
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
            out[cls] = {
                "rho_rev": restored / n,
                "n": n,
                "restored": restored,
                "rho_enum": rho_enum_c,
                "rho_quarantined": 0.0,
                "rho_escalated": 0.0,
            }
        elif cls == "derived":
            quarantined = (
                int((subset["attestation_action"] == "quarantined").sum()) if n else 0
            )
            out[cls] = {
                "rho_rev": None,
                "n": n,
                "quarantined": quarantined,
                "rho_enum": rho_enum_c,
                "rho_quarantined": None if n == 0 else quarantined / n,
                "rho_escalated": 0.0,
            }
        else:
            escalated = (
                int((subset["attestation_action"] == "escalated").sum()) if n else 0
            )
            rho = 0.0 if n else None
            out[cls] = {
                "rho_rev": rho,
                "n": n,
                "escalated": escalated,
                "rho_enum": rho_enum_c,
                "rho_quarantined": 0.0,
                "rho_escalated": None if n == 0 else escalated / n,
            }
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


def step_cost_split(
    boundaries: Iterable[Mapping[str, Any]],
    *,
    probe_enabled: bool,
    tolerance_pct: float = 5.0,
) -> dict[str, Any]:
    """Per-boundary SVID / propagation / probe / other split.

    ``other_ms`` is the residual of observed ``boundary_ms`` after the three
    named clocks. Totals must reconcile with observed boundary duration
    within ``tolerance_pct``.
    """
    rows: list[dict[str, Any]] = []
    for raw in boundaries:
        prop = float(raw.get("propagation_ms") or 0.0)
        svid = float(raw.get("svid_reissue_ms") or 0.0)
        probe = float(raw.get("probe_ms") or 0.0)
        observed = float(raw.get("boundary_ms") or 0.0)
        if "other_ms" in raw and raw["other_ms"] is not None:
            other = float(raw["other_ms"])
        else:
            other = observed - prop - svid - probe
        accounted = prop + svid + probe + other
        if observed <= 0:
            observed = accounted
        if observed > 0:
            row_err = abs(accounted - observed) / observed * 100.0
        else:
            row_err = 0.0
        d_ms = float(raw["d_ms"]) if raw.get("d_ms") is not None else prop
        row: dict[str, Any] = {
            "step": int(raw.get("step") or 0),
            "propagation_ms": prop,
            "svid_reissue_ms": svid,
            "probe_ms": probe,
            "other_ms": other,
            "boundary_ms": observed,
            "d_ms": d_ms,
            "reconcile_error_pct": row_err,
            "reconcile_ok": row_err <= tolerance_pct,
        }
        for key in (
            "declaration_updated_at_epoch",
            "first_enforced_at_epoch",
            "cnp_wait_started_epoch",
            "cnp_valid_epoch",
        ):
            if raw.get(key) is not None:
                row[key] = float(raw[key])
        rows.append(row)
    totals = {
        "propagation_ms": sum(r["propagation_ms"] for r in rows),
        "svid_reissue_ms": sum(r["svid_reissue_ms"] for r in rows),
        "probe_ms": sum(r["probe_ms"] for r in rows),
        "other_ms": sum(r["other_ms"] for r in rows),
        "boundary_ms": sum(r["boundary_ms"] for r in rows),
    }
    accounted = (
        totals["propagation_ms"]
        + totals["svid_reissue_ms"]
        + totals["probe_ms"]
        + totals["other_ms"]
    )
    observed = totals["boundary_ms"]
    error_pct = abs(accounted - observed) / observed * 100.0 if observed > 0 else 0.0
    per_ok = all(bool(r.get("reconcile_ok")) for r in rows) if rows else True
    max_row = max((float(r.get("reconcile_error_pct") or 0.0) for r in rows), default=0.0)
    return {
        "probe_enabled": bool(probe_enabled),
        "boundaries": rows,
        "totals": totals,
        "reconcile_error_pct": max(error_pct, max_row),
        "reconcile_ok": error_pct <= tolerance_pct and per_ok,
    }
