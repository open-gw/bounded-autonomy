"""Run driver: `python -m harness.driver --profile long-multistep --mode full --seed 1`."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from harness.simulator import run_local

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute one Paper 1 run")
    parser.add_argument("--profile", default="long-multistep")
    parser.add_argument("--mode", choices=("flat", "full"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--granularity",
        choices=("task", "step"),
        default=os.environ.get("GRANULARITY", "task"),
    )
    parser.add_argument(
        "--local",
        action="store_true",
        default=os.environ.get("BA_LOCAL", "") == "1",
        help="in-process simulator (used when the cluster is not up)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
    )
    args = parser.parse_args(argv)
    if args.profile != "long-multistep":
        raise SystemExit(f"unsupported profile {args.profile}")
    if args.granularity == "step":
        run_id = f"{args.profile}-{args.mode}-step-seed{args.seed}"
    else:
        run_id = f"{args.profile}-{args.mode}-seed{args.seed}"
    out = args.out or (ROOT / "runs" / "results" / run_id)

    baseline = None
    if args.mode == "full":
        flat_spans = ROOT / "runs" / "results" / f"{args.profile}-flat-seed{args.seed}" / "spans.parquet"
        if flat_spans.exists():
            baseline = pd.read_parquet(flat_spans)

    # Cluster driver is Task 11; the simulator is the always-available path
    # and is what `make run` uses until kubeconfig points at a live rig.
    kube = os.environ.get("KUBECONFIG") or str(Path.home() / ".kube" / "config")
    use_local = args.local or not Path("/tmp/ba-cluster-up").exists()
    if not use_local:
        from harness.cluster_driver import run_cluster

        result = run_cluster(
            mode=args.mode,
            seed=args.seed,
            out_dir=out,
            baseline_spans=baseline,
            granularity=args.granularity,
        )
    else:
        result = run_local(
            mode=args.mode,
            seed=args.seed,
            out_dir=out,
            injection=True,
            baseline_spans=baseline,
            granularity=args.granularity,
            task_id=run_id,
        )
    print(f"wrote {out / 'result.json'} reachable={result['metrics']['reachable_set_size']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
