# Task 12 — Reproducibility pass (this machine, 2026-09-21)

This host is the canonical measurement machine for Section VII tables. There is no separate cloud VM in this session. Timing figures without this spec are not reproducible. Cited from Section VI of the manuscript map in [`docs/design.md`](../design.md).

## Measurement host

| Item | Value |
| --- | --- |
| Date | 2026-09-21 |
| CPU | Apple M3 Pro (`machdep.cpu.brand_string`) |
| Cores | 12 (`hw.ncpu` / `hw.logicalcpu` / `hw.physicalcpu`) |
| Memory | 18.0 GiB (`hw.memsize` = 19327352832) |
| Kernel | Darwin 25.5.0 (`xnu-12377.121.6~2/RELEASE_ARM64_T6030`) arm64 |
| OS | macOS 26.5.1 (25F80) |
| Docker client/engine | 29.7.2 (API 1.55, darwin/arm64 client, linux/arm64 engine) |
| Docker Desktop | 4.87.0 (236836) |
| k3d | v5.8.3 (`rig/versions.yaml`) |
| k3s | `rancher/k3s:v1.32.3-k3s1` |
| Cilium | chart/image 1.17.13 |
| SPIRE | 1.15.3 |
| git HEAD of the runs | `14601f79fd5fd474a0bf25e44e4066b578992c05` (`origin/main`) |

`uname -a`:

```
Darwin Rinus-MBP-M3.local 25.5.0 Darwin Kernel Version 25.5.0: Mon Apr 27 20:41:06 PDT 2026; root:xnu-12377.121.6~2/RELEASE_ARM64_T6030 arm64
```

These fifteen `source=cluster` files are the canonical cluster timings for Section VII tables.

## Commands followed

README plus the fifteen-run manuscript set, after a clean cluster:

```
make down && make up
flat seeds 1–5, full seeds 1–5, full-step seeds 1–5 (GRANULARITY=step)
make analyse
make down
```

Driver code was `14601f7`. Two image pins were applied in-place before the fifteen runs so kubelet could pull (see Deviations).

## Wall-clock (UTC)

| Step | UTC | Notes |
| --- | --- | --- |
| `make down` start | 2026-09-21T16:22:22Z | deleted existing k3d cluster |
| `make down` done | 2026-09-21T16:22:30Z | |
| `make up` start | 2026-09-21T16:22:30Z | |
| DATAPATH_READY | ~2026-09-21T16:23:45Z | Cilium green, CoreDNS Ready |
| `make up` done | 2026-09-21T16:24:35Z | `/tmp/ba-cluster-up`; MinIO/Marquez still ImagePullBackOff |
| Image pins applied | 2026-09-21T16:32:19Z | MinIO and Marquez Ready |
| Runs start | 2026-09-21T16:32:30Z | |
| Flat 1–5 done | 2026-09-21T16:35:54Z | `\|R\|=8`, `source=cluster` |
| Full 1–5 done | 2026-09-21T16:44:33Z | `\|R\|=3`, `source=cluster` |
| Full-step 1–5 done | 2026-09-21T17:02:12Z | `\|R\|=3`, `source=cluster` |
| `make analyse` | 2026-09-21T17:02Z | provenance OK, n=15 |

## First pass (failed; superseded by Task 15)

README only: venv already present; `make tools`; `make up`; ten `make run` not reached.

| Step | UTC | Notes |
| --- | --- | --- |
| First `make up` start | 2026-09-21T12:46:36Z | k3d create succeeded (~21s) |
| First `make up` fail | 2026-09-21T12:57:06Z | Cilium helm `--wait` 10m: `context deadline exceeded` |
| Cluster deleted | 2026-09-21T13:01:50Z | STS/SPIRE leftover |
| Second `make up` start | 2026-09-21T13:01:53Z | two-phase Cilium |
| Second `make up` fail | 2026-09-21T13:05:13Z | `kubectl wait` CoreDNS Ready timed out (180s) |

Cause: k3d + kube-proxy-replacement datapath on Docker Desktop (no shared bpffs). Fixed in Task 15 (`cni.binPath=/opt/cni/bin`, `socketLB.hostNamespaceOnly: true`).

## Deviations on the successful pass

- No separate VM. This Darwin/Docker Desktop host is the measurement machine.
- `docker.io/minio/minio:RELEASE.2025-07-23T15-54-02Z` is no longer pullable. Same release is `quay.io/minio/minio:RELEASE.2025-07-23T15-54-02Z`.
- `marquezproject/marquez:0.50.1` was never published on Docker Hub. Pin is `0.50.0`. Lineage still writes `lineage.parquet` if Marquez is down.
- Flat seed 2 ingested 17 verify spans (`nunique=17`, still `≤ steps_completed`). Provenance accepts it; the other fourteen task/step files have 29 or 30.

## Acceptance

Met. 15/15 gates: `source=cluster`, reachable 8 vs 3, verify `nunique>1`, verify `n ≤ steps_completed`. `make analyse` exits 0. Host spec recorded here and cited from Section VI (`docs/design.md`). `\val{}` slots left for the user.
