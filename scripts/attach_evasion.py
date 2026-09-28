"""Attach evasion.parquet + evasion_matrix to existing long-multistep results.

Uses a dedicated probe pod (not ``agent``) so concurrent make-run jobs that
own the shared agent do not collide. Does not recompute Paper 1 metrics.
Takes ``/tmp/ba-campaign.lock`` unless ``--no-lock``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "rig"), str(ROOT / "analysis"), str(ROOT / "scripts")]

from controller.cnp import render_cnp  # noqa: E402
from harness.cluster_driver import CTX, NS, TOOLS, _kubectl, _wait_cnp  # noqa: E402
from observer.evasion import run_evasion, write_evasion  # noqa: E402

DECLARED = ["records", "search", "notify"]
LOCK_PATH = Path("/tmp/ba-campaign.lock")
SETTLE_S = 5.0
MATRIX_KEYS = (
    "row",
    "id",
    "probe",
    "target",
    "verdict",
    "latency_ms",
    "detail",
    "leak",
    "policy_propagation_ms",
    "probe_epoch",
    "cnp_valid_epoch",
    "seconds_after_cnp_valid",
)


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


def _apply_full_cnp(task_id: str) -> tuple[float, float]:
    spec = {
        "taskId": task_id,
        "expectedDurationSeconds": 1800,
        "services": [{"name": n} for n in DECLARED],
        "namespace": NS,
    }
    rendered = render_cnp(task_id, NS, spec)
    docs = [rendered["egress"], *rendered["ingress"]]
    _apply_yaml("---\n".join(yaml.safe_dump(d) for d in docs))
    cnp_valid_ms = _wait_cnp(task_id)
    cnp_valid_epoch = time.time()
    time.sleep(SETTLE_S)
    return cnp_valid_ms, cnp_valid_epoch


def _cleanup(name: str, task_id: str, mode: str) -> None:
    if mode == "full":
        _kubectl(
            "-n", NS, "delete", "cnp", "-l", f"bounded-autonomy.io/task-id={task_id}",
            "--ignore-not-found", check=False,
        )
    _kubectl("-n", NS, "delete", "pod", name, "--ignore-not-found", check=False)


def acquire_lock_blocking(*, poll_s: float = 15.0) -> int:
    """Block until ``/tmp/ba-campaign.lock`` is exclusive to this process."""
    import fcntl

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    while True:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            holder = LOCK_PATH.read_text().strip() if LOCK_PATH.exists() else "?"
            print(f"WAIT campaign lock held by {holder}", flush=True)
            time.sleep(poll_s)
            continue
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        print(f"LOCK acquired pid={os.getpid()} path={LOCK_PATH}", flush=True)
        return fd


def release_lock(fd: int) -> None:
    try:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    os.close(fd)


def attach_one(run_dir: Path, mode: str, seed: int) -> list[dict]:
    task_id = f"long-multistep-{mode}-seed{seed}"
    pod = f"evasion-{mode}-s{seed}"
    try:
        # Other campaigns leave ingress CNPs on inventory pods. Wipe so flat
        # is truly open and full is only this task's allow-list.
        _kubectl("-n", NS, "delete", "cnp", "--all", "--ignore-not-found", check=False)
        time.sleep(1)
        _ensure_probe(pod, task_id)
        cnp_valid_ms = 0.0
        cnp_valid_epoch = None
        if mode == "full":
            cnp_valid_ms, cnp_valid_epoch = _apply_full_cnp(task_id)
        probe_epoch = time.time()
        rows = run_evasion(
            _kubectl,
            pod,
            NS,
            mode,
            policy_propagation_ms=cnp_valid_ms,
            cnp_valid_epoch=cnp_valid_epoch,
            probe_epoch=probe_epoch,
        )
        write_evasion(run_dir / "evasion.parquet", rows)
        result_path = run_dir / "result.json"
        doc = json.loads(result_path.read_text())
        matrix = []
        for r in rows:
            item = {}
            for key in MATRIX_KEYS:
                if key in r and r[key] is not None:
                    item[key] = r[key]
            matrix.append(item)
        doc["evasion_matrix"] = matrix
        artefacts = doc.setdefault("artefacts", {})
        artefacts["evasion"] = "evasion.parquet"
        result_path.write_text(json.dumps(doc, indent=2) + "\n")
        return rows
    finally:
        _cleanup(pod, task_id, mode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "runs" / "results")
    parser.add_argument("--seeds", default="1-10")
    parser.add_argument("--modes", default="flat,full")
    parser.add_argument("--no-lock", action="store_true")
    args = parser.parse_args(argv)
    if not (TOOLS / "kubectl").exists():
        print("kubectl missing under .tools/", file=sys.stderr)
        return 2
    print(f"context={CTX}")
    raw_seeds = args.seeds.replace(",", " ")
    seeds: list[int] = []
    for token in raw_seeds.split():
        if "-" in token:
            a, b = token.split("-", 1)
            seeds.extend(range(int(a), int(b) + 1))
        else:
            seeds.append(int(token))
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    lock_fd = None if args.no_lock else acquire_lock_blocking()
    failed = 0
    try:
        for mode in modes:
            for seed in seeds:
                run_id = f"long-multistep-{mode}-seed{seed}"
                run_dir = args.results / run_id
                if not (run_dir / "result.json").exists():
                    print(f"SKIP {run_id}: no result.json", file=sys.stderr)
                    failed += 1
                    continue
                print(f"=== {run_id} ===", flush=True)
                try:
                    rows = attach_one(run_dir, mode, seed)
                except Exception as exc:
                    print(f"FAIL {run_id}: {exc}", file=sys.stderr)
                    failed += 1
                    continue
                verdicts = " ".join(f"{r.get('id', r['row'])}={r['verdict']}" for r in rows)
                print(f"OK {run_id} {verdicts}", flush=True)
    finally:
        if lock_fd is not None:
            release_lock(lock_fd)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
