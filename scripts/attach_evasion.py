"""Attach evasion.parquet + evasion_matrix to existing long-multistep results.

Uses a dedicated probe pod (not ``agent``) so concurrent make-run jobs that
own the shared agent do not collide. Does not recompute Paper 1 metrics.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "rig"), str(ROOT / "analysis")]

from controller.cnp import render_cnp  # noqa: E402
from harness.cluster_driver import CTX, NS, TOOLS, _kubectl, _wait_cnp  # noqa: E402
from observer.evasion import run_evasion, write_evasion  # noqa: E402

DECLARED = ["records", "search", "notify"]


def _apply_yaml(doc: str) -> None:
    proc = _kubectl("apply", "-f", "-", input_text=doc, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"kubectl apply failed:\n{proc.stderr}\n{proc.stdout}")


def _ensure_probe(name: str, task_id: str) -> str:
    _kubectl("-n", NS, "delete", "pod", name, "--ignore-not-found", "--wait=true", check=False)
    doc = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": name,
            "namespace": NS,
            "labels": {
                "app.kubernetes.io/name": "evasion-probe",
                "bounded-autonomy.io/task-id": task_id,
            },
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": "probe",
                    "image": "ba-runtime:paper1",
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["sleep", "600"],
                    "env": [
                        {"name": "PYTHONPATH", "value": "/app:/app/rig:/app/analysis"},
                    ],
                }
            ],
        },
    }
    _apply_yaml(yaml.safe_dump(doc))
    _kubectl("-n", NS, "wait", "--for=condition=Ready", f"pod/{name}", "--timeout=120s")
    return name


def _apply_full_cnp(task_id: str) -> None:
    spec = {
        "taskId": task_id,
        "expectedDurationSeconds": 1800,
        "services": [{"name": n} for n in DECLARED],
        "namespace": NS,
    }
    rendered = render_cnp(task_id, NS, spec)
    docs = [rendered["egress"], *rendered["ingress"]]
    _apply_yaml("---\n".join(yaml.safe_dump(d) for d in docs))
    _wait_cnp(task_id)
    time.sleep(2)


def _cleanup(name: str, task_id: str, mode: str) -> None:
    if mode == "full":
        _kubectl(
            "-n", NS, "delete", "cnp", "-l", f"bounded-autonomy.io/task-id={task_id}",
            "--ignore-not-found", check=False,
        )
    _kubectl("-n", NS, "delete", "pod", name, "--ignore-not-found", check=False)


def attach_one(run_dir: Path, mode: str, seed: int) -> list[dict]:
    task_id = f"long-multistep-{mode}-seed{seed}"
    pod = f"evasion-{mode}-s{seed}"
    try:
        # Other campaigns leave ingress CNPs on inventory pods. Wipe so flat
        # is truly open and full is only this task's allow-list.
        _kubectl("-n", NS, "delete", "cnp", "--all", "--ignore-not-found", check=False)
        time.sleep(1)
        _ensure_probe(pod, task_id)
        if mode == "full":
            _apply_full_cnp(task_id)
        rows = run_evasion(_kubectl, pod, NS, mode)
        write_evasion(run_dir / "evasion.parquet", rows)
        result_path = run_dir / "result.json"
        doc = json.loads(result_path.read_text())
        doc["evasion_matrix"] = [
            {
                "row": r["row"],
                "probe": r["probe"],
                "target": r.get("target", ""),
                "verdict": r["verdict"],
                "latency_ms": r["latency_ms"],
                "detail": r.get("detail", ""),
            }
            for r in rows
        ]
        artefacts = doc.setdefault("artefacts", {})
        artefacts["evasion"] = "evasion.parquet"
        result_path.write_text(json.dumps(doc, indent=2) + "\n")
        return rows
    finally:
        _cleanup(pod, task_id, mode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "runs" / "results")
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument("--modes", default="flat,full")
    args = parser.parse_args(argv)
    if not (TOOLS / "kubectl").exists():
        print("kubectl missing under .tools/", file=sys.stderr)
        return 2
    print(f"context={CTX}")
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    failed = 0
    for mode in modes:
        for seed in seeds:
            run_id = f"long-multistep-{mode}-seed{seed}"
            run_dir = args.results / run_id
            if not (run_dir / "result.json").exists():
                print(f"SKIP {run_id}: no result.json", file=sys.stderr)
                failed += 1
                continue
            print(f"=== {run_id} ===")
            try:
                rows = attach_one(run_dir, mode, seed)
            except Exception as exc:
                print(f"FAIL {run_id}: {exc}", file=sys.stderr)
                failed += 1
                continue
            verdicts = " ".join(f"{r['row']}={r['verdict']}" for r in rows)
            print(f"OK {run_id} {verdicts}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
