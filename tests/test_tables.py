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


def _cluster_run(tmp_path: Path, name: str, mode: str, n_verify: int, duration_fn=None):
    import pandas as pd

    run_dir = tmp_path / name
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text(
        f'{{"run_id":"{name}","source":"cluster","mode":"{mode}","seed":2,'
        '"steps_completed":30,"declaration":{"granularity":"task","services":["records","search","notify"]}}'
    )
    fn = duration_fn or (lambda i: float(i + 1))
    pd.DataFrame(
        [
            {"name": "verify", "duration_ms": fn(i), "task_id": name}
            for i in range(n_verify)
        ]
    ).to_parquet(run_dir / "spans.parquet", index=False)
    return run_dir


def test_analyse_refuses_leftover_verify_spans(tmp_path):
    _cluster_run(tmp_path, "leftover-run", "full", 58)
    results = load_results(tmp_path)
    try:
        assert_cluster_provenance(results)
        raise AssertionError("expected ProvenanceError")
    except ProvenanceError as exc:
        msg = str(exc)
        assert "verify-span count 58 exceeds steps_completed=30" in msg
        assert "leftover Tempo traces" in msg


def test_analyse_refuses_missing_verify_spans(tmp_path):
    _cluster_run(tmp_path, "missing-run", "flat", 17)
    results = load_results(tmp_path)
    try:
        assert_cluster_provenance(results)
        raise AssertionError("expected ProvenanceError")
    except ProvenanceError as exc:
        msg = str(exc)
        assert "verify-span count 17" in msg
        assert "missing traces" in msg or "flat requires" in msg


def test_analyse_refuses_full_below_floor(tmp_path):
    _cluster_run(tmp_path, "missing-full", "full", 17)
    results = load_results(tmp_path)
    try:
        assert_cluster_provenance(results)
        raise AssertionError("expected ProvenanceError")
    except ProvenanceError as exc:
        msg = str(exc)
        assert "verify-span count 17 below steps_completed-1=29" in msg
        assert "missing traces" in msg


def test_analyse_accepts_full_one_short_and_flat_exact(tmp_path):
    _cluster_run(tmp_path / "full", "full-run", "full", 29)
    _cluster_run(tmp_path / "flat", "flat-run", "flat", 30)
    assert_cluster_provenance(load_results(tmp_path / "full"))
    assert_cluster_provenance(load_results(tmp_path / "flat"))


def test_analyse_refuses_zero_variance_verify_spans(tmp_path):
    _cluster_run(tmp_path, "const-run", "full", 29, duration_fn=lambda _i: 1.0)
    results = load_results(tmp_path)
    try:
        assert_cluster_provenance(results)
        raise AssertionError("expected ProvenanceError")
    except ProvenanceError as exc:
        assert "zero variance" in str(exc)
