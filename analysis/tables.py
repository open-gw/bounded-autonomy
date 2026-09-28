"""Emit the three manuscript tables from result.json files.

Used by `make analyse`, `make paper-tables`, and analysis/notebook.ipynb.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from metrics import verify_duration_variance

ROOT = Path(__file__).resolve().parents[1]
_mpl = ROOT / "analysis" / ".mplcache"
_mpl.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl))

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "runs" / "results"
FIXTURE_RESULTS = ROOT / "analysis" / "fixtures" / "results"
_EMDASH = "\u2014"
SWEEP_VARIANTS = ("k1", "k3", "k5", "k7")


def load_results(results_dir: Path) -> list[dict[str, Any]]:
    paths = [
        path
        for path in sorted(results_dir.glob("**/result.json"))
        if not any(part.startswith("_") for part in path.parts)
    ]
    out: list[dict[str, Any]] = []
    for path in paths:
        doc = json.loads(path.read_text())
        doc["_path"] = str(path)
        out.append(doc)
    if not out:
        raise FileNotFoundError(f"no result.json under {results_dir}")
    return out


class ProvenanceError(Exception):
    """Manuscript tables requested from non-cluster results."""


def _variant_of(row: dict[str, Any]) -> str | None:
    variant = row.get("variant") or (row.get("declaration") or {}).get("variant")
    return str(variant) if variant else None


def _is_sweep(row: dict[str, Any]) -> bool:
    return _variant_of(row) in SWEEP_VARIANTS


def _is_data_intensive(row: dict[str, Any]) -> bool:
    return str(row.get("profile") or "long-multistep") == "data-intensive"


def _is_redeclaration(row: dict[str, Any]) -> bool:
    return str(row.get("profile") or "") == "redeclaration"


def _is_step_split(row: dict[str, Any]) -> bool:
    if row.get("step_cost_split"):
        return True
    run_id = str(row.get("run_id") or "")
    return "step-split" in run_id or "step-noprobe" in run_id


def _is_gateway(row: dict[str, Any]) -> bool:
    return row.get("mode") in ("gateway-only", "gateway-bypass") or bool(row.get("gateway_bypass"))


def _task_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in results
        if (r.get("declaration") or {}).get("granularity", "task") == "task"
        and not _is_sweep(r)
        and not _is_data_intensive(r)
        and not _is_gateway(r)
        and not _is_redeclaration(r)
        and not _is_step_split(r)
    ]


def _data_intensive_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in results if _is_data_intensive(r)]


def _sweep_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in results if _is_sweep(r)]


def _evasion_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in _task_results(results)
        if isinstance(r.get("evasion_matrix"), list) and r["evasion_matrix"]
    ]


def _evasion_consensus(results: list[dict[str, Any]], mode: str, row: int) -> str:
    verdicts = []
    for r in results:
        if r.get("mode") != mode:
            continue
        for item in r.get("evasion_matrix") or []:
            if int(item.get("row") or 0) == row:
                verdicts.append(str(item.get("verdict") or "error"))
    if not verdicts:
        return _EMDASH
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v] = counts.get(v, 0) + 1
    top = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return f"{top[0]} ({top[1]}/{len(verdicts)})"


_EVASION_LABELS = (
    (1, "direct-IP declared service pod"),
    (2, "direct-IP undeclared service pod"),
    (3, "DNS undeclared via CoreDNS + raw UDP/53 to 1.1.1.1"),
    (4, "external TCP/443 to 1.1.1.1"),
    (5, "node metadata 169.254.169.254:80"),
    (6, "kubernetes.default.svc:443 and ClusterIP"),
    (7, "node IP kubelet :10250"),
)


def _evasion_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    results = _evasion_results(results)
    rows: list[tuple[str, ...]] = []
    for spec in ({"row": n, "label": label} for n, label in _EVASION_LABELS):
        n = int(spec["row"])
        rows.append(
            (
                str(n),
                str(spec["label"]),
                _evasion_consensus(results, "flat", n),
                _evasion_consensus(results, "full", n),
            )
        )
    return rows


def table_evasion(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| row | probe | flat | full |",
        "| ---: | --- | --- | --- |",
        _evasion_rows(results),
    )


def emit_evasion_markdown(results: list[dict[str, Any]]) -> str:
    gated = _evasion_results(results)
    parts = [
        "# Evasion matrix (Task 23)",
        "",
        source_caption(gated, "Evasion"),
        "",
        table_evasion(results),
        "",
        "DNS is restricted to CoreDNS for declared names only. External "
        "resolver and TCP/443 target is Cloudflare `1.1.1.1`.",
        "",
    ]
    return "\n".join(parts)


def emit_evasion_latex(results: list[dict[str, Any]]) -> str:
    gated = _evasion_results(results)
    return (
        _tex_tabular(
            gated,
            "Evasion",
            "rlll",
            r"row & probe & flat & full",
            _evasion_rows(results),
        )
        + "\n"
    )


def _b_intersect_r(row: dict[str, Any]) -> int:
    metrics = row.get("metrics") or {}
    if "breach_intersection_size" in metrics:
        return int(metrics["breach_intersection_size"])
    breach = set(metrics.get("breach_services") or [])
    if not breach:
        breach = {"docs"}
    reached = set(metrics.get("reachable_services") or [])
    return len(breach & reached)


def _gateway_cell(row: dict[str, Any]) -> str:
    if row.get("mode") == "full" and row.get("gateway_bypass"):
        return "full+bypass"
    return str(row.get("mode") or "")


def _gateway_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in results if _is_gateway(r)]


def _gateway_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for row in sorted(
        _gateway_results(results),
        key=lambda r: (_gateway_cell(r), int(r.get("seed") or 0)),
    ):
        metrics = row.get("metrics") or {}
        rows.append(
            (
                _gateway_cell(row),
                str(row.get("seed") or ""),
                str(metrics.get("reachable_set_size") or 0),
                str(_b_intersect_r(row)),
                str(row.get("source") or ""),
            )
        )
    return rows


def table_gateway(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| mode | seed | \\|S\\| | \\|B ∩ R\\| | source |",
        "| --- | ---: | ---: | ---: | --- |",
        _gateway_rows(results),
    )


def _gateway_dispersion_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _gateway_results(results):
        grouped[_gateway_cell(row)].append(row)
    rows: list[tuple[str, ...]] = []
    for cell in sorted(grouped):
        cell_rows = grouped[cell]
        sizes = median_iqr_ci(
            _metric_values(cell_rows, lambda r: (r.get("metrics") or {}).get("reachable_set_size"))
        )
        inter = median_iqr_ci(_metric_values(cell_rows, _b_intersect_r))
        rows.append(
            (
                cell,
                str(len(cell_rows)),
                _fmt_median_iqr(sizes, 3),
                _fmt_ci(sizes, 3),
                _fmt_median_iqr(inter, 3),
                _fmt_ci(inter, 3),
            )
        )
    return rows


def table_gateway_dispersion(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| mode | n | median \\|S\\| [IQR] | 95% CI | median \\|B ∩ R\\| [IQR] | 95% CI |",
        "| --- | ---: | --- | --- | --- | --- |",
        _gateway_dispersion_rows(results),
    )


def emit_gateway_markdown(results: list[dict[str, Any]]) -> str:
    gated = _gateway_results(results)
    parts = [
        "# Gateway modes (Task 24 / Apache APISIX)",
        "",
        source_caption(gated, "Gateway"),
        "",
        table_gateway(results),
        "",
        "## Dispersion (M6)",
        "",
        source_caption(gated, "Gateway dispersion"),
        "",
        table_gateway_dispersion(results),
        "",
        "Product is Apache APISIX. Plugin is `uri-blocker`. Not Kong.",
        "",
    ]
    return "\n".join(parts)


def emit_gateway_latex(results: list[dict[str, Any]]) -> str:
    gated = _gateway_results(results)
    return (
        _tex_tabular(
            gated,
            "Gateway",
            "lrrrl",
            r"mode & seed & $|S|$ & $|B \cap R|$ & source",
            _gateway_rows(results),
        )
        + "\n\n"
        + _tex_tabular(
            gated,
            "Gateway dispersion",
            "lrlrlr",
            r"mode & $n$ & median $|S|$ [IQR] & 95\% CI & median $|B \cap R|$ [IQR] & 95\% CI",
            _gateway_dispersion_rows(results),
        )
        + "\n"
    )


def _verify_span_count_error(n_verify: int, steps: int, mode: str) -> str | None:
    """Symmetric leftover / missing Tempo-trace check.

    ``n > steps`` is leftover traces from a reused ``task_id``.
    ``n < steps - 1`` is missing traces (full/step runs complete 29 of 30
    because the undeclared docs injection never reaches a tool).
    Flat runs complete every step, so they must match ``steps`` exactly.
    """
    if n_verify > steps:
        return (
            f"verify-span count {n_verify} exceeds steps_completed={steps} "
            "(leftover Tempo traces)"
        )
    if mode == "flat" and n_verify != steps:
        return (
            f"verify-span count {n_verify} != steps_completed={steps} "
            "(flat requires one verify span per completed step)"
        )
    floor = steps - 1
    if n_verify < floor:
        return (
            f"verify-span count {n_verify} below steps_completed-1={floor} "
            "(missing traces)"
        )
    return None


def assert_cluster_provenance(results: list[dict[str, Any]]) -> None:
    """Refuse manuscript tables unless every result is from the cluster
    and verify-span durations actually vary (not the in-process constants).

    Also refuse leftover and missing Tempo traces: a SIGTERM'd retry that
    reused ``task_id`` can ingest verify spans from the killed attempt, so
    the count must not exceed ``steps_completed`` (default 30 if missing).
    Fewer than ``steps_completed - 1`` means Tempo dropped spans. Flat
    mode must match ``steps_completed`` exactly.
    """
    bad: list[str] = []
    for row in results:
        source = row.get("source")
        path = row.get("_path", row.get("run_id", "?"))
        if source != "cluster":
            bad.append(f"{path}: source={source!r}")
            continue
        span_path = Path(path).parent / "spans.parquet"
        if not span_path.exists():
            bad.append(f"{path}: missing spans.parquet")
            continue
        spans = pd.read_parquet(span_path)
        nunique = verify_duration_variance(spans)
        if nunique <= 1:
            bad.append(f"{path}: verify-span durations have zero variance (nunique={nunique})")
        n_verify = int((spans["name"] == "verify").sum()) if "name" in spans.columns else 0
        steps = row.get("steps_completed")
        cap = 30 if steps is None else int(steps)
        count_err = _verify_span_count_error(n_verify, cap, str(row.get("mode") or ""))
        if count_err:
            bad.append(f"{path}: {count_err}")
    if not bad:
        return
    lines = [
        "refusing manuscript tables: every result.json must have source=cluster",
        "and verify-span durations with non-zero variance",
        "and verify-span count in [steps_completed-1, steps_completed]",
        "  (leftover Tempo traces above the cap, missing traces below the floor;",
        "   flat requires n == steps_completed)",
        "non-cluster or synthetic-span inputs:",
        *[f"  - {item}" for item in bad],
        "simulator/fixture numbers must not be pasted into the manuscript",
    ]
    raise ProvenanceError("\n".join(lines))


def source_caption(results: list[dict[str, Any]], table_name: str) -> str:
    sources = sorted({str(r.get("source", "unknown")) for r in results})
    n = len(results)
    return f"*Caption: {table_name}. source={'+'.join(sources)} (n={n}).*"


def _by_mode(results: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[row["mode"]].append(row)
    return dict(grouped)


def _mean(xs: list[float]) -> float:
    return statistics.fmean(xs) if xs else float("nan")


def _latex_cell(value: str) -> str:
    if value == _EMDASH:
        return r"\textemdash{}"
    return value


def _md_lines(header: str, align: str, rows: list[tuple[str, ...]]) -> str:
    lines = [header, align]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _tex_tabular(
    results: list[dict[str, Any]],
    name: str,
    colspec: str,
    header: str,
    rows: list[tuple[str, ...]],
) -> str:
    comment = source_caption(results, name).strip("*")
    lines = [
        f"% --- {name} ---",
        f"% {comment}",
        rf"\begin{{tabular}}{{{colspec}}}",
        header + r" \\",
        r"\hline",
    ]
    for row in rows:
        lines.append(" & ".join(_latex_cell(c) for c in row) + r" \\")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def _reach_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    results = _task_results(results)
    rows: list[tuple[str, ...]] = []
    for mode, mode_rows in sorted(_by_mode(results).items()):
        sizes = [int(r["metrics"]["reachable_set_size"]) for r in mode_rows]
        declared_n = [len(r["declaration"]["services"]) for r in mode_rows]
        extra = [s - d for s, d in zip(sizes, declared_n)]
        weights = [int(r["metrics"].get("reachable_weight") or 0) for r in mode_rows]
        rows.append(
            (
                mode,
                str(len(mode_rows)),
                f"{_mean(sizes):.3f}",
                str(min(sizes)),
                str(max(sizes)),
                f"{_mean(extra):.3f}",
                f"{_mean(weights):.3f}",
            )
        )
    return rows


def table_reach(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| mode | n | mean \\|S\\| | min | max | mean extra | mean R_w |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        _reach_rows(results),
    )


def _rollback_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    results = _task_results(results)
    # Paper 1 reports rollback from full (segmented) drifted runs; flat is listed for contrast.
    rows: list[tuple[str, ...]] = []
    for mode, mode_rows in sorted(_by_mode(results).items()):
        rb = [r["metrics"]["rollback_completeness"] for r in mode_rows]
        for cls, extra_key in (
            ("idempotent", "restored"),
            ("versioned", "restored"),
            ("derived", "quarantined"),
            ("irreversible", "escalated"),
        ):
            rhos = [c[cls]["rho_rev"] for c in rb if c[cls]["rho_rev"] is not None]
            ns = [c[cls]["n"] for c in rb]
            extras = [c[cls][extra_key] for c in rb]
            rho_txt = _EMDASH if not rhos else f"{_mean(rhos):.3f}"
            rows.append(
                (mode, cls, rho_txt, f"{_mean(ns):.1f}", f"{_mean(extras):.1f}")
            )
    return rows


def table_rollback(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| mode | class | mean rho_rev | mean n | mean restored/quarantined/escalated |",
        "| --- | --- | ---: | ---: | ---: |",
        _rollback_rows(results),
    )


def _rho_cell(values: list[float | None]) -> str:
    present = [float(v) for v in values if v is not None]
    return _EMDASH if not present else f"{_mean(present):.3f}"


def _data_intensive_rollback_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for mode, mode_rows in sorted(_by_mode(results).items()):
        rb = [r["metrics"]["rollback_completeness"] for r in mode_rows]
        enums = [r["metrics"].get("rho_enum") for r in mode_rows]
        for cls, extra_key in (
            ("idempotent", "restored"),
            ("versioned", "restored"),
            ("derived", "quarantined"),
            ("irreversible", "escalated"),
        ):
            rhos = [c[cls]["rho_rev"] for c in rb if c[cls]["rho_rev"] is not None]
            ns = [c[cls]["n"] for c in rb]
            extras = [c[cls].get(extra_key) or 0 for c in rb]
            class_enums = [
                c[cls].get("rho_enum")
                if c[cls].get("rho_enum") is not None
                else enums[i]
                for i, c in enumerate(rb)
            ]
            q_rates = []
            e_rates = []
            for c in rb:
                n = c[cls]["n"] or 0
                if cls == "derived":
                    q = c[cls].get("rho_quarantined")
                    if q is None:
                        q = None if n == 0 else (c[cls].get("quarantined") or 0) / n
                    q_rates.append(q)
                    e_rates.append(c[cls].get("rho_escalated") if c[cls].get("rho_escalated") is not None else 0.0)
                elif cls == "irreversible":
                    e = c[cls].get("rho_escalated")
                    if e is None:
                        e = None if n == 0 else (c[cls].get("escalated") or 0) / n
                    e_rates.append(e)
                    q_rates.append(c[cls].get("rho_quarantined") if c[cls].get("rho_quarantined") is not None else 0.0)
                else:
                    q_rates.append(c[cls].get("rho_quarantined") if c[cls].get("rho_quarantined") is not None else 0.0)
                    e_rates.append(c[cls].get("rho_escalated") if c[cls].get("rho_escalated") is not None else 0.0)
            rows.append(
                (
                    mode,
                    cls,
                    _rho_cell(class_enums),
                    _EMDASH if not rhos else f"{_mean(rhos):.3f}",
                    f"{_mean(ns):.1f}",
                    _rho_cell(q_rates),
                    _rho_cell(e_rates),
                    f"{_mean(extras):.1f}",
                )
            )
    return rows


def table_data_intensive_rollback(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| mode | class | mean rho_enum | mean rho_rev | mean n | mean rho_quarantined | mean rho_escalated | mean count |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        _data_intensive_rollback_rows(results),
    )


def _overhead_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    results = _task_results(results)
    rows: list[tuple[str, ...]] = []
    flat_by_seed = {r["seed"]: r for r in results if r["mode"] == "flat"}
    for mode, mode_rows in sorted(_by_mode(results).items()):
        verify = [float(r["metrics"]["verification_overhead"]["verify_ms"]) for r in mode_rows]
        relatives: list[float] = []
        for r in mode_rows:
            rel = r["metrics"]["verification_overhead"].get("relative")
            if rel is None and r["seed"] in flat_by_seed and mode != "flat":
                t = r["metrics"]["verification_overhead"]["total_ms"]
                b = flat_by_seed[r["seed"]]["metrics"]["verification_overhead"]["total_ms"]
                rel = None if b == 0 else (t - b) / b
            if mode == "flat":
                rel = 0.0
            if rel is not None:
                relatives.append(float(rel))
        rel_txt = _EMDASH if not relatives else f"{_mean(relatives):.4f}"
        rows.append((mode, str(len(mode_rows)), f"{_mean(verify):.1f}", rel_txt))
    return rows


def table_overhead(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| mode | n | mean verify_ms | mean relative vs same-seed flat |",
        "| --- | ---: | ---: | ---: |",
        _overhead_rows(results),
    )


def q2_series(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-seed |S| for the Q2 grouped-bar figure."""
    results = _task_results(results)
    return [
        {
            "seed": r["seed"],
            "mode": r["mode"],
            "reachable_set_size": r["metrics"]["reachable_set_size"],
            "declared": len(r["declaration"]["services"]),
            "extra": r["metrics"]["reachable_set_size"] - len(r["declaration"]["services"]),
        }
        for r in sorted(results, key=lambda r: (r["seed"], r["mode"]))
    ]


