from __future__ import annotations

from pathlib import Path

from tables import emit_markdown, load_results, table_overhead, table_reach, table_rollback

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
