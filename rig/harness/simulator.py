"""In-process run: same artefacts and metrics as the cluster driver."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agent.orchestrator import pick_from_injection, pick_tool
from harness.payloads import load_payload
from plan import build_step_plan
from rollback.procedures import rollback_task
from stores.memory import Minio, NotifyLog, Postgres, Qdrant
from tools.dispatch import AudienceDenied, SegmentDenied, dispatch

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


def _task_id(seed: int, mode: str) -> str:
    return f"long-multistep-{mode}-seed{seed}"


def _spiffe(task_id: str) -> str:
    return f"spiffe://rig/task/{task_id}"


def _connect(mode: str, dest: str, declared: list[str]) -> bool:
    return True if mode == "flat" else dest in declared


def run_local(
    *,
    mode: str,
    seed: int,
    out_dir: Path,
    injection: bool = True,
    lineage_disabled_for: str | None = None,
    baseline_spans: pd.DataFrame | None = None,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    task_id = _task_id(seed, mode)
    spiffe = _spiffe(task_id)
    plan = build_step_plan(seed)
    declared = ["records", "search", "notify"]
    payload = load_payload("v1", seed) if injection else None

    postgres, minio, qdrant, notify = Postgres(), Minio(), Qdrant(), NotifyLog()
    qdrant.snapshot()

    probe_rows: list[dict[str, Any]] = []
    flow_rows: list[dict[str, Any]] = []
    span_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    gt_rows: list[dict[str, Any]] = []
    last_result: dict[str, Any] | None = None
    steps_completed = 0
    write_counts = {"idempotent": 0, "versioned": 0, "derived": 0, "irreversible": 0}

    def probe(step: int) -> None:
        for svc in INVENTORY:
            ok = _connect(mode, svc, declared)
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

    for step in plan:
        tool = pick_tool(step.instruction, declared, last_result)
        operation = step.operation
        key = f"{step.write_class}-{step.index}"
        value = {"step": step.index, "seed": seed}
        injected = injection and payload and step.index == 15
        if injected:
            tool = pick_from_injection(payload, declared)
            operation = payload.get("operation", "put")
            key = "blast/radius.json"
            value = {"injected": True, "seed": seed}

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
        can = _connect(mode, tool, declared)
        lineage_on = lineage_disabled_for != tool
        try:
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
        except (AudienceDenied, SegmentDenied) as exc:
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

        verify_ms = 12 if mode == "full" else 2
        span_rows.append(
            {
                "name": "verify",
                "duration_ms": verify_ms,
                "mode": mode,
                "task_id": task_id,
                "audience_ok": True,
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
                    "spiffe_id": ev["spiffe_id"],
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

    svid_rows = [
        {
            "task_id": task_id,
            "spiffe_id": spiffe,
            "issued_at": started.isoformat(),
            "not_after": started.isoformat(),
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
    (out_dir / "attestation.json").write_text(json.dumps(attestation, indent=2, default=str) + "\n")

    finished = datetime.now(timezone.utc)
    from analysis.compute_result import compute_result as _compute

    result = _compute(
        out_dir,
        {
            "run_id": task_id,
            "profile": "long-multistep",
            "mode": mode,
            "seed": seed,
            "started_at": started.isoformat().replace("+00:00", "Z"),
            "finished_at": finished.isoformat().replace("+00:00", "Z"),
            "wall_clock_seconds": (finished - started).total_seconds(),
            "declaration": {
                "task_id": task_id,
                "spiffe_id": spiffe,
                "services": declared,
                "expected_duration_seconds": 1800,
                "granularity": "task",
            },
            "steps_completed": steps_completed,
            "write_counts": write_counts,
            "policy_propagation_ms": [] if mode == "flat" else [11.0 + seed],
            "source": "simulator",
        },
        baseline_spans=baseline_spans,
    )
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