def _q2_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    return [
        (
            str(row["seed"]),
            str(row["mode"]),
            str(row["reachable_set_size"]),
            str(row["declared"]),
            str(row["extra"]),
        )
        for row in q2_series(results)
    ]


def _credentials_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    results = _task_results(results)
    rows: list[tuple[str, ...]] = []
    for mode, mode_rows in sorted(_by_mode(results).items()):
        tau = [float(r["metrics"]["tau_seconds"]) for r in mode_rows if r["metrics"].get("tau_seconds") is not None]
        tsec = [float(r["metrics"]["T_seconds"]) for r in mode_rows if r["metrics"].get("T_seconds") is not None]
        ratio = [float(r["metrics"]["credential_ratio"]) for r in mode_rows if r["metrics"].get("credential_ratio") is not None]
        rows.append(
            (mode, str(len(mode_rows)), f"{_mean(tau):.3f}", f"{_mean(tsec):.3f}", f"{_mean(ratio):.3f}")
        )
    return rows


def table_credentials(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| mode | n | mean τ (s) | mean T (s) | mean τ/T |",
        "| --- | ---: | ---: | ---: | ---: |",
        _credentials_rows(results),
    )


def _segment_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    results = _task_results(results)
    rows: list[tuple[str, ...]] = []
    for mode, mode_rows in sorted(_by_mode(results).items()):
        p = [float(r["metrics"]["segment_p_ms"]) for r in mode_rows if r["metrics"].get("segment_p_ms") is not None]
        q = [float(r["metrics"]["segment_q_ms"]) for r in mode_rows if r["metrics"].get("segment_q_ms") is not None]
        dmean = [float(r["metrics"]["d_ms_mean"]) for r in mode_rows if r["metrics"].get("d_ms_mean") is not None]
        dmax = [float(r["metrics"]["d_ms_max"]) for r in mode_rows if r["metrics"].get("d_ms_max") is not None]
        rows.append(
            (
                mode,
                str(len(mode_rows)),
                f"{_mean(p):.1f}",
                f"{_mean(q):.1f}",
                f"{_mean(dmean):.1f}",
                f"{_mean(dmax):.1f}",
            )
        )
    return rows


