"""Ground-truth row shape. Cluster consumers write the same columns."""

from __future__ import annotations

from typing import Any


def record(
    *,
    task_id: str,
    step: int,
    store: str,
    operation: str,
    write_class: str,
    key: str,
    before: Any,
    after: Any,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "step": step,
        "store": store,
        "operation": operation,
        "write_class": write_class,
        "key": key,
        "before": before,
        "after": after,
    }
