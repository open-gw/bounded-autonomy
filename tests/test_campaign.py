from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT / "rig"))

from campaign import (  # noqa: E402
    expand_jobs,
    is_complete,
    job_run_id,
    parse_granularities,
    parse_modes,
    parse_seeds,
    provenance_ok,
)


def test_parse_seeds_range_and_list():
    assert parse_seeds("1-10") == list(range(1, 11))
    assert parse_seeds("1,3,5") == [1, 3, 5]
    assert parse_seeds("6-10,1") == [6, 7, 8, 9, 10, 1]


def test_parse_modes_full_bypass():
    assert ("full", True) in parse_modes("flat,gateway-only,gateway-bypass,full,full+bypass")
    assert parse_modes("full+bypass") == [("full", True)]
    assert parse_modes("all")[0] == ("flat", False)


def test_job_run_ids():
    assert job_run_id("long-multistep", "full", 2, "task", True) == "long-multistep-full-bypass-seed2"
    assert job_run_id("long-multistep", "gateway-only", 10, "task", False) == (
        "long-multistep-gateway-only-seed10"
    )
    assert job_run_id("long-multistep", "full", 7, "step", False) == "long-multistep-full-step-seed7"


def test_expand_jobs_fifty_plus_ten():
    modes = parse_modes("flat,gateway-only,gateway-bypass,full,full+bypass")
    task = expand_jobs("long-multistep", modes, parse_seeds("1-10"), ["task"])
    step = expand_jobs("long-multistep", modes, parse_seeds("1-10"), ["step"])
    assert len(task) == 50
    assert len(step) == 10
    assert all(j["granularity"] == "step" and j["mode"] == "full" and not j["gateway_bypass"] for j in step)
    both = expand_jobs("long-multistep", modes, parse_seeds("1-10"), parse_granularities("task,step"))
    assert len(both) == 60


def test_resume_skips_complete_cluster_result(tmp_path: Path):
    import pandas as pd

    run = tmp_path / "long-multistep-flat-seed9"
    run.mkdir()
    (run / "result.json").write_text(
        json.dumps(
            {
                "run_id": "long-multistep-flat-seed9",
                "source": "cluster",
                "mode": "flat",
                "seed": 9,
                "steps_completed": 30,
                "declaration": {"granularity": "task", "services": ["records", "search", "notify"]},
            }
        )
    )
    pd.DataFrame(
        [{"name": "verify", "duration_ms": float(i + 1)} for i in range(30)]
    ).to_parquet(run / "spans.parquet", index=False)
    assert is_complete(run)
    ok, _ = provenance_ok(run / "result.json")
    assert ok


def test_resume_retries_simulator_or_bad_provenance(tmp_path: Path):
    run = tmp_path / "long-multistep-full-seed9"
    run.mkdir()
    (run / "result.json").write_text(
        json.dumps({"run_id": "x", "source": "simulator", "mode": "full", "steps_completed": 30})
    )
    assert is_complete(run) is False


def test_resume_retries_superseded(tmp_path: Path):
    import pandas as pd

    run = tmp_path / "long-multistep-full-seed1"
    run.mkdir()
    (run / "result.json").write_text(
        json.dumps(
            {
                "run_id": "long-multistep-full-seed1",
                "source": "cluster",
                "mode": "full",
                "seed": 1,
                "steps_completed": 30,
                "superseded_by": "task31",
                "declaration": {"granularity": "task", "services": ["records", "search", "notify"]},
            }
        )
    )
    pd.DataFrame(
        [{"name": "verify", "duration_ms": float(i + 1)} for i in range(29)]
    ).to_parquet(run / "spans.parquet", index=False)
    assert is_complete(run) is False


def test_parse_rejects_empty_and_unknown():
    with pytest.raises(ValueError):
        parse_seeds("")
    with pytest.raises(ValueError):
        parse_modes("kong")
    with pytest.raises(ValueError):
        parse_granularities("pod")
