from __future__ import annotations

from pathlib import Path

from tables import (
    ProvenanceError,
    assert_cluster_provenance,
    emit_evasion_latex,
    emit_gateway_latex,
    emit_latex,
    emit_markdown,
    load_results,
    main as analyse_main,
    source_caption,
    table_evasion,
    table_gateway,
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


def test_emit_latex_on_synthetic_fixtures():
    from build_fixtures import main as build

    build()
    results = load_results(FIXTURES)
    tex = emit_latex(results)
    assert r"\begin{tabular}" in tex
    assert r"mean $|S|$" in tex
    assert "8.000" in tex and "3.000" in tex
    assert "idempotent" in tex and "1.000" in tex
    assert r"\textemdash{}" in tex
    assert "source=simulator" in tex
    md = emit_markdown(results)
    assert "8.000" in table_reach(results)
    assert "3.000" in md


def test_paper_tables_refuses_simulator_fixtures(tmp_path):
    from build_fixtures import main as build

    build()
    rc = analyse_main(
        ["--results", str(FIXTURES), "--out", str(tmp_path), "--format", "latex"]
    )
    assert rc == 1
    assert not (tmp_path / "tables.tex").exists()


def test_paper_tables_refuses_leftover_verify_spans(tmp_path):
    _cluster_run(tmp_path, "leftover-run", "full", 58)
    rc = analyse_main(
        ["--results", str(tmp_path), "--out", str(tmp_path / "out"), "--format", "latex"]
    )
    assert rc == 1
    assert not (tmp_path / "out" / "tables.tex").exists()


def test_paper_tables_writes_tex_on_cluster_results(tmp_path):
    import json

    for name, mode, n_verify in (("full-run", "full", 29), ("flat-run", "flat", 30)):
        run_dir = _cluster_run(tmp_path / mode, name, mode, n_verify)
        doc = json.loads((run_dir / "result.json").read_text())
        size = 3 if mode == "full" else 8
        doc["metrics"] = {
            "reachable_set_size": size,
            "reachable_weight": 7 if mode == "full" else 14,
            "tau_seconds": 1.0,
            "T_seconds": 1.0,
            "credential_ratio": 1.0,
            "segment_p_ms": 0.0,
            "segment_q_ms": 0.0,
            "d_ms_mean": 1.0,
            "d_ms_max": 1.0,
            "rollback_completeness": {
                "idempotent": {"rho_rev": 1.0, "n": 12, "restored": 12},
                "versioned": {"rho_rev": 1.0, "n": 9, "restored": 9},
                "derived": {"rho_rev": None, "n": 6, "quarantined": 6},
                "irreversible": {"rho_rev": 0.0, "n": 3, "escalated": 3},
            },
            "verification_overhead": {"verify_ms": 2.0, "total_ms": 100.0, "relative": 0.0},
        }
        (run_dir / "result.json").write_text(json.dumps(doc))
    rc = analyse_main(
        ["--results", str(tmp_path), "--out", str(tmp_path / "out"), "--format", "latex"]
    )
    assert rc == 0
    tex = (tmp_path / "out" / "tables.tex").read_text()
    assert r"\begin{tabular}" in tex
    assert "% --- Reach ---" in tex
    assert "source=cluster" in tex


def test_paper_tables_sweep_writes_tex(tmp_path):
    import json

    run_dir = _cluster_run(tmp_path, "long-multistep-k1-full-seed1", "full", 29)
    doc = json.loads((run_dir / "result.json").read_text())
    doc["variant"] = "k1"
    doc["declaration"] = {
        "granularity": "task",
        "services": ["records"],
        "declared_count": 1,
        "variant": "k1",
    }
    doc["metrics"] = {
        "reachable_set_size": 1,
        "reachable_weight": 3,
        "breach_intersection_size": 0,
        "tau_seconds": 1.0,
        "T_seconds": 1.0,
        "credential_ratio": 1.0,
        "segment_p_ms": 0.0,
        "segment_q_ms": 0.0,
        "d_ms_mean": 1.0,
        "d_ms_max": 1.0,
        "rollback_completeness": {
            "idempotent": {"rho_rev": 1.0, "n": 12, "restored": 12},
            "versioned": {"rho_rev": 1.0, "n": 9, "restored": 9},
            "derived": {"rho_rev": None, "n": 6, "quarantined": 6},
            "irreversible": {"rho_rev": 0.0, "n": 3, "escalated": 3},
        },
        "verification_overhead": {"verify_ms": 2.0, "total_ms": 100.0, "relative": 0.0},
    }
    (run_dir / "result.json").write_text(json.dumps(doc))
    rc = analyse_main(
        [
            "--results",
            str(tmp_path),
            "--out",
            str(tmp_path / "out"),
            "--format",
            "latex",
            "--table",
            "sweep",
        ]
    )
    assert rc == 0
    tex = (tmp_path / "out" / "sweep.tex").read_text()
    assert r"$k$" in tex
    assert "source=cluster" in tex
    assert not (tmp_path / "out" / "tables.tex").exists()


def _evasion_matrix(mode: str) -> list[dict]:
    if mode == "full":
        verdicts = ["allowed"] + ["refused"] * 8
    else:
        verdicts = [
            "allowed", "allowed", "allowed", "allowed",
            "host-refused", "host-refused", "allowed", "allowed", "allowed",
        ]
    probes = [
        "direct_ip_declared",
        "direct_ip_undeclared",
        "dns_coredns_undeclared",
        "dns_udp53_external",
        "external_https",
        "node_metadata",
        "kubernetes_api_name",
        "kubernetes_api_ip",
        "kubelet",
    ]
    return [
        {"row": i + 1, "probe": probes[i], "verdict": verdicts[i], "latency_ms": 1.0}
        for i in range(9)
    ]


def test_paper_tables_evasion(tmp_path):
    import json

    for name, mode, n_verify in (("full-run", "full", 29), ("flat-run", "flat", 30)):
        run_dir = _cluster_run(tmp_path / mode, name, mode, n_verify)
        doc = json.loads((run_dir / "result.json").read_text())
        doc["evasion_matrix"] = _evasion_matrix(mode)
        doc["artefacts"] = {"evasion": "evasion.parquet"}
        (run_dir / "result.json").write_text(json.dumps(doc))
    rc = analyse_main(
        [
            "--results",
            str(tmp_path),
            "--out",
            str(tmp_path / "out"),
            "--format",
            "latex",
            "--table",
            "evasion",
        ]
    )
    assert rc == 0
    tex = (tmp_path / "out" / "evasion.tex").read_text()
    assert "% --- Evasion ---" in tex
    assert "source=cluster" in tex
    assert "allowed (1/1)" in tex
    md = table_evasion(load_results(tmp_path))
    assert "| 1 |" in md and "direct-IP" in md
    assert "host-refused" in md
    assert "1.1.1.1" in emit_evasion_latex(load_results(tmp_path)) or "external" in md


def test_caption_n_uses_selector_not_tree_size(tmp_path):
    """Default captions print the selector n, never the full results-tree n."""
    import json

    for i in range(3):
        _cluster_run(tmp_path / "task", f"task-full-{i}", "full", 29)
        doc = json.loads((tmp_path / "task" / f"task-full-{i}" / "result.json").read_text())
        doc["metrics"] = {
            "reachable_set_size": 3,
            "reachable_weight": 7,
            "tau_seconds": 1.0,
            "T_seconds": 1.0,
            "credential_ratio": 1.0,
            "segment_p_ms": 1.0,
            "segment_q_ms": 1.0,
            "d_ms_mean": 1.0,
            "d_ms_max": 1.0,
            "rollback_completeness": {
                "idempotent": {"rho_rev": 1.0, "n": 1, "restored": 1},
                "versioned": {"rho_rev": 1.0, "n": 1, "restored": 1},
                "derived": {"rho_rev": None, "n": 1, "quarantined": 1},
                "irreversible": {"rho_rev": 0.0, "n": 1, "escalated": 1},
            },
            "verification_overhead": {"verify_ms": 1.0, "relative": 0.0, "total_ms": 1.0, "absolute_seconds": 0.001},
        }
        doc["declaration"] = {"granularity": "task", "services": ["records", "search", "notify"]}
        doc["seed"] = i + 1
        (tmp_path / "task" / f"task-full-{i}" / "result.json").write_text(json.dumps(doc))
    for i in range(2):
        _cluster_run(tmp_path / "sweep", f"sweep-k1-{i}", "full", 29)
        doc = json.loads((tmp_path / "sweep" / f"sweep-k1-{i}" / "result.json").read_text())
        doc["variant"] = "k1"
        doc["declaration"] = {"granularity": "task", "services": ["records"], "variant": "k1"}
        doc["metrics"] = {
            "reachable_set_size": 1,
            "reachable_weight": 3,
            "breach_intersection_size": 0,
            "tau_seconds": 1.0,
            "T_seconds": 1.0,
            "credential_ratio": 1.0,
            "segment_p_ms": 1.0,
            "segment_q_ms": 1.0,
            "d_ms_mean": 1.0,
            "d_ms_max": 1.0,
            "rollback_completeness": {
                "idempotent": {"rho_rev": 1.0, "n": 1, "restored": 1},
                "versioned": {"rho_rev": 1.0, "n": 1, "restored": 1},
                "derived": {"rho_rev": None, "n": 1, "quarantined": 1},
                "irreversible": {"rho_rev": 0.0, "n": 1, "escalated": 1},
            },
            "verification_overhead": {"verify_ms": 1.0, "relative": 0.0, "total_ms": 1.0, "absolute_seconds": 0.001},
        }
        doc["seed"] = i + 1
        (tmp_path / "sweep" / f"sweep-k1-{i}" / "result.json").write_text(json.dumps(doc))
    results = load_results(tmp_path)
    assert len(results) == 5
    tex = emit_latex(results)
    assert "n=97" not in tex
    assert "Caption: Reach. source=cluster (n=3)." in tex
    assert "Caption: Q2 series. source=cluster (n=3)." in tex
    assert "Caption: Sweep. source=cluster (n=2)." in tex
    md = emit_markdown(results)
    assert "n=97" not in md
    assert "source=cluster (n=3)" in md


def test_evasion_mixed_cell_does_not_collapse_to_five_of_ten():
    rows = []
    for seed, verdict in enumerate(["refused"] * 5 + ["error"] * 5, start=1):
        rows.append(
            {
                "mode": "full",
                "seed": seed,
                "declaration": {"granularity": "task"},
                "evasion_matrix": [
                    {"row": 3, "probe": "dns_coredns_undeclared", "verdict": verdict, "latency_ms": 1.0}
                ],
            }
        )
        rows.append(
            {
                "mode": "flat",
                "seed": seed,
                "declaration": {"granularity": "task"},
                "evasion_matrix": [
                    {"row": 3, "probe": "dns_coredns_undeclared", "verdict": "allowed", "latency_ms": 1.0}
                ],
            }
        )
    md = table_evasion(rows)
    assert "refused (5/10)" not in md
    assert "error 5" in md and "refused 5" in md
    tex = emit_evasion_latex(rows)
    assert "refused (5/10)" not in tex


def test_gateway_403_column(tmp_path):
    import json

    run_dir = _cluster_run(tmp_path, "gw-only", "gateway-only", 30)
    doc = json.loads((run_dir / "result.json").read_text())
    doc["mode"] = "gateway-only"
    doc["metrics"] = {
        "reachable_set_size": 8,
        "breach_intersection_size": 1,
        "gateway_403": 2,
    }
    (run_dir / "result.json").write_text(json.dumps(doc))
    md = table_gateway(load_results(tmp_path))
    assert "gateway_403" in md
    assert "| 2 |" in md
    tex = emit_gateway_latex(load_results(tmp_path))
    assert r"gateway\_403" in tex
    assert " 2 " in tex or "& 2 &" in tex
