"""HTTP front for a single MCP tool. Used in-cluster; tests use tools.dispatch."""

from __future__ import annotations

import argparse
import json
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from lineage.emitter import emit_run_event
from tools.dispatch import AudienceDenied, verify_audience

app = FastAPI()
TOOL_NAME = "records"
MODE = "full"
DECLARED = ["records", "search", "notify"]


class Call(BaseModel):
    operation: str
    key: str
    value: Any = None
    step: int


@app.post("/tools/call")
def call(
    body: Call,
    x_spiffe_id: str = Header(default=""),
) -> dict:
    if not x_spiffe_id:
        raise HTTPException(401, "missing presented SVID")
    verify = verify_audience(
        mode=MODE, tool=TOOL_NAME, declared=DECLARED, spiffe_id=x_spiffe_id
    )
    if not verify["audience_ok"]:
        raise HTTPException(403, str(AudienceDenied(TOOL_NAME, x_spiffe_id)))
    event = emit_run_event(
        spiffe_id=x_spiffe_id,
        step=body.step,
        store={"records": "postgres", "docs": "minio", "search": "qdrant", "notify": "notify-log"}[TOOL_NAME],
        operation=body.operation,
        is_write=True,
        dataset=f"{TOOL_NAME}.{body.key}",
    )
    return {"ok": True, "verify": verify, "lineage": event}


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
