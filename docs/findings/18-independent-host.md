# Task 18 — Independent-host reproduction (Linux VM, 2026-09-21)

Clean Linux VM. Clone `origin/main` from GitHub. Install only Docker, then follow the README. Nothing was copied from the Darwin workstation (no `.tools`, no git bundle, no `runs/`).

This host is **not** the canonical Section VII measurement machine. Timings here are findings only. Canonical spec remains [`12-reproducibility.md`](12-reproducibility.md) (Apple M3 Pro).

## Host spec

| Item | Value |
| --- | --- |
| Date | 2026-09-21 |
| Provisioner | Lima 2.2.0 (`limactl start --name=ba-t18 --cpus=4 --memory=16 --disk=60 --mount-none --containerd=none --vm-type=vz template:ubuntu-24.04`) |
| Why Lima | Multipass is first choice; Homebrew cask install needed `sudo` (no TTY). Lima installed as a user formula. |
| Hypervisor | Apple Virtualization.framework (`vz`) |
| Arch | aarch64 (arm64) |
| vCPU | 4 |
| Memory | 16 GiB configured; `MemTotal` 16341236 kB (~15.6 GiB) |
| Disk | 60 GiB |
| OS | Ubuntu 24.04.4 LTS (Noble) |
| Kernel | Linux 6.8.0-134-generic `#134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:28:11 UTC 2026` aarch64 |
| Docker | Engine 29.8.1, API 1.56, linux/arm64 (`docker-ce` from download.docker.com) |
| containerd | v2.3.5 |
| Python | 3.12.3 (Ubuntu package) after `python3-venv` |
| git HEAD of the 15 runs | `a1dd0b2` (`origin/main` after the Linux cgroup README/script fix) |

`uname -a`:

```
Linux lima-ba-t18 6.8.0-134-generic #134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:28:11 UTC 2026 aarch64 aarch64 aarch64 GNU/Linux
```

No host mounts (`--mount-none`). Lima containerd disabled. Docker installed inside the guest only.

## Commands followed

After Docker CE 29.8.1 and `git clone git@github.com:open-gw/bounded-autonomy.git` (SSH; the repository is not cloneable over HTTPS without auth):

```
sudo apt-get install -y git make python3 python3-venv   # first README insufficiency
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
make help && make test && make tools
make up
flat seeds 1–5, full seeds 1–5, full-step seeds 1–5 (GRANULARITY=step)
make analyse
make paper-tables
make down
```

`make test`: 40 passed. First `make up` on `6d187ab` failed (cgroup bind). After `a1dd0b2` on origin, `make up` and all fifteen `make run` needed no manual intervention.

## Wall-clock (UTC), successful pass (`a1dd0b2`)

| Step | UTC | Notes |
| --- | --- | --- |
| `make up` start | 2026-09-21T17:51:28Z | k3d delete leftover failed cluster |
| DATAPATH_READY / `make up` done | 2026-09-21T17:54:25Z | 177 s |
| Flat 1 | 17:54:25Z–17:54:38Z | 13 s, `\|S\|=8` |
| Flat 2 | 17:54:38Z–17:55:18Z | 40 s, `\|S\|=8` |
| Flat 3 | 17:55:18Z–17:55:58Z | 40 s, `\|S\|=8` |
| Flat 4 | 17:55:58Z–17:56:37Z | 39 s, `\|S\|=8` |
| Flat 5 | 17:56:37Z–17:57:18Z | 41 s, `\|S\|=8` |
| Full 1 | 17:57:18Z–17:58:59Z | 101 s, `\|S\|=3` |
| Full 2 | 17:58:59Z–18:00:43Z | 104 s, `\|S\|=3` |
| Full 3 | 18:00:43Z–18:02:24Z | 101 s, `\|S\|=3` |
| Full 4 | 18:02:24Z–18:04:05Z | 101 s, `\|S\|=3` |
| Full 5 | 18:04:05Z–18:05:46Z | 101 s, `\|S\|=3` |
| Full-step 1 | 18:05:46Z–18:09:10Z | 204 s, `\|S\|=3` |
| Full-step 2 | 18:09:10Z–18:12:35Z | 205 s, `\|S\|=3` |
| Full-step 3 | 18:12:35Z–18:16:00Z | 205 s, `\|S\|=3` |
| Full-step 4 | 18:16:00Z–18:19:25Z | 205 s, `\|S\|=3` |
| Full-step 5 | 18:19:25Z–18:22:50Z | 205 s, `\|S\|=3` |
| `make analyse` | 2026-09-21T18:22:50Z | exit 0, n=15, `source=cluster` |
| `make paper-tables` | 2026-09-21T18:22:51Z | exit 0 |
| `make down` done | 2026-09-21T18:23:03Z | |

