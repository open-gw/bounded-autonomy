"""MCP-shaped tool dispatch. Audience check lives here so verify spans wrap it."""

from __future__ import annotations

from typing import Any

from lineage.emitter import emit_run_event
from lineage.write_classes import write_class
from stores.memory import Minio, NotifyLog, Postgres, Qdrant

TOOL_STORE = {
    "records": ("postgres", Postgres),
    "docs": ("minio", Minio),
    "search": ("qdrant", Qdrant),
    "notify": ("notify-log", NotifyLog),
}


class AudienceDenied(Exception):
    def __init__(self, tool: str, spiffe_id: str):
        super().__init__(f"audience check failed for {tool} from {spiffe_id}")
        self.tool = tool
        self.spiffe_id = spiffe_id


class SegmentDenied(Exception):
    def __init__(self, tool: str):
        super().__init__(f"segment denies connect to {tool}")
        self.tool = tool


class GatewayDenied(Exception):
    def __init__(self, tool: str):
        super().__init__(f"gateway uri-blocker 403 for {tool}")
        self.tool = tool
        self.status = 403


def verify_audience(*, mode: str, tool: str, declared: list[str], spiffe_id: str) -> dict:
    """Return a verify-span payload. L7 audience is a no-op unless mode is full."""
    ok = True if mode != "full" else tool in declared
    return {
        "name": "verify",
        "mode": mode,
        "tool": tool,
        "audience_ok": ok,
        "spiffe_id": spiffe_id,
    }


def dispatch(
    *,
    tool: str,
    operation: str,
    key: str,
    value: Any,
    step: int,
    spiffe_id: str,
    mode: str,
    declared: list[str],
    postgres: Postgres,
    minio: Minio,
    qdrant: Qdrant,
    notify: NotifyLog,
    can_connect: bool,
    lineage_enabled: bool = True,
) -> dict[str, Any]:
    verify = verify_audience(mode=mode, tool=tool, declared=declared, spiffe_id=spiffe_id)
    if not can_connect:
        raise SegmentDenied(tool)
    if not verify["audience_ok"]:
        raise AudienceDenied(tool, spiffe_id)

    store_name, _ = TOOL_STORE[tool]
    if tool == "records":
        fn = postgres.upsert if operation == "upsert" else postgres.insert
        result = fn(key, value, _task(spiffe_id))
    elif tool == "docs":
        result = minio.put(key, value, _task(spiffe_id), overwrite=operation == "put_overwrite")
    elif tool == "search":
        fn = qdrant.upsert if operation == "upsert" else qdrant.delete
        result = fn(key, value, _task(spiffe_id)) if operation == "upsert" else qdrant.delete(key, _task(spiffe_id))
    elif tool == "notify":
        result = notify.append(key, value, _task(spiffe_id))
    else:
        raise KeyError(tool)

    wclass = write_class(store_name, operation)
    event = None
    if lineage_enabled:
        event = emit_run_event(
            spiffe_id=spiffe_id,
            step=step,
            store=store_name,
            operation=operation,
            is_write=True,
            dataset=f"{store_name}.{key}",
        )
    return {
        "result": result,
        "verify": verify,
        "lineage": event,
        "write_class": wclass,
        "store": store_name,
        "operation": operation,
        "key": key,
        "before": result.get("before"),
        "after": result.get("after"),
    }


def _task(spiffe_id: str) -> str:
    return spiffe_id.rsplit("/", 1)[-1]
