"""In-memory stores with the versioning/history the real stores expose."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Postgres:
    """Temporal-table pattern: live row + history of every change."""

    live: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def upsert(self, key: str, value: Any, task_id: str) -> dict[str, Any]:
        before = deepcopy(self.live.get(key))
        self.history.append(
            {"key": key, "before": before, "after": value, "op": "upsert", "task_id": task_id, "at": _now()}
        )
        self.live[key] = value
        return {"key": key, "before": before, "after": value}

    def insert(self, key: str, value: Any, task_id: str) -> dict[str, Any]:
        before = deepcopy(self.live.get(key))
        self.history.append(
            {"key": key, "before": before, "after": value, "op": "insert", "task_id": task_id, "at": _now()}
        )
        self.live[key] = value
        return {"key": key, "before": before, "after": value}

    def restore(self, key: str) -> Any:
        for row in reversed(self.history):
            if row["key"] == key:
                prior = deepcopy(row["before"])
                if prior is None:
                    self.live.pop(key, None)
                else:
                    self.live[key] = prior
                return prior
        return None


@dataclass
class Minio:
    objects: dict[str, Any] = field(default_factory=dict)
    versions: dict[str, list[Any]] = field(default_factory=dict)
    notifications: list[dict[str, Any]] = field(default_factory=list)

    def put(self, key: str, value: Any, task_id: str, overwrite: bool = False) -> dict[str, Any]:
        before = deepcopy(self.objects.get(key))
        self.versions.setdefault(key, [])
        if before is not None:
            self.versions[key].append(before)
        self.objects[key] = value
        event = {
            "event": "PUT",
            "key": key,
            "task_id": task_id,
            "overwrite": overwrite,
            "at": _now(),
        }
        self.notifications.append(event)
        return {"key": key, "before": before, "after": value}

    def restore(self, key: str) -> Any:
        versions = self.versions.get(key) or []
        if not versions:
            self.objects.pop(key, None)
            return None
        prior = versions.pop()
        self.objects[key] = prior
        return prior


@dataclass
class Qdrant:
    points: dict[str, Any] = field(default_factory=dict)
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    oplog: list[dict[str, Any]] = field(default_factory=list)
    quarantined: bool = False

    def snapshot(self) -> int:
        self.snapshots.append(deepcopy(self.points))
        return len(self.snapshots) - 1

    def upsert(self, key: str, value: Any, task_id: str) -> dict[str, Any]:
        before = deepcopy(self.points.get(key))
        self.points[key] = value
        self.oplog.append(
            {"op": "upsert", "key": key, "task_id": task_id, "before": before, "after": value}
        )
        return {"key": key, "before": before, "after": value}

    def delete(self, key: str, task_id: str) -> dict[str, Any]:
        before = self.points.pop(key, None)
        self.oplog.append(
            {"op": "delete", "key": key, "task_id": task_id, "before": before, "after": None}
        )
        return {"key": key, "before": before, "after": None}

    def restore_snapshot(self, index: int = -1) -> None:
        self.points = deepcopy(self.snapshots[index])
        self.quarantined = True


@dataclass
class NotifyLog:
    """Append-only external-effect log. No procedure reverses an append."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def append(self, key: str, value: Any, task_id: str) -> dict[str, Any]:
        row = {"key": key, "value": value, "task_id": task_id, "at": _now()}
        self.entries.append(row)
        return {"key": key, "before": None, "after": value}
