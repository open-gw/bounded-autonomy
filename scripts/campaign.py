"""Ten-seed campaign: resume-on-failure and a per-run provenance guard.

`make campaign PROFILE=long-multistep MODES=flat,gateway-only,gateway-bypass,full,full+bypass SEEDS=1-10`

Refuses the in-process simulator. A completed `result.json` with
`source=cluster` and a passing provenance check is skipped so Paper 1
pre-revision dirs are not rewritten.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "analysis", ROOT / "rig"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from modes import run_id_for  # noqa: E402
from tables import ProvenanceError, assert_cluster_provenance  # noqa: E402

ALL_CAMPAIGN_MODES = (
    "flat",
    "gateway-only",
    "gateway-bypass",
    "full",
    "full+bypass",
)
LOCK_PATH = Path("/tmp/ba-campaign.lock")
CLUSTER_MARKER = Path("/tmp/ba-cluster-up")


def parse_seeds(spec: str) -> list[int]:
    out: list[int] = []
    for part in (spec or "").split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            start, end = int(left), int(right)
            if end < start:
                raise ValueError(f"empty seed range {token!r}")
            out.extend(range(start, end + 1))
        else:
            out.append(int(token))
    if not out:
        raise ValueError("SEEDS= is empty")
    seen: set[int] = set()
    unique: list[int] = []
    for seed in out:
        if seed not in seen:
            seen.add(seed)
            unique.append(seed)
    return unique


def parse_modes(spec: str) -> list[tuple[str, bool]]:
    raw = (spec or "").strip()
    if raw in ("", "all"):
        tokens = list(ALL_CAMPAIGN_MODES)
    else:
        tokens = [part.strip() for part in raw.split(",") if part.strip()]
    out: list[tuple[str, bool]] = []
    for token in tokens:
        if token in ("full+bypass", "full-bypass"):
            out.append(("full", True))
        elif token in ALL_CAMPAIGN_MODES or token in ("flat", "full", "gateway-only", "gateway-bypass"):
            out.append((token, False))
        else:
            raise ValueError(f"unknown mode {token!r}")
    return out


def parse_granularities(spec: str) -> list[str]:
    tokens = [part.strip() for part in (spec or "task").split(",") if part.strip()]
    if not tokens:
        tokens = ["task"]
    for token in tokens:
        if token not in ("task", "step"):
            raise ValueError(f"unknown granularity {token!r}")
    return tokens


def job_run_id(
    profile: str,
    mode: str,
    seed: int,
    granularity: str,
    gateway_bypass: bool,
) -> str:
    return run_id_for(
        profile=profile,
        mode=mode,
        seed=seed,
        granularity=granularity,
        gateway_bypass=gateway_bypass,
    )


def expand_jobs(
    profile: str,
    modes: Iterable[tuple[str, bool]],
    seeds: Iterable[int],
    granularities: Iterable[str],
) -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = []
    for granularity in granularities:
        for mode, bypass in modes:
            if granularity == "step" and (mode != "full" or bypass):
                continue
            for seed in seeds:
                run_id = job_run_id(profile, mode, int(seed), granularity, bool(bypass))
                jobs.append(
                    {
                        "profile": profile,
                        "mode": mode,
                        "seed": int(seed),
                        "granularity": granularity,
                        "gateway_bypass": bool(bypass),
                        "run_id": run_id,
                    }
                )
    return jobs


def _load_one(path: Path) -> dict:
    doc = json.loads(path.read_text())
    doc["_path"] = str(path)
    return doc


def provenance_ok(result_path: Path) -> tuple[bool, str]:
    if not result_path.exists():
        return False, "missing result.json"
    try:
        assert_cluster_provenance([_load_one(result_path)])
    except (ProvenanceError, OSError, ValueError, KeyError) as exc:
        return False, str(exc)
    return True, "ok"


def is_complete(out_dir: Path) -> bool:
    ok, _ = provenance_ok(out_dir / "result.json")
    return ok


def _python() -> str:
    return sys.executable


def run_job(job: dict[str, object], out_root: Path) -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "analysis"), str(ROOT / "rig"), env.get("PYTHONPATH", "")]
    )
    env.pop("BA_LOCAL", None)
    cmd = [
        _python(),
        "-m",
        "harness.driver",
        "--profile",
        str(job["profile"]),
        "--mode",
        str(job["mode"]),
        "--seed",
        str(job["seed"]),
        "--granularity",
        str(job["granularity"]),
    ]
    if job["gateway_bypass"]:
        cmd.append("--gateway-bypass")
    print(f"RUN {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    if proc.returncode != 0:
        return proc.returncode
    out_dir = out_root / str(job["run_id"])
    ok, reason = provenance_ok(out_dir / "result.json")
    if not ok:
        print(f"PROVENANCE_FAIL {job['run_id']}: {reason}", flush=True)
        return 2
    print(f"PROVENANCE_OK {job['run_id']}", flush=True)
    return 0


def _other_rig_jobs() -> list[str]:
    try:
        proc = subprocess.run(
            ["pgrep", "-fl", r"make (run|campaign|up|down)|python -m harness|cluster_driver"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    lines = []
    self = str(os.getpid())
    for line in (proc.stdout or "").splitlines():
        if self in line.split()[:1]:
            continue
        if "campaign.py" in line and self in line:
            continue
        lines.append(line)
    return lines


def wait_for_idle(*, timeout_s: int = 0, poll_s: int = 15) -> None:
    started = time.time()
    while True:
        others = _other_rig_jobs()
        if not others:
            return
        print("WAIT other rig jobs:", flush=True)
        for line in others[:12]:
            print(f"  {line}", flush=True)
        if timeout_s and time.time() - started > timeout_s:
            raise SystemExit("timed out waiting for exclusive cluster")
        time.sleep(poll_s)


def acquire_lock() -> int:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise SystemExit(f"campaign lock held: {LOCK_PATH}")
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="long-multistep")
    parser.add_argument("--modes", default="flat,full")
    parser.add_argument("--seeds", default="1-10")
    parser.add_argument("--granularity", default="task")
    parser.add_argument("--results", type=Path, default=ROOT / "runs" / "results")
    parser.add_argument("--wait-idle", action="store_true", help="wait for other make run/campaign jobs")
    parser.add_argument("--wait-timeout", type=int, default=0)
    args = parser.parse_args(argv)

    if args.profile == "all":
        profiles = ["long-multistep"]
    else:
        profiles = [args.profile]
    modes = parse_modes(args.modes)
    seeds = parse_seeds(args.seeds)
    granularities = parse_granularities(args.granularity)

    if not CLUSTER_MARKER.exists():
        print("campaign requires a live cluster (/tmp/ba-cluster-up); refusing simulator", file=sys.stderr)
        return 2

    if args.wait_idle:
        wait_for_idle(timeout_s=args.wait_timeout)

    lock_fd = acquire_lock()
    try:
        jobs: list[dict[str, object]] = []
        for profile in profiles:
            jobs.extend(expand_jobs(profile, modes, seeds, granularities))
        skipped = failed = ran = 0
        for job in jobs:
            out_dir = args.results / str(job["run_id"])
            if is_complete(out_dir):
                print(f"SKIP {job['run_id']} (resume: cluster provenance ok)", flush=True)
                skipped += 1
                continue
            rc = run_job(job, args.results)
            if rc == 0:
                ran += 1
            else:
                failed += 1
                print(f"FAIL {job['run_id']} rc={rc} (resume will retry)", flush=True)
        print(
            f"CAMPAIGN_DONE jobs={len(jobs)} ran={ran} skipped={skipped} failed={failed}",
            flush=True,
        )
        return 0 if failed == 0 else 1
    finally:
        try:
            import fcntl

            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
