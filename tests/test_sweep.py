"""Task 27: declaration-tightness sweep. Answers known by construction."""

from __future__ import annotations

from pathlib import Path

from harness.simulator import run_local
from plan import build_step_plan
from sweep import INJECTION_SERVICE, VARIANTS, declared_weight
from tables import emit_sweep_latex, emit_sweep_markdown, table_sweep
from weights import reachable_weight


def test_step_plan_uses_only_declared_tools():
    for variant, declared in VARIANTS.items():
        plan = build_step_plan(1, declared=declared)
        assert {step.tool for step in plan} <= set(declared)
        assert all(step.tool in declared for step in plan)
        if variant == "k1":
            assert {step.tool for step in plan} == {"records"}


def test_declared_weights_match_frozen_table():
    assert declared_weight("k1") == 3
    assert declared_weight("k3") == 7
    assert declared_weight("k5") == 9
    assert declared_weight("k7") == 11
    assert INJECTION_SERVICE == "docs"
    for declared in VARIANTS.values():
        assert INJECTION_SERVICE not in declared


def test_local_full_sweep_acceptance(tmp_path: Path):
    for variant, declared in VARIANTS.items():
        result = run_local(
            mode="full",
            seed=1,
            out_dir=tmp_path / variant,
            injection=True,
            declared=declared,
            variant=variant,
            breach_services=[INJECTION_SERVICE],
        )
        reached = result["metrics"]["reachable_services"]
        assert result["variant"] == variant
        assert result["declaration"]["declared_count"] == len(declared)
        assert result["metrics"]["reachable_set_size"] == len(declared)
        assert set(reached) == set(declared)
        assert result["metrics"]["reachable_weight"] == reachable_weight(declared)
        assert result["metrics"]["breach_intersection_size"] == 0
        assert INJECTION_SERVICE not in reached


def test_table_sweep_rows(tmp_path: Path):
    results = []
    for variant, declared in VARIANTS.items():
        for seed in (1, 2):
            result = run_local(
                mode="full",
                seed=seed,
                out_dir=tmp_path / f"{variant}-seed{seed}",
                injection=True,
                declared=declared,
                variant=variant,
                breach_services=[INJECTION_SERVICE],
            )
            results.append(result)
    md = table_sweep(results)
    assert "| 1 |" in md and "3.000" in md
    assert "| 7 |" in md and "11.000" in md
    assert "0.000" in md
    text = emit_sweep_markdown(results)
    assert "Declaration tightness" in text
    tex = emit_sweep_latex(results)
    assert r"$k$" in tex and r"$R_w$" in tex
