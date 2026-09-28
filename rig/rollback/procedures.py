"""Per-class rollback procedures and attestation.

M1 (ordering): a later legitimate write that read a row after a drifted
write is a *dependent write*. Report it; do not revert it silently.
Qdrant quarantine is per task (one snapshot restore), not per collection.
"""

from __future__ import annotations

from typing import Any, Iterable

from stores.memory import Minio, NotifyLog, Postgres, Qdrant


def _key_of(event: dict[str, Any], gt: dict[str, Any]) -> str:
    return str(gt.get("key") or event.get("key") or f"step-{event['step']}")


def _store_key(store: str, key: str) -> tuple[str, str]:
    return (str(store), str(key))


def drifted_keys(
    events: Iterable[dict[str, Any]],
    groundtruth: Iterable[dict[str, Any]],
) -> set[tuple[str, str]]:
    """Keys written by a drifted/injected step."""
    gt_by_step = {int(g["step"]): g for g in groundtruth}
    out: set[tuple[str, str]] = set()
    for event in events:
        if not (event.get("is_write") and event.get("drifted")):
            continue
        gt = gt_by_step.get(int(event["step"]), {})
        out.add(_store_key(event.get("store") or gt.get("store"), _key_of(event, gt)))
    return out


def dependent_write_steps(
    events: list[dict[str, Any]],
    groundtruth: list[dict[str, Any]],
) -> set[int]:
    """Later writes whose key was read after a drifted write (M1).

    A write is dependent when read lineage (or the write's own ``before``)
    shows the row was observed after the drifted write to the same key.
    """
    drifted = drifted_keys(events, groundtruth)
    if not drifted:
        return set()
    gt_by_step = {int(g["step"]): g for g in groundtruth}
    first_drift_step: dict[tuple[str, str], int] = {}
    for event in events:
        if not (event.get("is_write") and event.get("drifted")):
            continue
        gt = gt_by_step.get(int(event["step"]), {})
        sk = _store_key(event.get("store") or gt.get("store"), _key_of(event, gt))
        step = int(event["step"])
        prev = first_drift_step.get(sk)
        if prev is None or step < prev:
            first_drift_step[sk] = step

    reads_after_drift: set[tuple[str, str]] = set()
    dependent: set[int] = set()
    ordered = sorted(events, key=lambda e: (int(e["step"]), 0 if e.get("is_read") else 1))
    for event in ordered:
        step = int(event["step"])
        gt = gt_by_step.get(step, {})
        store = str(event.get("store") or gt.get("store") or "")
        key = _key_of(event, gt)
        sk = _store_key(store, key)
        drift_at = first_drift_step.get(sk)
        if drift_at is None:
            continue
        is_read = bool(event.get("is_read")) or (
            event.get("is_write") and gt.get("before") is not None
        )
        if is_read and step > drift_at:
            reads_after_drift.add(sk)
        if (
            event.get("is_write")
            and not event.get("drifted")
            and step > drift_at
            and sk in drifted
            and sk in reads_after_drift
        ):
            dependent.add(step)
    return dependent


def rollback_task(
    *,
    events: list[dict[str, Any]],
    groundtruth: list[dict[str, Any]],
    postgres: Postgres,
    minio: Minio,
    qdrant: Qdrant,
    notify: NotifyLog,
) -> list[dict[str, Any]]:
    """Enumerate lineage writes for a task, order by step, apply procedures."""
    writes = sorted(
        [e for e in events if e.get("is_write")],
        key=lambda e: int(e["step"]),
    )
    gt_by_step = {int(g["step"]): g for g in groundtruth}
    dependent = dependent_write_steps(events, groundtruth)
    protected_keys = {
        _store_key(
            (gt_by_step.get(step) or {}).get("store")
            or next((e.get("store") for e in writes if int(e["step"]) == step), ""),
            (gt_by_step.get(step) or {}).get("key")
            or next((e.get("key") for e in writes if int(e["step"]) == step), f"step-{step}"),
        )
        for step in dependent
    }
    attestation: list[dict[str, Any]] = []
    # Quarantine per task, not per collection: one snapshot restore.
    qdrant_restored = False
    for event in reversed(writes):
        cls = event["write_class"]
        store = event["store"]
        gt = gt_by_step.get(int(event["step"]), {})
        key = _key_of(event, gt)
        sk = _store_key(store, key)
        record: dict[str, Any] = {
            "step": event["step"],
            "store": store,
            "write_class": cls,
            "key": key,
            "ground_truth_before": gt.get("before"),
            "procedure": cls,
            "quarantine_scope": "task" if cls == "derived" else None,
        }
        if int(event["step"]) in dependent:
            record.update(
                {
                    "action": "dependent",
                    "dependent": True,
                    "reversed": False,
                    "procedure": "M1-dependent-write",
                }
            )
            attestation.append(record)
            continue
        if sk in protected_keys:
            # A later dependent write owns this row; restoring would clobber it.
            record.update(
                {
                    "action": "skipped_dependent",
                    "reversed": False,
                    "procedure": "M1-dependent-write",
                }
            )
            attestation.append(record)
            continue
        if cls in ("idempotent", "versioned"):
            if store == "postgres":
                restored = postgres.restore(key)
            elif store == "minio":
                restored = minio.restore(key)
            else:
                restored = None
            matches = restored == gt.get("before")
            record.update(
                {
                    "action": "restored",
                    "restored": restored,
                    "matches_before": matches,
                    "reversed": True,
                }
            )
        elif cls == "derived":
            if not qdrant_restored:
                if qdrant.snapshots:
                    qdrant.restore_snapshot(-1)
                qdrant_restored = True
            record.update(
                {
                    "action": "quarantined",
                    "quarantined": True,
                    "quarantine_scope": "task",
                }
            )
        else:
            record.update({"action": "escalated", "escalated": True})
        attestation.append(record)
    attestation.sort(key=lambda r: int(r["step"]))
    return attestation
