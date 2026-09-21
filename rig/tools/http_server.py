"""HTTP front for a single MCP tool. Used in-cluster; tests use tools.dispatch."""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from lineage.emitter import emit_run_event
from observer.otel import force_flush, tracer
from tools.dispatch import AudienceDenied, verify_audience

app = FastAPI()
TOOL_NAME = os.environ.get("TOOL_NAME", "records")
DECLARED = ["records", "search", "notify"]
_TRACER = None


def _tracer():
    global _TRACER
    if _TRACER is None:
        _TRACER = tracer(TOOL_NAME)
    return _TRACER


class Call(BaseModel):
    operation: str
    key: str
    value: Any = None
    step: int


@app.post("/tools/call")
def call(
    body: Call,
    x_spiffe_id: str = Header(default=""),
    x_rig_mode: str = Header(default="full"),
    x_task_id: str = Header(default=""),
) -> dict:
    if not x_spiffe_id:
        raise HTTPException(401, "missing presented SVID")
    mode = x_rig_mode if x_rig_mode in ("flat", "full") else "full"
    tr = _tracer()
    with tr.start_as_current_span("verify") as span:
        span.set_attribute("mode", mode)
        span.set_attribute("task_id", x_task_id or "")
        span.set_attribute("tool", TOOL_NAME)
        t0 = time.perf_counter()
        verify = verify_audience(
            mode=mode, tool=TOOL_NAME, declared=DECLARED, spiffe_id=x_spiffe_id
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        span.set_attribute("audience_ok", bool(verify["audience_ok"]))
        span.set_attribute("verify_ms", elapsed_ms)
    if not verify["audience_ok"]:
        force_flush()
        raise HTTPException(403, str(AudienceDenied(TOOL_NAME, x_spiffe_id)))
    store = {
        "records": "postgres",
        "docs": "minio",
        "search": "qdrant",
        "notify": "notify-log",
    }[TOOL_NAME]
    event = emit_run_event(
        spiffe_id=x_spiffe_id,
        step=body.step,
        store=store,
        operation=body.operation,
        is_write=True,
        dataset=f"{TOOL_NAME}.{body.key}",
    )
    force_flush()
    return {"ok": True, "verify": verify, "lineage": event, "verify_ms": elapsed_ms}


def main() -> None:
    global TOOL_NAME
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    TOOL_NAME = args.name
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
