"""Task 29: data-intensive profile, three-store plan, M1 ordering."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from harness.simulator import run_local
from plan import THREE_STORE_DECLARED, build_step_plan, counts_from_mix
from profiles import profile_spec
from rollback.procedures import rollback_task
from stores.memory import Minio, NotifyLog, Postgres, Qdrant
from validate_manifest import extra_errors, load_inventory, validate_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "runs" / "manifests" / "data-intensive-full.yaml"


def test_data_intensive_mix_is_4_6_8_2():
    spec = profile_spec("data-intensive")
    mix = spec["write_mix"]
    assert counts_from_mix(mix, 20) == {
        "idempotent": 4,
        "versioned": 6,
        "derived": 8,
        "irreversible": 2,
    }
    for seed in range(1, 11):
        plan = build_step_plan(
            seed,
            steps=20,
            write_mix=mix,
            declared=THREE_STORE_DECLARED,
            three_store=True,
        )
        assert len(plan) == 20
        counts = Counter(s.write_class for s in plan)
        assert counts["idempotent"] == 4
        assert counts["versioned"] == 6
        assert counts["derived"] == 8
        assert counts["irreversible"] == 2
        tools = {s.tool for s in plan}
        assert {"records", "docs", "search", "notify"} <= tools


def test_data_intensive_manifest_validates():
    assert validate_manifest(MANIFEST) == []


def test_data_intensive_wrong_mix_fails():
    import yaml

    doc = yaml.safe_load(MANIFEST.read_text())
    doc["spec"]["write_mix"]["derived"] = 0.2
    doc["spec"]["write_mix"]["idempotent"] = 0.4
    errors = extra_errors(doc, load_inventory())
    assert any("write_mix" in e for e in errors)


def test_m1_later_write_is_dependent_not_reversed():
    """Later legitimate overwrite of a drifted row is reported, not reverted."""
    pg, s3, qd, nlog = Postgres(), Minio(), Qdrant(), NotifyLog()
    qd.snapshot()
    pg.upsert("shared-row", {"v": "orig"}, "t")
    drift = pg.upsert("shared-row", {"v": "DRIFT"}, "t")
    later = pg.upsert("shared-row", {"v": "later-ok"}, "t")
    assert later["before"] == {"v": "DRIFT"}

    events = [
        {
            "step": 1,
            "is_write": True,
            "write_class": "idempotent",
            "store": "postgres",
            "key": "shared-row",
            "drifted": False,
        },
        {
            "step": 3,
            "is_write": True,
            "write_class": "idempotent",
            "store": "postgres",
            "key": "shared-row",
            "drifted": True,
        },
        {
            "step": 8,
            "is_write": False,
            "is_read": True,
            "write_class": None,
            "store": "postgres",
            "key": "shared-row",
        },
        {
            "step": 8,
            "is_write": True,
            "write_class": "idempotent",
            "store": "postgres",
            "key": "shared-row",
            "drifted": False,
        },
    ]
    gt = [
        {
            "step": 1,
            "store": "postgres",
            "key": "shared-row",
            "write_class": "idempotent",
            "before": None,
            "after": {"v": "orig"},
        },
        {
            "step": 3,
            "store": "postgres",
            "key": "shared-row",
            "write_class": "idempotent",
            "before": {"v": "orig"},
            "after": {"v": "DRIFT"},
        },
        {
            "step": 8,
            "store": "postgres",
            "key": "shared-row",
            "write_class": "idempotent",
            "before": {"v": "DRIFT"},
            "after": {"v": "later-ok"},
        },
    ]
    attest = rollback_task(
        events=events,
        groundtruth=gt,
        postgres=pg,
        minio=s3,
        qdrant=qd,
        notify=nlog,
    )
    by_step = {int(a["step"]): a for a in attest}
    assert by_step[8]["action"] == "dependent"
    assert by_step[8]["procedure"] == "M1-dependent-write"
    assert by_step[8].get("reversed") is False
    assert by_step[3]["action"] == "skipped_dependent"
    assert pg.live["shared-row"] == {"v": "later-ok"}
    assert drift["after"] == {"v": "DRIFT"}


def test_local_data_intensive_m1_when_step3_is_row_store(tmp_path: Path):
    spec = profile_spec("data-intensive")
    hit = None
    for seed in range(1, 11):
        plan = build_step_plan(
            seed,
            steps=20,
            write_mix=spec["write_mix"],
            declared=THREE_STORE_DECLARED,
            three_store=True,
        )
        if plan[2].tool in ("records", "docs"):
            hit = seed
            break
    assert hit is not None
    result = run_local(
        mode="full",
        seed=hit,
        out_dir=tmp_path / "m1",
        injection=True,
        profile="data-intensive",
    )
    import json

    attest = json.loads((tmp_path / "m1" / "attestation.json").read_text())
    assert any(row.get("action") == "dependent" for row in attest)
    assert result["metrics"]["rho_enum"] == 1.0


def test_local_data_intensive_full(tmp_path: Path):
    result = run_local(
        mode="full",
        seed=1,
        out_dir=tmp_path / "di",
        injection=True,
        profile="data-intensive",
    )
    assert result["profile"] == "data-intensive"
    assert result["steps_completed"] == 20
    counts = result["write_counts"]
    assert abs(counts["idempotent"] - 4) <= 1
    assert abs(counts["versioned"] - 6) <= 1
    assert abs(counts["derived"] - 8) <= 1
    assert abs(counts["irreversible"] - 2) <= 1
    stores = set()
    import json

    attest = json.loads((tmp_path / "di" / "attestation.json").read_text())
    stores = {row["store"] for row in attest}
    assert {"postgres", "minio", "qdrant"} <= stores
    rb = result["metrics"]["rollback_completeness"]
    assert rb["irreversible"]["rho_escalated"] == 1.0
    assert result["metrics"]["rho_enum"] == 1.0
    schema = json.loads((ROOT / "schemas" / "result.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
    actions = {row["action"] for row in attest}
    if "dependent" not in actions:
        assert rb["derived"]["rho_quarantined"] == 1.0
        assert rb["derived"]["quarantined"] == rb["derived"]["n"]