def table_segment(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| mode | n | mean p (ms) | mean q (ms) | mean d (ms) | max d (ms) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        _segment_rows(results),
    )


def _step_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    rows = [
        r
        for r in results
        if (r.get("declaration") or {}).get("granularity") == "step"
        and not _is_step_split(r)
        and not _is_redeclaration(r)
    ]
    if not rows:
        return [(_EMDASH, _EMDASH, _EMDASH, _EMDASH, _EMDASH)]
    out: list[tuple[str, ...]] = []
    for r in sorted(rows, key=lambda x: x["seed"]):
        m = r["metrics"]
        out.append(
            (
                str(r["seed"]),
                f"{m.get('step_ratio_mean'):.3f}",
                f"{m.get('step_ratio_max'):.3f}",
                f"{m.get('d_ms_mean'):.1f}",
                f"{m.get('d_ms_max'):.1f}",
            )
        )
    return out


def _sweep_summary_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _sweep_results(results):
        grouped[str(_variant_of(row))].append(row)
    out: list[tuple[str, ...]] = []
    for variant in SWEEP_VARIANTS:
        rows = grouped.get(variant) or []
        if not rows:
            continue
        k = int(variant[1:])
        sizes = [int(r["metrics"]["reachable_set_size"]) for r in rows]
        weights = [int(r["metrics"].get("reachable_weight") or 0) for r in rows]
        inter = [_b_intersect_r(r) for r in rows]
        out.append(
            (
                str(k),
                str(len(rows)),
                f"{_mean([float(s) for s in sizes]):.3f}",
                str(min(sizes)),
                str(max(sizes)),
                f"{_mean([float(w) for w in weights]):.3f}",
                f"{_mean([float(x) for x in inter]):.3f}",
            )
        )
    return out


