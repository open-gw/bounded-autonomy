from __future__ import annotations

from pathlib import Path

from tables import (
    ProvenanceError,
    assert_cluster_provenance,
    emit_markdown,
    load_results,
    main as analyse_main,
    source_caption,
    table_overhead,
    table_reach,
    table_rollback,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "analysis" / "fixtures" / "results"


def test_tables_on_synthetic_fixtures(tmp_path, monkeypatch):
    from build_fixtures import main as build

    build()
    results = load_results(FIXTURES)
    assert len(results) == 10
    reach = table_reach(results)
    rollback = table_rollback(results)
    overhead = table_overhead(results)
    assert "| full |" in reach and "3.000" in reach
    assert "| flat |" in reach and "8.000" in reach
    assert "idempotent" in rollback and "1.000" in rollback
    assert "derived" in rollback
    assert "verify_ms" in overhead
    md = emit_markdown(results)
    assert "## Reach" in md and "## Rollback" in md and "## Overhead" in md
    assert "source=simulator" in md


def test_analyse_refuses_simulator_fixtures(tmp_path):
    from build_fixtures import main as build

    build()
    rc = analyse_main(["--results", str(FIXTURES), "--out", str(tmp_path)])
    assert rc == 1
    results = load_results(FIXTURES)
    try:
        assert_cluster_provenance(results)
        raise AssertionError("expected ProvenanceError")
    except ProvenanceError as exc:
        assert "source=cluster" in str(exc)
        assert "simulator" in str(exc)
    assert "source=simulator" in source_caption(results, "Reach")


def test_analyse_refuses_leftover_verify_spans(tmp_path):
    run_dir = tmp_path / "leftover-run"
    run_dir.mkdir()
    (run_dir / "result.json").write_text(
        '{"run_id":"leftover-run","source":"cluster","mode":"full","seed":2,'
        '"steps_completed":30,"declaration":{"granularity":"step","services":["records","search","notify"]}}'
    )
    import pandas as pd

    pd.DataFrame(
        [
            {"name": "verify", "duration_ms": float(i), "task_id": "leftover-run"}
            for i in range(58)
        ]
    ).to_parquet(run_dir / "spans.parquet", index=False)
    results = load_results(tmp_path)
    try:
        assert_cluster_provenance(results)
        raise AssertionError("expected ProvenanceError")
    except ProvenanceError as exc:
        msg = str(exc)
        assert "verify-span count 58 exceeds steps_completed=30" in msg
        assert "leftover Tempo traces" in msg
