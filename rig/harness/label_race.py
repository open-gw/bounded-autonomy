"""Q3 label-race: held-open TCP across pod relabel A→B.

One agent pod hosts task A, then is relabelled to task B while a TCP
connection opened under A's CNP is kept open. Records whether Cilium
drops that socket. A surviving connection is a threat to validity;
mitigation is one pod per task (the cluster driver already deletes the
agent pod between ``make run`` invocations).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from controller.cnp import TASK_LABEL, render_cnp
from harness.cluster_driver import (
    NS,
    _apply_yaml,
    _cluster_ip,
    _ensure_agent,
    _kubectl,
    _wait_cnp,
)

ROOT = Path(__file__).resolve().parents[2]
TASK_A = "label-race-a"
TASK_B = "label-race-b"
HOLD_PATH = "/tmp/ba-label-race.json"
GO_PATH = "/tmp/ba-label-race.go"


def _label(task_id: str) -> None:
    _kubectl(
        "-n", NS, "label", "pod", "agent",
        f"{TASK_LABEL}={task_id}", "--overwrite",
    )


def _apply_segment(task_id: str, services: list[str]) -> None:
    spec = {
        "taskId": task_id,
        "expectedDurationSeconds": 1800,
        "services": [{"name": name} for name in services],
        "namespace": NS,
    }
    rendered = render_cnp(task_id, NS, spec)
    docs = [rendered["egress"], *rendered["ingress"]]
    _apply_yaml("---\n".join(yaml.safe_dump(doc) for doc in docs))
    _wait_cnp(task_id)


def _delete_segment(task_id: str) -> None:
    _kubectl("-n", NS, "delete", "cnp", "-l", f"{TASK_LABEL}={task_id}", check=False)


def _start_holder(records_ip: str) -> None:
    _kubectl("-n", NS, "exec", "agent", "--", "rm", "-f", HOLD_PATH, GO_PATH, check=False)
    src = Path(__file__).resolve().parent / "label_race_holder.py"
    _kubectl("cp", str(src), f"{NS}/agent:/tmp/label_race_holder.py")
    _kubectl(
        "-n", NS, "exec", "agent", "--",
        "sh", "-c",
        f"nohup python /tmp/label_race_holder.py {records_ip} 8081 "
        ">/tmp/ba-label-race.out 2>/tmp/ba-label-race.err &",
        check=False,
    )


def _read_holder() -> dict[str, Any]:
    proc = _kubectl("-n", NS, "exec", "agent", "--", "cat", HOLD_PATH, check=False)
    text = (proc.stdout or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _wait_held(timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        doc = _read_holder()
        if doc.get("phase") in {"held", "done"}:
            return doc
        time.sleep(0.2)
    return _read_holder()


def _signal_go() -> None:
    _kubectl("-n", NS, "exec", "agent", "--", "sh", "-c", f"date > {GO_PATH}")


def run_label_race(*, out_dir: Path) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    pod = _ensure_agent(TASK_A, "full")
    _apply_segment(TASK_A, ["records"])
    records_ip = _cluster_ip("records")
    _start_holder(records_ip)
    held = _wait_held()
    if held.get("phase") not in {"held", "done"}:
        raise RuntimeError(f"holder did not open TCP: {held}")
    # Relabel A→B; B's allow-list is search only, so records is undeclared.
    _label(TASK_B)
    _apply_segment(TASK_B, ["search"])
    _delete_segment(TASK_A)
    time.sleep(0.5)
    relabelled_at = time.time()
    _signal_go()
    deadline = time.time() + 25
    observed = held
    while time.time() < deadline:
        observed = _read_holder()
        if observed.get("phase") == "done":
            break
        time.sleep(0.2)
    survived = bool(observed.get("held_open_survived"))
    new_ok = bool(observed.get("new_connection_ok"))
    result = {
        "schema_version": "1.0.0",
        "run_id": "label-race",
        "experiment": "label-race",
        "source": "cluster",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pod": pod,
        "task_a": TASK_A,
        "task_b": TASK_B,
        "records_ip": records_ip,
        "held_open_first_ok": bool(held.get("first_ok")),
        "held_open_survived": survived,
        "new_connection_after_relabel_ok": new_ok,
        "new_connection_after_relabel": "allowed" if new_ok else "refused",
        "holder": observed,
        "relabelled_at_epoch": relabelled_at,
        "observed": (
            "held-open TCP to records survived relabel A→B"
            if survived
            else "held-open TCP to records was dropped after relabel A→B"
        ),
        "threat_to_validity": survived,
        "mitigation": "one pod per task; cluster driver deletes the agent pod between runs",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    _delete_segment(TASK_A)
    _delete_segment(TASK_B)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Q3 label-race experiment")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "runs" / "results" / "_label-race",
    )
    args = parser.parse_args(argv)
    result = run_label_race(out_dir=args.out)
    print(json.dumps({
        "held_open_survived": result["held_open_survived"],
        "new_connection_after_relabel": result["new_connection_after_relabel"],
        "threat_to_validity": result["threat_to_validity"],
        "out": str(args.out / "result.json"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