def _sweep_seed_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    rows = sorted(
        _sweep_results(results),
        key=lambda r: (_variant_of(r) or "", int(r.get("seed") or 0)),
    )
    return [
        (
            str(_variant_of(r)),
            str(r.get("seed")),
            str(len(r.get("declaration", {}).get("services") or [])),
            str(r["metrics"]["reachable_set_size"]),
            str(r["metrics"].get("reachable_weight") or 0),
            str(_b_intersect_r(r)),
        )
        for r in rows
    ]


def table_sweep(results: list[dict[str, Any]]) -> str:
    parts = [
        _md_lines(
            "| k | n | mean \\|R\\| | min \\|R\\| | max \\|R\\| | mean R_w | mean \\|B ∩ R\\| |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            _sweep_summary_rows(results),
        ),
        "",
        _md_lines(
            "| variant | seed | k | \\|R\\| | R_w | \\|B ∩ R\\| |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            _sweep_seed_rows(results),
        ),
    ]
    return "\n".join(parts)


def table_step(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| seed | mean τ/T | max τ/T | mean d (ms) | max d (ms) |",
        "| ---: | ---: | ---: | ---: | ---: |",
        _step_rows(results),
    )


def _dispersion_series(results: list[dict[str, Any]]) -> list[tuple[str, str, list[float], int]]:
    """(mode, metric, values, digits) for headline task-granularity cells."""
    series: list[tuple[str, str, list[float], int]] = []
    for mode, mode_rows in sorted(_by_mode(_task_results(results)).items()):
        series.append(
            (
                mode,
                "|S|",
                _metric_values(mode_rows, lambda r: (r.get("metrics") or {}).get("reachable_set_size")),
                3,
            )
        )
        series.append(
            (
                mode,
                "R_w",
                _metric_values(mode_rows, lambda r: (r.get("metrics") or {}).get("reachable_weight")),
                3,
            )
        )
        series.append(
            (
                mode,
                "verify_ms",
                _metric_values(
                    mode_rows,
                    lambda r: ((r.get("metrics") or {}).get("verification_overhead") or {}).get("verify_ms"),
                ),
                1,
            )
        )
        series.append(
            (
                mode,
                "τ (s)",
                _metric_values(mode_rows, lambda r: (r.get("metrics") or {}).get("tau_seconds")),
                3,
            )
        )
        series.append(
            (
                mode,
                "T (s)",
                _metric_values(mode_rows, lambda r: (r.get("metrics") or {}).get("T_seconds")),
                3,
            )
        )
        series.append(
            (
                mode,
                "τ/T",
                _metric_values(mode_rows, lambda r: (r.get("metrics") or {}).get("credential_ratio")),
                3,
            )
        )
    return series


