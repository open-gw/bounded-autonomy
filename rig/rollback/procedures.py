"""Per-class rollback procedures and attestation."""

from __future__ import annotations

from typing import Any

from stores.memory import Minio, NotifyLog, Postgres, Qdrant


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
    attestation: list[dict[str, Any]] = []
    # Restore derived stores once from the pre-task snapshot.
    qdrant_restored = False
    for event in reversed(writes):
        cls = event["write_class"]
        store = event["store"]
        gt = gt_by_step.get(int(event["step"]), {})
        key = gt.get("key") or f"step-{event['step']}"
        record: dict[str, Any] = {
            "step": event["step"],
            "store": store,
            "write_class": cls,
            "key": key,
            "ground_truth_before": gt.get("before"),
        }
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
                }
            )
        elif cls == "derived":
            if not qdrant_restored:
                if qdrant.snapshots:
                    qdrant.restore_snapshot(-1)
                qdrant_restored = True
            record.update({"action": "quarantined", "quarantined": True})
        else:
            record.update({"action": "escalated", "escalated": True})
        attestation.append(record)
    attestation.sort(key=lambda r: int(r["step"]))
    return attestation
