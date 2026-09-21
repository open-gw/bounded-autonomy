"""OpenLineage-shaped events. Task facet comes from the presented SVID only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from lineage.write_classes import write_class as class_for


def spiffe_task_id(spiffe_id: str) -> str:
    prefix = "spiffe://rig/task/"
    if not spiffe_id.startswith(prefix):
        raise ValueError(f"task facet refuses non-task SPIFFE id: {spiffe_id}")
    return spiffe_id[len(prefix) :]


def emit_run_event(
    *,
    spiffe_id: str,
    step: int,
    store: str,
    operation: str,
    is_write: bool,
    dataset: str,
    producer: str = "bounded-autonomy/tool",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one RunEvent. `spiffe_id` is the presented SVID, not a header."""
    task_id = spiffe_task_id(spiffe_id)
    wclass = class_for(store, operation) if is_write else None
    event = {
        "eventType": "COMPLETE",
        "eventTime": datetime.now(timezone.utc).isoformat(),
        "run": {
            "runId": str(uuid4()),
            "facets": {
                "task": {
                    "_producer": producer,
                    "_schemaURL": "https://bounded-autonomy.io/facets/task",
                    "task_id": task_id,
                    "step": step,
                    "write_class": wclass,
                }
            },
        },
        "job": {"namespace": "rig", "name": f"{store}.{operation}"},
        "inputs": [],
        "outputs": [{"namespace": "rig", "name": dataset}] if is_write else [],
        "producer": producer,
        "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json",
        "store": store,
        "operation": operation,
        "is_write": is_write,
        "write_class": wclass,
        "task_id": task_id,
        "step": step,
        "spiffe_id": spiffe_id,
    }
    if extra:
        event.update(extra)
    return event
