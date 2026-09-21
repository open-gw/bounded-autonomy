# Task 12 — Reproducibility pass (this machine, 2026-09-21)

## Commands followed

README only: venv already present; `make tools`; `make up`; ten `make run` not reached; `make analyse` not reached for cluster data; `make down` after the failed bring-up.

## Wall-clock

| Step | UTC | Notes |
| --- | --- | --- |
| First `make up` start | 2026-09-21T12:46:36Z | k3d create succeeded (~21s) |
| First `make up` fail | 2026-09-21T12:57:06Z | Cilium helm `--wait` 10m: `context deadline exceeded` |
| Cluster deleted | 2026-09-21T13:01:50Z | STS/SPIRE leftover |
| Second `make up` start | 2026-09-21T13:01:53Z | two-phase Cilium |
| Phase 1 helm | 2026-09-21T13:02:12Z | `STATUS: deployed` (no SPIRE) |
| Second `make up` fail | 2026-09-21T13:05:13Z | `kubectl wait` CoreDNS Ready timed out (180s) |

No ten-run wall-clock. No `source=cluster` files. `make analyse` correctly refuses the simulator fixtures (Task 13).

## What broke

Cilium agent/operator/envoy become Ready. CoreDNS stays unready (`plugin/ready: Still waiting on: "kubernetes"`). ClusterIP `kubernetes` has a Cilium backend (`172.18.0.3:6443`) but kube-system pods cannot complete API/DNS (local-path and metrics-server CrashLoop; Hubble relay DNS timeouts). SPIRE server stayed Pending on a PVC while local-path was down (chicken-egg). Second attempt disabled SPIRE for phase 1; CoreDNS still did not become Ready.

This is a k3d + kube-proxy-replacement datapath problem on Docker Desktop (linuxkit 7.0.12, arm64), not a missing README step.

## README knowledge added during the pass

- `make tools` now actually installs helm, kubectl, cilium, hubble (was k3d-only).
- Cilium values: `cni.binPath=/bin`; SPIRE `dataStorage.enabled=false`.
- `cluster_up.sh` is two-phase (datapath, then SPIRE) so a PVC is not required before the API works. That was not enough.

## Acceptance

Not met. A second person following only the README will hit the same CoreDNS wait. Do not paste simulator tables. Do not mark Paper 1 artefact-complete until ten `source=cluster` files exist and `make analyse` exits 0.
