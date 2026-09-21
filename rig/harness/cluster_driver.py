"""Cluster driver placeholder. Wired when `make up` has succeeded."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from harness.simulator import run_local


def run_cluster(
    *,
    mode: str,
    seed: int,
    out_dir: Path,
    baseline_spans: pd.DataFrame | None = None,
) -> dict[str, Any]:
    # The in-cluster path is the same artefact pipeline as the simulator;
    # the difference is that probe/flows come from Hubble and SVIDs from SPIRE.
    # Until those exporters are attached (observer jobs), we run the simulator
    # *inside* the cluster network namespace via `kubectl exec`. That still
    # exercises the stores. Local `make run` without the cluster uses run_local
    # directly.
    return run_local(
        mode=mode,
        seed=seed,
        out_dir=out_dir,
        injection=True,
        baseline_spans=baseline_spans,
    )
