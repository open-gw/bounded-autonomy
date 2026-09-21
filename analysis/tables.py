"""Emit the three manuscript tables from result.json files.

Used by `make analyse` and by analysis/notebook.ipynb.
"""

from __future__ import annotations

import argparse
import json
import os
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


def _task_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in results
        if (r.get("declaration") or {}).get("granularity", "task") == "task"
    ]


def assert_cluster_provenance(results: list[dict[str, Any]]) -> None:
    """Refuse manuscript tables unless every result is from the cluster
    and verify-span durations actually vary (not the in-process constants).

    Also refuse leftover Tempo traces: a SIGTERM'd retry that reused
    ``task_id`` can ingest verify spans from the killed attempt, so the
    count must not exceed ``steps_completed`` (default 30 if missing).
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
        if n_verify > cap:
            bad.append(
                f"{path}: verify-span count {n_verify} exceeds steps_completed={cap}"
            )
    if not bad:
        return
    lines = [
        "refusing manuscript tables: every result.json must have source=cluster",
        "and verify-span durations with non-zero variance",
        "and verify-span count ≤ steps_completed (leftover Tempo traces)",
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


def table_reach(results: list[dict[str, Any]]) -> str:
    results = _task_results(results)
    lines = [
        "| mode | n | mean \\|S\\| | min | max | mean extra | mean R_w |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, rows in sorted(_by_mode(results).items()):
        sizes = [int(r["metrics"]["reachable_set_size"]) for r in rows]
        declared_n = [len(r["declaration"]["services"]) for r in rows]
        extra = [s - d for s, d in zip(sizes, declared_n)]
        weights = [int(r["metrics"].get("reachable_weight") or 0) for r in rows]
        lines.append(
            f"| {mode} | {len(rows)} | {_mean(sizes):.3f} | {min(sizes)} | {max(sizes)} | {_mean(extra):.3f} | {_mean(weights):.3f} |"
        )
    return "\n".join(lines)


def table_rollback(results: list[dict[str, Any]]) -> str:
    results = _task_results(results)
    # Paper 1 reports rollback from full (segmented) drifted runs; flat is listed for contrast.
    lines = [
        "| mode | class | mean rho_rev | mean n | mean restored/quarantined/escalated |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for mode, rows in sorted(_by_mode(results).items()):
        rb = [r["metrics"]["rollback_completeness"] for r in rows]
        for cls, extra_key in (
            ("idempotent", "restored"),
            ("versioned", "restored"),
            ("derived", "quarantined"),
            ("irreversible", "escalated"),
        ):
            rhos = [c[cls]["rho_rev"] for c in rb if c[cls]["rho_rev"] is not None]
            ns = [c[cls]["n"] for c in rb]
            extras = [c[cls][extra_key] for c in rb]
            rho_txt = "—" if not rhos else f"{_mean(rhos):.3f}"
            lines.append(
                f"| {mode} | {cls} | {rho_txt} | {_mean(ns):.1f} | {_mean(extras):.1f} |"
            )
    return "\n".join(lines)


def table_overhead(results: list[dict[str, Any]]) -> str:
    results = _task_results(results)
    lines = [
        "| mode | n | mean verify_ms | mean relative vs same-seed flat |",
        "| --- | ---: | ---: | ---: |",
    ]
    flat_by_seed = {
        r["seed"]: r
        for r in results
        if r["mode"] == "flat"
    }
    for mode, rows in sorted(_by_mode(results).items()):
        verify = [float(r["metrics"]["verification_overhead"]["verify_ms"]) for r in rows]
        relatives: list[float] = []
        for r in rows:
            rel = r["metrics"]["verification_overhead"].get("relative")
            if rel is None and r["seed"] in flat_by_seed and mode != "flat":
                t = r["metrics"]["verification_overhead"]["total_ms"]
                b = flat_by_seed[r["seed"]]["metrics"]["verification_overhead"]["total_ms"]
                rel = None if b == 0 else (t - b) / b
            if mode == "flat":
                rel = 0.0
            if rel is not None:
                relatives.append(float(rel))
        rel_txt = "—" if not relatives else f"{_mean(relatives):.4f}"
        lines.append(
            f"| {mode} | {len(rows)} | {_mean(verify):.1f} | {rel_txt} |"
        )
    return "\n".join(lines)


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


def table_credentials(results: list[dict[str, Any]]) -> str:
    results = _task_results(results)
    lines = [
        "| mode | n | mean τ (s) | mean T (s) | mean τ/T |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for mode, rows in sorted(_by_mode(results).items()):
        tau = [float(r["metrics"]["tau_seconds"]) for r in rows if r["metrics"].get("tau_seconds") is not None]
        tsec = [float(r["metrics"]["T_seconds"]) for r in rows if r["metrics"].get("T_seconds") is not None]
        ratio = [float(r["metrics"]["credential_ratio"]) for r in rows if r["metrics"].get("credential_ratio") is not None]
        lines.append(
            f"| {mode} | {len(rows)} | {_mean(tau):.3f} | {_mean(tsec):.3f} | {_mean(ratio):.3f} |"
        )
    return "\n".join(lines)


def table_segment(results: list[dict[str, Any]]) -> str:
    results = _task_results(results)
    lines = [
        "| mode | n | mean p (ms) | mean q (ms) | mean d (ms) | max d (ms) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, rows in sorted(_by_mode(results).items()):
        p = [float(r["metrics"]["segment_p_ms"]) for r in rows if r["metrics"].get("segment_p_ms") is not None]
        q = [float(r["metrics"]["segment_q_ms"]) for r in rows if r["metrics"].get("segment_q_ms") is not None]
        dmean = [float(r["metrics"]["d_ms_mean"]) for r in rows if r["metrics"].get("d_ms_mean") is not None]
        dmax = [float(r["metrics"]["d_ms_max"]) for r in rows if r["metrics"].get("d_ms_max") is not None]
        lines.append(
            f"| {mode} | {len(rows)} | {_mean(p):.1f} | {_mean(q):.1f} | {_mean(dmean):.1f} | {_mean(dmax):.1f} |"
        )
    return "\n".join(lines)


def table_step(results: list[dict[str, Any]]) -> str:
    rows = [
        r
        for r in results
        if (r.get("declaration") or {}).get("granularity") == "step"
    ]
    lines = [
        "| seed | mean τ/T | max τ/T | mean d (ms) | max d (ms) |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    if not rows:
        lines.append("| — | — | — | — | — |")
        return "\n".join(lines)
    for r in sorted(rows, key=lambda x: x["seed"]):
        m = r["metrics"]
        lines.append(
            f"| {r['seed']} | {m.get('step_ratio_mean'):.3f} | {m.get('step_ratio_max'):.3f} | "
            f"{m.get('d_ms_mean'):.1f} | {m.get('d_ms_max'):.1f} |"
        )
    return "\n".join(lines)


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
    args = parser.parse_args(argv)
    results = load_results(args.results)
    try:
        assert_cluster_provenance(results)
    except ProvenanceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    markdown = emit_markdown(results)
    (args.out / "tables.md").write_text(markdown)
    write_q2_figure(results, args.out)
    print(markdown)
    print(f"wrote {args.out / 'tables.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
