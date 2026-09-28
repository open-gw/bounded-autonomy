"""In-pod (or kubectl-exec) HTTP calls to tool services plus the OTel root span."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from observer.otel import force_flush, tracer
from plan import DEFAULT_DECLARED, build_step_plan
from profiles import profile_spec
from agent.orchestrator import pick_from_injection, pick_tool
from harness.payloads import load_payload
from modes import ALL_MODES, GATEWAY_HOST, GATEWAY_PORT, uses_gateway_path

SERVICE_PORTS = {
    "records": 8081,
    "docs": 8082,
    "search": 8083,
    "notify": 8084,
    "billing": 8085,
    "analytics": 8086,
    "audit": 8087,
    "catalog": 8088,
}


def call_tool(
    *,
    tool: str,
    operation: str,
    key: str,
    value: object,
    step: int,
    mode: str,
    task_id: str,
    spiffe_id: str,
    timeout: float = 1.0,  # connect+read; CNP-dropped injection must not wait 5s
    gateway_bypass: bool = False,
) -> dict:
    port = SERVICE_PORTS[tool]
    if uses_gateway_path(mode, gateway_bypass):
        url = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}/{tool}/tools/call"
    else:
        url = f"http://{tool}:{port}/tools/call"
    body = json.dumps(
        {"operation": operation, "key": key, "value": value, "step": step}
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-SPIFFE-ID": spiffe_id,
            "X-Rig-Mode": mode,
            "X-Task-Id": task_id,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": exc.read().decode()}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def run_steps(
    *,
    mode: str,
    seed: int,
    task_id: str,
    spiffe_id: str,
    only_step: int | None = None,
    from_step: int | None = None,
    until_step: int | None = None,
    with_root: bool = True,
    declared: list[str] | None = None,
    profile: str = "long-multistep",
    gateway_bypass: bool = False,
) -> dict:
    spec = profile_spec(profile)
    declared = list(declared) if declared is not None else list(spec["declared"])
    plan = build_step_plan(
        seed,
        steps=spec["steps"],
        write_mix=spec["write_mix"],
        declared=list(spec["declared"]),
        three_store=spec["three_store"],
        redeclare_at=spec.get("redeclare_at"),
        redeclare_tool=spec.get("redeclare_tool") or "docs",
    )
    payload = load_payload(spec["payload_version"], seed)
    inject_step = spec["injection_at"]
    inject = spec.get("injection_enabled", True)
    tr = tracer("agent")
    start = time.time()
    start_ns = time.time_ns()
    outcomes: list[dict] = []
    last_result: dict | None = None
    first_call_epoch: float | None = None
    span_cm = tr.start_as_current_span("run", start_time=start_ns) if with_root else None
    span = span_cm.__enter__() if span_cm else None
    if span is not None:
        span.set_attribute("mode", mode)
        span.set_attribute("task_id", task_id)
    try:
        for step in plan:
            if only_step is not None and step.index != only_step:
                continue
            if from_step is not None and step.index < from_step:
                continue
            if until_step is not None and step.index > until_step:
                break
            tool = pick_tool(step.instruction, declared, last_result)
            operation = step.operation
            key = f"{step.write_class}-{step.index}"
            value: object = {"step": step.index, "seed": seed}
            if inject and step.index == inject_step:
                if spec.get("three_store"):
                    key = "shared-row"
                    value = {"injected": True, "seed": seed, "drifted": True}
                else:
                    tool = pick_from_injection(payload, declared)
                    operation = payload.get("operation", "put")
                    key = "blast/radius.json"
                    value = {"injected": True, "seed": seed}
            if first_call_epoch is None:
                first_call_epoch = time.time()
            out = call_tool(
                tool=tool,
                operation=operation,
                key=key,
                value=value,
                step=step.index,
                mode=mode,
                task_id=task_id,
                spiffe_id=spiffe_id,
                gateway_bypass=gateway_bypass,
            )
            last_result = out if out.get("ok") else {"denied": True, "tool": tool}
            outcomes.append({"step": step.index, "tool": tool, "ok": bool(out.get("ok"))})
    finally:
        if span is not None:
            span.end(end_time=time.time_ns())
            span_cm.__exit__(None, None, None)
    force_flush()
    end = time.time()
    return {
        "task_id": task_id,
        "mode": mode,
        "seed": seed,
        "start_epoch": start,
        "end_epoch": end,
        "first_call_epoch": first_call_epoch,
        "outcomes": outcomes,
        "started_at": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "finished_at": datetime.fromtimestamp(end, timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=ALL_MODES, required=True)
    parser.add_argument("--gateway-bypass", action="store_true")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--spiffe-id", required=True)
    parser.add_argument("--only-step", type=int, default=None)
    parser.add_argument("--from-step", type=int, default=None)
    parser.add_argument("--until-step", type=int, default=None)
    parser.add_argument("--no-root", action="store_true")
    parser.add_argument(
        "--declared",
        default=",".join(DEFAULT_DECLARED),
        help="comma-separated declared services; step plan uses only these tools",
    )
    parser.add_argument("--profile", default="long-multistep")
    args = parser.parse_args(argv)
    declared = [name.strip() for name in args.declared.split(",") if name.strip()]
    print(json.dumps(run_steps(
        mode=args.mode,
        seed=args.seed,
        task_id=args.task_id,
        spiffe_id=args.spiffe_id,
        only_step=args.only_step,
        from_step=args.from_step,
        until_step=args.until_step,
        with_root=not args.no_root,
        declared=declared,
        profile=args.profile,
        gateway_bypass=args.gateway_bypass,
    )))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
