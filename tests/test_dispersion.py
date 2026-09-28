from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tables import (
    BOOTSTRAP_RESAMPLES,
    emit_latex,
    emit_markdown,
    median_iqr_ci,
    table_dispersion,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "dispersion.schema.json").read_text())


def test_median_iqr_and_bootstrap_reproducible():
    values = [1.0, 2.0, 3.0, 4.0, 100.0]
    a = median_iqr_ci(values)
    b = median_iqr_ci(values)
    assert a == b
    assert a["n"] == 5
    assert a["median"] == 3.0
    assert a["q1"] == 2.0
    assert a["q3"] == 4.0
    assert a["iqr"] == 2.0
    assert a["resamples"] == BOOTSTRAP_RESAMPLES == 1000
    assert a["ci95_low"] <= a["median"] <= a["ci95_high"]
    Draft202012Validator(SCHEMA).validate(a)


def test_constant_sample_has_degenerate_ci():
    stat = median_iqr_ci([3.0] * 10)
    assert stat["median"] == 3.0
    assert stat["q1"] == 3.0
    assert stat["q3"] == 3.0
    assert stat["ci95_low"] == 3.0
    assert stat["ci95_high"] == 3.0


def test_emit_tables_include_median_iqr():
    from build_fixtures import main as build

    build()
    results_dir = ROOT / "analysis" / "fixtures" / "results"
    from tables import load_results

    results = load_results(results_dir)
    md = emit_markdown(results)
    tex = emit_latex(results)
    disp = table_dispersion(results)
    assert "## Dispersion (M6)" in md
    assert "median [IQR]" in md
    assert "bootstrap 95% CI" in md
    assert "median [IQR]" in tex
    assert r"bootstrap 95\% CI" in tex
    assert "| full |" in disp and "| flat |" in disp