Fifteen-run wall (first `make run` through last): **28 min 25 s**. `make up` + 15 runs + analyse + down: **31 min 35 s**.

## Timing vs M3 Pro (findings only)

Canonical Task 12 pass (same profile, Darwin/Docker Desktop): flats ~3.4 min, fulls ~8.7 min, full-step ~17.7 min, fifteen-run block ~30 min. This 4 vCPU / 16 GiB aarch64 VM: flats 173 s, fulls 508 s, full-step 1024 s, fifteen-run block 28.4 min.

The 15-run block is not slower here. Overhead **is** different: VM mean `verify_ms` flat 1.4 / full 1.8, relative vs same-seed flat **5.818**; M3 tables were 2.1 / 1.8 / **2.571**. Credentials `τ/T` and segment `p/q/d` also differ. Do not paste these timings into the manuscript.

## README insufficiencies (each fixed on the workstation and pushed)

1. **`python3 -m venv` fails** on Ubuntu 24.04 until `python3-venv` is installed (`ensurepip` missing). `make` is also absent. README now lists `git`, GNU make, `python3-venv`, and the `apt-get` line.
2. **Manuscript loop was ten runs.** README omitted `GRANULARITY=step` (five more `full` runs). ARTIFACT.md already had them; README now matches.
3. **`make tools` was not a listed step.** Makefile installs tools from `make up` too; README now calls `make tools` explicitly.
4. **`make up` bind-mounted host `/sys/fs/cgroup` on Linux.** First bring-up (`6d187ab`) timed out: every pod sandbox failed with `cgroup.procs: no such file or directory` (cgroup v2 `nsdelegate` + Docker `cgroupns=private`). `cluster_up.sh` now drops that bind on Linux and keeps host bpf. Darwin still drops both. Documented in README and `docs/NEW-MATTER.md`.
5. **Private clone.** `https://github.com/open-gw/bounded-autonomy.git` returns repository-not-found. SSH clone works. README shows the SSH URL. (Auth is the reviewer's GitHub key; not a package.)

Fixes were committed on the workstation, pushed, and `git reset --hard origin/main` inside the VM before the successful pass. No in-VM-only README drift.

## Analyse tables (this VM, not manuscript)

`make analyse` exit 0. `source=cluster (n=15)`.

**Reach:** flat mean `|S|` 8.000 (min=max=8); full 3.000 (min=max=3). Injection service `docs` ∈ R on every flat (`|B∩R|=1`) and on no full (`|B∩R|=0`).

**Rollback:** `ρ_rev` = 1.000 for idempotent and versioned in both modes.

**Overhead:** see timing note above (host-specific).

## Other observations (not README blockers)

- Marquez `CrashLoopBackOff` during `make up`; MinIO/Postgres/Qdrant/Tempo Ready. Lineage still wrote (same pin note as Task 12).
- First flat seed finished in 13 s (cluster already warm); later flats ~40 s.
- Committed `result.json` files in the clone would let `make analyse` pass without running; this pass overwrote all fifteen from the VM cluster.

## Acceptance

Met. 15/15 `source=cluster`. Reach 8/3, `|B∩R|` 1/0, `ρ_rev` 1.0 for idempotent and versioned. Three manuscript tables regenerated with no manual intervention after the README/`cluster_up.sh` fixes were on `origin/main`.