def _dispersion_rows(results: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for mode, metric, values, digits in _dispersion_series(results):
        stat = median_iqr_ci(values)
        rows.append(
            (
                mode,
                metric,
                str(stat["n"]),
                _fmt_median_iqr(stat, digits),
                _fmt_ci(stat, digits),
            )
        )
    return rows


def table_dispersion(results: list[dict[str, Any]]) -> str:
    return _md_lines(
        "| mode | metric | n | median [IQR] | bootstrap 95% CI |",
        "| --- | --- | ---: | --- | --- |",
        _dispersion_rows(results),
    )


def dispersion_document(results: list[dict[str, Any]]) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    for mode, metric, values, _digits in _dispersion_series(results):
        stat = median_iqr_ci(values)
        cells.append({"mode": mode, "metric": metric, **stat})
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _gateway_results(results):
        grouped[_gateway_cell(row)].append(row)
    for cell, cell_rows in sorted(grouped.items()):
        sizes = median_iqr_ci(
            _metric_values(cell_rows, lambda r: (r.get("metrics") or {}).get("reachable_set_size"))
        )
        inter = median_iqr_ci(_metric_values(cell_rows, _b_intersect_r))
        cells.append({"mode": cell, "metric": "|S|", **sizes})
        cells.append({"mode": cell, "metric": "|B ∩ R|", **inter})
    return {
        "schema": "dispersion.schema.json",
        "resamples": BOOTSTRAP_RESAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "cells": cells,
    }


def emit_dispersion_markdown(results: list[dict[str, Any]]) -> str:
    gated = _task_results(results)
    parts = [
        "# Dispersion (M6)",
        "",
        source_caption(gated, "Dispersion"),
        "",
        table_dispersion(results),
        "",
        "Median [IQR]; bootstrap 95% CI for the median, 1000 resamples, seed 26.",
        "",
    ]
    if _gateway_results(results):
        parts.extend(
            [
                "## Gateway",
                "",
                table_gateway_dispersion(results),
                "",
            ]
        )
    return "\n".join(parts)


def emit_dispersion_latex(results: list[dict[str, Any]]) -> str:
    gated = _task_results(results)
    parts = [
        _tex_tabular(
            gated,
            "Dispersion",
            "llrrr",
            r"mode & metric & $n$ & median [IQR] & bootstrap 95\% CI",
            _dispersion_rows(results),
        ),
        "",
    ]
    if _gateway_results(results):
        parts.extend(
            [
                _tex_tabular(
                    _gateway_results(results),
                    "Gateway dispersion",
                    "lrlrlr",
                    r"mode & $n$ & median $|S|$ [IQR] & 95\% CI & median $|B \cap R|$ [IQR] & 95\% CI",
                    _gateway_dispersion_rows(results),
                ),
                "",
            ]
        )
    return "\n".join(parts)


def _redeclaration_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in results if _is_redeclaration(r)]


def _step_split_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in results if _is_step_split(r)]


BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 26


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return ordered[int(k)]
    return ordered[lo] * (hi - k) + ordered[hi] * (k - lo)


def _iqr(values: list[float]) -> tuple[float, float]:
    return _percentile(values, 0.25), _percentile(values, 0.75)


