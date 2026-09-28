"""Run driver: `python -m harness.driver --profile long-multistep --mode full --seed 1`."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from harness.simulator import run_local
from modes import ALL_MODES, run_id_for

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute one Paper 1 run")
    parser.add_argument("--profile", default="long-multistep")
    parser.add_argument("--mode", choices=ALL_MODES, required=True)
    parser.add_argument(
        "--gateway-bypass",
        action="store_true",
        default=os.environ.get("GATEWAY_BYPASS", "") in ("1", "true", "yes"),
        help="deploy the APISIX allow-list but send agent calls to ClusterIP",
    )
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
    parser.add_argument(
        "--variant",
        choices=("k1", "k3", "k5", "k7"),
        default=os.environ.get("VARIANT") or None,
        help="declaration-tightness variant (Task 27 k/|S| sweep)",
    )
    probe_env = os.environ.get("PROBE", os.environ.get("OBSERVER_PROBE", "1"))
    parser.add_argument(
        "--probe",
        dest="probe",
        action="store_true",
        default=probe_env not in ("0", "false", "no", "off"),
        help="reachable-set TCP probe (default on)",
    )
    parser.add_argument(
        "--no-probe",
        dest="probe",
        action="store_false",
        help="observer.probe=false; reachable set from flows only",
    )
    parser.add_argument(
        "--step-split",
        action="store_true",
        default=os.environ.get("STEP_SPLIT", "") in ("1", "true", "yes"),
        help="time SVID / propagation / probe per step boundary",
    )
    args = parser.parse_args(argv)
    if args.profile not in ("long-multistep", "data-intensive", "redeclaration"):
        raise SystemExit(f"unsupported profile {args.profile}")
    variant = args.variant or None
    probe_enabled = args.probe
    step_split = args.step_split
    if variant:
        run_id = f"{args.profile}-{variant}-{args.mode}-seed{args.seed}"
    else:
        run_id = run_id_for(
            profile=args.profile,
            mode=args.mode,
            seed=args.seed,
            granularity=args.granularity,
            gateway_bypass=args.gateway_bypass,
            probe=probe_enabled,
            step_split=step_split,
        )
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
            variant=variant,
            profile=args.profile,
            gateway_bypass=args.gateway_bypass,
            probe_enabled=probe_enabled,
            step_split=step_split,
        )
    else:
        from profiles import profile_spec
        from sweep import INJECTION_SERVICE, declared_services

        spec = profile_spec(args.profile)
        declared = declared_services(variant) if variant else spec["declared"]
        breach = [INJECTION_SERVICE] if variant else [spec["injection_service"]]
        result = run_local(
            mode=args.mode,
            seed=args.seed,
            out_dir=out,
            injection=spec.get("injection_enabled", True),
            baseline_spans=baseline,
            granularity=args.granularity,
            task_id=run_id,
            declared=declared,
            variant=variant,
            breach_services=breach,
            profile=args.profile,
            gateway_bypass=args.gateway_bypass,
            probe_enabled=probe_enabled,
            step_split=step_split,
        )
    print(f"wrote {out / 'result.json'} reachable={result['metrics']['reachable_set_size']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
