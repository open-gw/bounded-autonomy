"""In-process run: same artefacts and metrics as the cluster driver."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agent.orchestrator import pick_from_injection, pick_tool
from harness.payloads import load_payload
from modes import deploys_gateway_policy, uses_flat_credential, uses_gateway_path, uses_segment
from plan import DEFAULT_DECLARED, build_step_plan
from profiles import profile_spec
from rollback.procedures import rollback_task
from stores.memory import Minio, NotifyLog, Postgres, Qdrant
from tools.dispatch import AudienceDenied, GatewayDenied, SegmentDenied, dispatch

INVENTORY = [
    "records",
    "docs",
    "search",
    "notify",
    "billing",
    "analytics",
    "audit",
    "catalog",
]
ROOT = Path(__file__).resolve().parents[2]


def _task_id(seed: int, mode: str, profile: str = "long-multistep") -> str:
    return f"{profile}-{mode}-seed{seed}"


def _spiffe(task_id: str) -> str:
    return f"spiffe://rig/task/{task_id}"


def _connect(mode: str, dest: str, declared: list[str], gateway_bypass: bool = False) -> bool:
    if uses_segment(mode, gateway_bypass):
        return dest in declared
    return True


def run_local(
    *,
    mode: str,
    seed: int,
    out_dir: Path,
    injection: bool = True,
    lineage_disabled_for: str | None = None,
    baseline_spans: pd.DataFrame | None = None,
    granularity: str = "task",
    task_id: str | None = None,
    declared: list[str] | None = None,
    variant: str | None = None,
    breach_services: list[str] | None = None,
    profile: str = "long-multistep",
    steps: int | None = None,
    write_mix: dict[str, float] | None = None,
    injection_at: int | None = None,
    payload_version: str | None = None,
    three_store: bool | None = None,
    shared_overwrite_key: str | None = None,
    gateway_bypass: bool = False,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    spec = profile_spec(profile)
    task_id = task_id or _task_id(seed, mode, profile)
    spiffe = _spiffe(task_id)
    declared = list(declared) if declared is not None else list(spec["declared"])
    steps = spec["steps"] if steps is None else steps
    mix = write_mix if write_mix is not None else spec["write_mix"]
    three = spec["three_store"] if three_store is None else three_store
    inject_step = spec["injection_at"] if injection_at is None else injection_at
    payload_ver = payload_version or spec["payload_version"]
    plan = build_step_plan(
        seed, steps=steps, write_mix=mix, declared=declared, three_store=three
    )
    payload = load_payload(payload_ver, seed) if injection else None
    overwrite_key = shared_overwrite_key or (
        "shared-row" if profile == "data-intensive" else None
    )

    postgres, minio, qdrant, notify = Postgres(), Minio(), Qdrant(), NotifyLog()
    qdrant.snapshot()

    probe_rows: list[dict[str, Any]] = []
    flow_rows: list[dict[str, Any]] = []
    span_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    gt_rows: list[dict[str, Any]] = []
    gw_rows: list[dict[str, Any]] = []
    last_result: dict[str, Any] | None = None
    steps_completed = 0
    write_counts = {"idempotent": 0, "versioned": 0, "derived": 0, "irreversible": 0}

    def record_gateway(tool: str, status: int) -> None:
        if not uses_gateway_path(mode, gateway_bypass):
            return
        gw_rows.append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "client": "simulator",
                "host": "apisix-gateway",
                "uri": f"/{tool}/tools/call",
                "request": f"POST /{tool}/tools/call HTTP/1.1",
                "status": status,
                "upstream": "",
                "service": tool,
            }
        )

    def probe(step: int) -> None:
        for svc in INVENTORY:
            ok = _connect(mode, svc, declared, gateway_bypass)
            probe_rows.append({"step": step, "service": svc, "success": ok})
            if ok:
                flow_rows.append(
                    {
                        "source_spiffe": spiffe,
                        "destination_service": svc,
                        "verdict": "FORWARDED",
                    }
                )

    probe(0)

    overwrite_pending = bool(overwrite_key and profile == "data-intensive")
    drifted_store: str | None = None

    for step in plan:
        tool = pick_tool(step.instruction, declared, last_result)
        operation = step.operation
        key = f"{step.write_class}-{step.index}"
        value: Any = {"step": step.index, "seed": seed}
        injected = bool(injection and payload and step.index == inject_step)
        drifted_declared = False
        extra_undeclared = False
        if injected and profile == "data-intensive" and overwrite_key:
            extra_undeclared = True
            # Pin the drifted row on postgres/minio only. Derived/qdrant stays
            # on the per-task snapshot path so quarantine is not mixed with M1.
            if tool in ("records", "docs"):
                key = overwrite_key
                value = {"injected": True, "seed": seed, "drifted": True}
                drifted_declared = True
            else:
                value = {"injected": True, "seed": seed, "drifted": True}
        elif injected:
            tool = pick_from_injection(payload, declared)
            operation = payload.get("operation", "put")
            key = "blast/radius.json"
            value = {"injected": True, "seed": seed}
        elif overwrite_pending and overwrite_key and drifted_store is not None:
            from tools.dispatch import TOOL_STORE

            store_name, _ = TOOL_STORE.get(tool, (None, None))
            if store_name == drifted_store:
                key = overwrite_key
                overwrite_pending = False

        span_rows.append(
            {
                "name": "orchestrator.step",
                "duration_ms": 20 + step.index % 5,
                "mode": mode,
                "task_id": task_id,
                "step": step.index,
                "write_class": step.write_class,
            }
        )
        can = _connect(mode, tool, declared, gateway_bypass)
        lineage_on = lineage_disabled_for != tool
        try:
            if uses_gateway_path(mode, gateway_bypass) and tool not in declared:
                record_gateway(tool, 403)
                raise GatewayDenied(tool)
            if uses_gateway_path(mode, gateway_bypass):
                record_gateway(tool, 200)
            outcome = dispatch(
                tool=tool,
                operation=operation,
                key=key,
                value=value,
                step=step.index,
                spiffe_id=spiffe,
                mode=mode,
                declared=declared,
                postgres=postgres,
                minio=minio,
                qdrant=qdrant,
                notify=notify,
                can_connect=can,
                lineage_enabled=lineage_on,
            )
        except (AudienceDenied, SegmentDenied, GatewayDenied) as exc:
            span_rows.append(
                {
                    "name": "verify",
                    "duration_ms": 8 if mode == "full" else 1,
                    "mode": mode,
                    "task_id": task_id,
                    "audience_ok": False,
                    "error": str(exc),
                }
            )
            last_result = {"denied": True, "tool": tool}
            steps_completed += 1
            probe(step.index)
            continue

        verify_ms = (12 if mode == "full" else 2) + (step.index % 7) * 0.13
        span_rows.append(
            {
                "name": "verify",
                "duration_ms": verify_ms,
                "mode": mode,
                "task_id": task_id,
                "audience_ok": True,
                "export": "simulator",
            }
        )
        span_rows.append(
            {
                "name": "tool.call",
                "duration_ms": 40,
                "mode": mode,
                "task_id": task_id,
                "tool": tool,
            }
        )
        span_rows.append(
            {
                "name": "store.op",
                "duration_ms": 15,
                "mode": mode,
                "task_id": task_id,
                "store": outcome["store"],
            }
        )
        if outcome["before"] is not None:
            lineage_rows.append(
                {
                    "task_id": task_id,
                    "step": step.index,
                    "write_class": outcome["write_class"],
                    "store": outcome["store"],
                    "operation": "read",
                    "is_write": False,
                    "is_read": True,
                    "key": key,
                    "spiffe_id": spiffe,
                    "drifted": False,
                }
            )
        if outcome["lineage"]:
            ev = outcome["lineage"]
            lineage_rows.append(
                {
                    "task_id": ev["task_id"],
                    "step": ev["step"],
                    "write_class": ev["write_class"],
                    "store": ev["store"],
                    "operation": ev["operation"],
                    "is_write": ev["is_write"],
                    "is_read": False,
                    "key": key,
                    "spiffe_id": ev["spiffe_id"],
                    "drifted": bool(drifted_declared or injected),
                }
            )
        gt_rows.append(
            {
                "task_id": task_id,
                "step": step.index,
                "store": outcome["store"],
                "operation": outcome["operation"],
                "write_class": outcome["write_class"],
                "key": key,
                "before": outcome["before"],
                "after": outcome["after"],
            }
        )
        write_counts[outcome["write_class"]] = write_counts.get(outcome["write_class"], 0) + 1
        last_result = outcome["result"]
        if drifted_declared:
            drifted_store = outcome["store"]
        if extra_undeclared and payload:
            undecl_tool = pick_from_injection(payload, declared)
            try:
                dispatch(
                    tool=undecl_tool,
                    operation=payload.get("operation", "put"),
                    key="blast/radius.json",
                    value={"injected": True, "seed": seed, "undeclared": True},
                    step=step.index,
                    spiffe_id=spiffe,
                    mode=mode,
                    declared=declared,
                    postgres=postgres,
                    minio=minio,
                    qdrant=qdrant,
                    notify=notify,
                    can_connect=_connect(mode, undecl_tool, declared, gateway_bypass),
                    lineage_enabled=False,
                )
            except (AudienceDenied, SegmentDenied, GatewayDenied, KeyError):
                pass
        steps_completed += 1
        probe(step.index)

    attestation = rollback_task(
        events=lineage_rows,
        groundtruth=gt_rows,
        postgres=postgres,
        minio=minio,
        qdrant=qdrant,
        notify=notify,
    )
    action_by_step = {int(a["step"]): a for a in attestation}
    for row in gt_rows:
        att = action_by_step.get(int(row["step"]), {})
        row["attestation_action"] = att.get("action")
        row["restored_matches_before"] = att.get("matches_before")

    finished = datetime.now(timezone.utc)
    t_start = started.timestamp()
    t_end = finished.timestamp()
    tau_issued = t_start
    if uses_flat_credential(mode):
        tau_not_after = t_start + 86400.0
        cred_kind = "sa-token"
    else:
        ttl = 60.0 if granularity == "step" else 1800.0
        tau_not_after = t_start + ttl
        cred_kind = "jwt-svid"
    segment = uses_segment(mode, gateway_bypass)
    span_rows.append(
        {
            "name": "run",
            "duration_ms": (t_end - t_start) * 1000.0,
            "mode": mode,
            "task_id": task_id,
            "start_epoch": t_start,
            "end_epoch": t_end,
            "export": "simulator",
        }
    )
    svid_rows = [
        {
            "task_id": task_id,
            "spiffe_id": spiffe,
            "issued_at": started.isoformat(),
            "not_after": datetime.fromtimestamp(tau_not_after, timezone.utc).isoformat(),
            "issued_at_epoch": tau_issued,
            "not_after_epoch": tau_not_after,
            "credential_kind": cred_kind,
        }
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(probe_rows).to_parquet(out_dir / "probe.parquet", index=False)
    pd.DataFrame(flow_rows).to_parquet(out_dir / "flows.parquet", index=False)
    pd.DataFrame(span_rows).to_parquet(out_dir / "spans.parquet", index=False)
    pd.DataFrame(lineage_rows).to_parquet(out_dir / "lineage.parquet", index=False)
    gt_parquet = []
    for row in gt_rows:
        dumped = dict(row)
        dumped["before"] = json.dumps(row["before"], default=str)
        dumped["after"] = json.dumps(row["after"], default=str)
        gt_parquet.append(dumped)
    pd.DataFrame(gt_parquet).to_parquet(out_dir / "groundtruth.parquet", index=False)
    pd.DataFrame(svid_rows).to_parquet(out_dir / "svid.parquet", index=False)
    if deploys_gateway_policy(mode, gateway_bypass):
        pd.DataFrame(gw_rows).to_parquet(out_dir / "gateway.parquet", index=False)
    (out_dir / "attestation.json").write_text(json.dumps(attestation, indent=2, default=str) + "\n")

    finished = datetime.now(timezone.utc)
    from analysis.compute_result import compute_result as _compute

    result = _compute(
        out_dir,
        {
            "run_id": task_id,
            "profile": profile,
            "mode": mode,
            "seed": seed,
            "variant": variant,
            "gateway_bypass": gateway_bypass,
            "started_at": started.isoformat().replace("+00:00", "Z"),
            "finished_at": finished.isoformat().replace("+00:00", "Z"),
            "wall_clock_seconds": (finished - started).total_seconds(),
            "declaration": {
                "task_id": task_id,
                "spiffe_id": spiffe,
                "services": declared,
                "expected_duration_seconds": 1800,
                "granularity": granularity,
                **({"declared_count": len(declared), "variant": variant} if variant else {}),
            },
            "breach_services": list(breach_services)
            if breach_services is not None
            else (["docs"] if injection else []),
            "steps_completed": steps_completed,
            "write_counts": write_counts,
            "policy_propagation_ms": [] if not segment else [11.0 + seed],
            "source": "simulator",
            "segment_p_ms": 0.0 if not segment else 11.0 + seed,
            "segment_q_ms": 0.0 if not segment else 4.0 + seed,
            "step_ratios": [],
            "reachable_weight": None,
            "task_end_epoch": t_end,
            "policy_removed_at_epoch": None if not segment else t_end + (4.0 + seed) / 1000.0,
            "entry_deleted_at_epoch": None if not segment else t_end,
        },
        baseline_spans=baseline_spans,
    )
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