def median_iqr_ci(
    values: list[float],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Median, Tukey IQR, and percentile bootstrap 95% CI for the median."""
    present = [float(v) for v in values]
    if not present:
        return {
            "n": 0,
            "median": None,
            "q1": None,
            "q3": None,
            "iqr": None,
            "ci95_low": None,
            "ci95_high": None,
            "resamples": resamples,
            "bootstrap_seed": seed,
        }
    med = _median(present)
    q1, q3 = _iqr(present)
    rng = random.Random(seed)
    n = len(present)
    boot: list[float] = []
    for _ in range(resamples):
        sample = [present[rng.randrange(n)] for _ in range(n)]
        boot.append(_median(sample))
    boot.sort()
    lo_idx = int(math.floor(0.025 * (resamples - 1)))
    hi_idx = int(math.ceil(0.975 * (resamples - 1)))
    lo_idx = max(0, min(resamples - 1, lo_idx))
    hi_idx = max(0, min(resamples - 1, hi_idx))
    return {
        "n": n,
        "median": med,
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
        "ci95_low": boot[lo_idx],
        "ci95_high": boot[hi_idx],
        "resamples": resamples,
        "bootstrap_seed": seed,
    }


def _fmt_median_iqr(stat: dict[str, Any], digits: int = 3) -> str:
    if not stat.get("n") or stat.get("median") is None:
        return _EMDASH
    fmt = f"{{:.{digits}f}}"
    return (
        f"{fmt.format(stat['median'])} "
        f"[{fmt.format(stat['q1'])}, {fmt.format(stat['q3'])}]"
    )


def _fmt_ci(stat: dict[str, Any], digits: int = 3) -> str:
    if not stat.get("n") or stat.get("ci95_low") is None:
        return _EMDASH
    fmt = f"{{:.{digits}f}}"
    return f"{fmt.format(stat['ci95_low'])}–{fmt.format(stat['ci95_high'])}"


def _metric_values(rows: list[dict[str, Any]], getter) -> list[float]:
    out: list[float] = []
    for row in rows:
        value = getter(row)
        if value is None:
            continue
        out.append(float(value))
    return out


def table_redeclaration(results: list[dict[str, Any]]) -> str:
    rows = sorted(_redeclaration_results(results), key=lambda r: int(r.get("seed") or 0))
    costs = [float(r.get("redeclaration_cost_ms") or 0.0) for r in rows]
    body: list[tuple[str, ...]] = []
    for r in rows:
        body.append(
            (
                str(r.get("seed")),
                f"{float(r.get('redeclaration_cost_ms') or 0.0):.1f}",
                str(int(r.get("steps_reexecuted") or 0)),
                "yes" if r.get("writes_committed_before_termination") else "no",
                str(r.get("source") or ""),
            )
        )
    parts = [
        _md_lines(
            "| seed | redeclaration_cost_ms | steps re-executed | writes committed | source |",
            "| ---: | ---: | ---: | --- | --- |",
            body or [(_EMDASH, _EMDASH, _EMDASH, _EMDASH, _EMDASH)],
        ),
        "",
        f"Median redeclaration_cost_ms over {len(costs)} seed(s): **{_median(costs):.1f}**",
    ]
    return "\n".join(parts)


def table_step_split(results: list[dict[str, Any]]) -> str:
    rows = sorted(
        _step_split_results(results),
        key=lambda r: (
            0 if (r.get("observer") or {}).get("probe", True) else 1,
            int(r.get("seed") or 0),
        ),
    )
    body: list[tuple[str, ...]] = []
    for r in rows:
        split = r.get("step_cost_split") or {}
        totals = split.get("totals") or {}
        probe_on = (r.get("observer") or {}).get("probe")
        if probe_on is None:
            probe_on = split.get("probe_enabled")
        body.append(
            (
                "on" if probe_on else "off",
                str(r.get("seed")),
                f"{float(totals.get('propagation_ms') or 0.0):.1f}",
                f"{float(totals.get('svid_reissue_ms') or 0.0):.1f}",
                f"{float(totals.get('probe_ms') or 0.0):.1f}",
                f"{float(totals.get('other_ms') or 0.0):.1f}",
                f"{float(totals.get('boundary_ms') or 0.0):.1f}",
                f"{float(split.get('reconcile_error_pct') or 0.0):.2f}",
            )
        )
    return _md_lines(
        "| probe | seed | propagation (ms) | SVID reissue (ms) | probe (ms) | other (ms) | boundary (ms) | reconcile % |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        body or [(_EMDASH, _EMDASH, _EMDASH, _EMDASH, _EMDASH, _EMDASH, _EMDASH, _EMDASH)],
    )


def emit_redeclaration_markdown(results: list[dict[str, Any]]) -> str:
    rows = _redeclaration_results(results)
    return "\n".join(
        [
            "# Re-declaration cost (M4 Q4)",
            "",
            source_caption(rows, "redeclaration"),
            "",
            table_redeclaration(results),
            "",
        ]
    )


def emit_redeclaration_latex(results: list[dict[str, Any]]) -> str:
    rows = _redeclaration_results(results)
    costs = [float(r.get("redeclaration_cost_ms") or 0.0) for r in rows]
    body = [
        (
            str(r.get("seed")),
            f"{float(r.get('redeclaration_cost_ms') or 0.0):.1f}",
            str(int(r.get("steps_reexecuted") or 0)),
            "yes" if r.get("writes_committed_before_termination") else "no",
        )
        for r in sorted(rows, key=lambda x: int(x.get("seed") or 0))
    ]
    return (
        _tex_tabular(
            rows,
            "Re-declaration",
            "rrrl",
            r"seed & cost (ms) & steps re-executed & writes committed",
            body,
        )
        + f"\n% median redeclaration_cost_ms = {_median(costs):.1f}\n"
    )


def emit_step_split_markdown(results: list[dict[str, Any]]) -> str:
    rows = _step_split_results(results)
    return "\n".join(
        [
            "# Per-step cost split (M4 Q4 / G8)",
            "",
            source_caption(rows, "step-split"),
            "",
            table_step_split(results),
            "",
            "Columns are totals over step boundaries. `other` is residual after SVID reissue, policy propagation, and probe. Sums must reconcile with observed boundary duration within 5%.",
            "",
        ]
    )


def emit_step_split_latex(results: list[dict[str, Any]]) -> str:
    rows = _step_split_results(results)
    body = []
    for r in sorted(
        rows,
        key=lambda x: (
            0 if (x.get("observer") or {}).get("probe", True) else 1,
            int(x.get("seed") or 0),
        ),
    ):
        split = r.get("step_cost_split") or {}
        totals = split.get("totals") or {}
        probe_on = (r.get("observer") or {}).get("probe")
        if probe_on is None:
            probe_on = split.get("probe_enabled")
        body.append(
            (
                "on" if probe_on else "off",
                str(r.get("seed")),
                f"{float(totals.get('propagation_ms') or 0.0):.1f}",
                f"{float(totals.get('svid_reissue_ms') or 0.0):.1f}",
                f"{float(totals.get('probe_ms') or 0.0):.1f}",
                f"{float(totals.get('other_ms') or 0.0):.1f}",
                f"{float(totals.get('boundary_ms') or 0.0):.1f}",
                f"{float(split.get('reconcile_error_pct') or 0.0):.2f}",
            )
        )
    return _tex_tabular(
        rows,
        "Step cost split",
        "lrrrrrrr",
        r"probe & seed & prop (ms) & SVID (ms) & probe (ms) & other (ms) & boundary (ms) & err \%",
        body,
    )


def emit_markdown(results: list[dict[str, Any]]) -> str:
    parts = [
        "# Manuscript tables",
        "",
        source_caption(results, "all tables"),
        "",
        "## Reach",
        "",
        source_caption(results, "Reach"),
        "",
        table_reach(results),
        "",
        "## Rollback",
        "",
        source_caption(results, "Rollback"),
        "",
        table_rollback(results),
        "",
        "## Overhead",
        "",
        source_caption(results, "Overhead"),
        "",
        table_overhead(results),
        "",
        "## Credentials (Q2)",
        "",
        source_caption(results, "Credentials"),
        "",
        table_credentials(results),
        "",
        "## Segment p/q/d (Q4)",
        "",
        source_caption(results, "Segment"),
        "",
        table_segment(results),
        "",
        "## Step granularity",
        "",
        source_caption(results, "Step"),
        "",
        table_step(results),
        "",
        "## Dispersion (M6)",
        "",
        source_caption(_task_results(results), "Dispersion"),
        "",
        table_dispersion(results),
        "",
        "Median [IQR]; bootstrap 95% CI for the median, 1000 resamples, seed 26.",
        "",
        "## Sweep (k/|S|)",
        "",
        source_caption(_sweep_results(results), "Sweep"),
        "",
        table_sweep(results),
        "",
        "## Q2 series",
        "",
        source_caption(results, "Q2"),
        "",
        "| seed | mode | \\|S\\| | declared | extra |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    for row in q2_series(results):
        parts.append(
            f"| {row['seed']} | {row['mode']} | {row['reachable_set_size']} | {row['declared']} | {row['extra']} |"
        )
    return "\n".join(parts) + "\n"


def emit_latex(results: list[dict[str, Any]]) -> str:
    """LaTeX-ready tabular rows for the manuscript. Same numbers as emit_markdown."""
    parts = [
        "% Manuscript tables (LaTeX-ready rows from make paper-tables)",
        f"% {source_caption(results, 'all tables').strip('*')}",
        "% Paste into Paper 1 tabulars. Simulator/fixture numbers must not be used.",
        "",
        _tex_tabular(
            results,
            "Reach",
            "lrrrrrr",
            r"mode & $n$ & mean $|S|$ & min & max & mean extra & mean $R_w$",
            _reach_rows(results),
        ),
        "",
        _tex_tabular(
            results,
            "Rollback",
            "llrrr",
            r"mode & class & mean $\rho_{\mathrm{rev}}$ & mean $n$ & mean restored/quarantined/escalated",
            _rollback_rows(results),
        ),
        "",
        _tex_tabular(
            results,
            "Overhead",
            "lrrr",
            r"mode & $n$ & mean verify\_ms & mean relative vs same-seed flat",
            _overhead_rows(results),
        ),
        "",
        _tex_tabular(
            results,
            "Credentials",
            "lrrrr",
            r"mode & $n$ & mean $\tau$ (s) & mean $T$ (s) & mean $\tau/T$",
            _credentials_rows(results),
        ),
        "",
        _tex_tabular(
            results,
            "Segment",
            "lrrrrr",
            r"mode & $n$ & mean $p$ (ms) & mean $q$ (ms) & mean $d$ (ms) & max $d$ (ms)",
            _segment_rows(results),
        ),
        "",
        _tex_tabular(
            results,
            "Step",
            "rrrrr",
            r"seed & mean $\tau/T$ & max $\tau/T$ & mean $d$ (ms) & max $d$ (ms)",
            _step_rows(results),
        ),
        "",
        _tex_tabular(
            _task_results(results),
            "Dispersion",
            "llrrr",
            r"mode & metric & $n$ & median [IQR] & bootstrap 95\% CI",
            _dispersion_rows(results),
        ),
        "",
        _tex_tabular(
            results,
            "Q2 series",
            "rlrrr",
            r"seed & mode & $|S|$ & declared & extra",
            _q2_rows(results),
        ),
        "",
        _tex_tabular(
            results,
            "Sweep",
            "rrrrrrr",
            r"$k$ & $n$ & mean $|R|$ & min $|R|$ & max $|R|$ & mean $R_w$ & mean $|B \cap R|$",
            _sweep_summary_rows(results),
        ),
        "",
        _tex_tabular(
            results,
            "Sweep seeds",
            "lrrrrr",
            r"variant & seed & $k$ & $|R|$ & $R_w$ & $|B \cap R|$",
            _sweep_seed_rows(results),
        ),
        "",
    ]
    return "\n".join(parts)


def emit_sweep_markdown(results: list[dict[str, Any]]) -> str:
    sweep = _sweep_results(results)
    parts = [
        "# Declaration tightness sweep (Section 7.4)",
        "",
        source_caption(sweep, "Sweep"),
        "",
        "## k vs |R| vs R_w",
        "",
        source_caption(sweep, "Sweep summary"),
        "",
        table_sweep(results),
        "",
    ]
    return "\n".join(parts)


def emit_sweep_latex(results: list[dict[str, Any]]) -> str:
    sweep = _sweep_results(results)
    parts = [
        "% Declaration tightness sweep (Section 7.4) from make paper-tables TABLE=sweep",
        f"% {source_caption(sweep, 'Sweep').strip('*')}",
        "",
        _tex_tabular(
            sweep,
            "Sweep",
            "rrrrrrr",
            r"$k$ & $n$ & mean $|R|$ & min $|R|$ & max $|R|$ & mean $R_w$ & mean $|B \cap R|$",
            _sweep_summary_rows(results),
        ),
        "",
        _tex_tabular(
            sweep,
            "Sweep seeds",
            "lrrrrr",
            r"variant & seed & $k$ & $|R|$ & $R_w$ & $|B \cap R|$",
            _sweep_seed_rows(results),
        ),
        "",
    ]
    return "\n".join(parts)


def emit_data_intensive_markdown(results: list[dict[str, Any]]) -> str:
    rows = _data_intensive_results(results)
    parts = [
        "# Data-intensive profile (G4 / Q3 generality)",
        "",
        source_caption(rows, "data-intensive"),
        "",
        "## Rollback (per class)",
        "",
        source_caption(rows, "data-intensive rollback"),
        "",
        table_data_intensive_rollback(rows),
        "",
    ]
    return "\n".join(parts)


def emit_data_intensive_latex(results: list[dict[str, Any]]) -> str:
    rows = _data_intensive_results(results)
    parts = [
        "% Data-intensive profile (G4 / Q3 generality) from make paper-tables TABLE=data-intensive",
        f"% {source_caption(rows, 'data-intensive').strip('*')}",
        "",
        _tex_tabular(
            rows,
            "Data-intensive rollback",
            "llrrrrrr",
            r"mode & class & mean $\rho_{\mathrm{enum}}$ & mean $\rho_{\mathrm{rev}}$ & mean $n$ & mean $\rho_{\mathrm{quarantined}}$ & mean $\rho_{\mathrm{escalated}}$ & mean count",
            _data_intensive_rollback_rows(rows),
        ),
        "",
    ]
    return "\n".join(parts)


def write_q2_figure(results: list[dict[str, Any]], out_dir: Path) -> Path | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    series = q2_series(results)
    seeds = sorted({s["seed"] for s in series})
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    width = 0.35
    x = list(range(len(seeds)))
    for offset, mode in ((-width / 2, "flat"), (width / 2, "full")):
        ys = []
        for seed in seeds:
            match = [s for s in series if s["seed"] == seed and s["mode"] == mode]
            ys.append(match[0]["reachable_set_size"] if match else 0)
        ax.bar([i + offset for i in x], ys, width, label=mode)
    ax.set_title("Reachable set size by seed and mode")
    ax.set_xlabel("Seed")
    ax.set_ylabel("|S| (services)")
    ax.set_xticks(x, [str(s) for s in seeds])
    ax.legend()
    ax.set_ylim(0, 9)
    fig.tight_layout()
    fig.text(
        0.5,
        0.01,
        source_caption(results, "Q2 reachable-set figure").strip("*"),
        ha="center",
        fontsize=8,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "q2-reachable-set.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out", type=Path, default=ROOT / "analysis" / "output")
    parser.add_argument(
        "--format",
        choices=("markdown", "latex"),
        default="markdown",
        help="markdown for make analyse; latex for make paper-tables",
    )
    parser.add_argument(
        "--table",
        default="",
        help="optional table selector (sweep, evasion, data-intensive, gateway, redeclaration, step-split, dispersion). empty = Paper 1 headline tables",
    )
    args = parser.parse_args(argv)
    results = load_results(args.results)
    table = (args.table or "").strip().lower()
    if table == "sweep":
        gated = _sweep_results(results)
        if not gated:
            print("refusing sweep table: no variant=k{1,3,5,7} results", file=sys.stderr)
            return 1
    elif table == "evasion":
        gated = _evasion_results(results)
        if not gated:
            print("refusing evasion table: no result.json with evasion_matrix", file=sys.stderr)
            return 1
    elif table in ("data-intensive", "data_intensive"):
        gated = _data_intensive_results(results)
        if not gated:
            print("refusing data-intensive table: no profile=data-intensive results", file=sys.stderr)
            return 1
    elif table == "gateway":
        gated = _gateway_results(results)
        if not gated:
            print("refusing gateway table: no gateway-only/gateway-bypass results", file=sys.stderr)
            return 1
    elif table in ("redeclaration", "redecl"):
        gated = _redeclaration_results(results)
        if not gated:
            print("refusing redeclaration table: no profile=redeclaration results", file=sys.stderr)
            return 1
    elif table in ("step-split", "step_split", "split"):
        gated = _step_split_results(results)
        if not gated:
            print("refusing step-split table: no step_cost_split results", file=sys.stderr)
            return 1
    elif table in ("dispersion", "median", "iqr"):
        gated = [
            r
            for r in results
            if not _is_sweep(r)
            and not _is_data_intensive(r)
            and not _is_redeclaration(r)
            and not _is_step_split(r)
        ]
        if not gated:
            print("refusing dispersion table: no task or gateway results", file=sys.stderr)
            return 1
    elif table in ("", "all"):
        gated = [
            r
            for r in results
            if not _is_sweep(r)
            and not _is_data_intensive(r)
            and not _is_gateway(r)
            and not _is_redeclaration(r)
            and not _is_step_split(r)
        ]
    else:
        print(
            f"unknown TABLE={args.table!r} (supported: sweep, evasion, data-intensive, gateway, redeclaration, step-split, dispersion)",
            file=sys.stderr,
        )
        return 2
    try:
        assert_cluster_provenance(gated)
    except ProvenanceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    if table == "sweep":
        if args.format == "latex":
            text = emit_sweep_latex(results)
            out_path = args.out / "sweep.tex"
        else:
            text = emit_sweep_markdown(results)
            out_path = args.out / "sweep.md"
        out_path.write_text(text)
        print(text)
        print(f"wrote {out_path}")
        return 0
    if table == "evasion":
        if args.format == "latex":
            text = emit_evasion_latex(results)
            out_path = args.out / "evasion.tex"
        else:
            text = emit_evasion_markdown(results)
            out_path = args.out / "evasion.md"
        out_path.write_text(text)
        print(text)
        print(f"wrote {out_path}")
        return 0
    if table in ("data-intensive", "data_intensive"):
        if args.format == "latex":
            text = emit_data_intensive_latex(results)
            out_path = args.out / "data-intensive.tex"
        else:
            text = emit_data_intensive_markdown(results)
            out_path = args.out / "data-intensive.md"
        out_path.write_text(text)
        print(text)
        print(f"wrote {out_path}")
        return 0
    if table == "gateway":
        if args.format == "latex":
            text = emit_gateway_latex(results)
            out_path = args.out / "gateway.tex"
        else:
            text = emit_gateway_markdown(results)
            out_path = args.out / "gateway.md"
        out_path.write_text(text)
        print(text)
        print(f"wrote {out_path}")
        return 0
    if table in ("redeclaration", "redecl"):
        if args.format == "latex":
            text = emit_redeclaration_latex(results)
            out_path = args.out / "redeclaration.tex"
        else:
            text = emit_redeclaration_markdown(results)
            out_path = args.out / "redeclaration.md"
        out_path.write_text(text)
        print(text)
        print(f"wrote {out_path}")
        return 0
    if table in ("step-split", "step_split", "split"):
        if args.format == "latex":
            text = emit_step_split_latex(results)
            out_path = args.out / "step-split.tex"
        else:
            text = emit_step_split_markdown(results)
            out_path = args.out / "step-split.md"
        out_path.write_text(text)
        print(text)
        print(f"wrote {out_path}")
        return 0
    if table in ("dispersion", "median", "iqr"):
        if args.format == "latex":
            text = emit_dispersion_latex(results)
            out_path = args.out / "dispersion.tex"
        else:
            text = emit_dispersion_markdown(results)
            out_path = args.out / "dispersion.md"
        out_path.write_text(text)
        (args.out / "dispersion.json").write_text(json.dumps(dispersion_document(results), indent=2) + "\n")
        print(text)
        print(f"wrote {out_path}")
        return 0
    if args.format == "latex":
        text = emit_latex(results)
        out_path = args.out / "tables.tex"
        out_path.write_text(text)
        (args.out / "dispersion.json").write_text(json.dumps(dispersion_document(results), indent=2) + "\n")
        print(text)
        print(f"wrote {out_path}")
        return 0
    markdown = emit_markdown(results)
    (args.out / "tables.md").write_text(markdown)
    (args.out / "dispersion.json").write_text(json.dumps(dispersion_document(results), indent=2) + "\n")
    write_q2_figure(results, args.out)
    print(markdown)
    print(f"wrote {args.out / 'tables.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
