# New matter

Anything the build forces that the manuscript does not describe. Review against the manuscript and the provisional before submission.

## Items

- 2026-09-21 / Task 00 / `docs/study-design.md` was authored in this repository because no prior design document was in the checkout. Treat it as the frozen contract; if an earlier document surfaces, diff it here rather than silently overwriting.
- 2026-09-21 / Task 14 / Original design document still not found (see `docs/findings/14-prereg-diff.md`). Reconstruction remains in place; it is not ratified as the pre-registration of record.
- 2026-09-21 / Task 04 / CiliumNetworkPolicy cannot put a SPIFFE ID in a Kubernetes label value (`:` and `/` are illegal). The controller writes `bounded-autonomy.io/task-id` on the live pod (no restart) as the SPIRE selector and the CNP match. Paper 1 does not set `authentication.mode: required`.
- 2026-09-21 / Task 15 / Cilium's bundled SPIRE/mTLS is not installed. Mutual-TLS enforcement moves to Paper 2. The manuscript line “task-id label with mutual TLS” should become “task-id label bound to the task's SVID”. Attribution still comes from identity: the label is set from the task SVID.
- 2026-09-21 / Task 15 / `make up` always `k3d cluster delete` first. Helm-uninstall-in-place is how `cilium-spire` was left terminating.
- 2026-09-21 / Task 15 / On Darwin/Docker Desktop, k3d cannot bind-mount host `/sys/fs/bpf` (macOS has no bpffs). `make up` mounts bpf inside the node and `mount --make-shared`. Linux keeps the specced host binds.
- 2026-09-21 / Task 15 / k3s v1.32.3 kubelet loads CNI plugins from `/opt/cni/bin`, not `/bin`. Setting Cilium `cni.binPath: /bin` installs `cilium-cni` where kubelet does not look; CoreDNS stays ContainerCreating.
- 2026-09-21 / Task 15 / `socketLB.hostNamespaceOnly: true` is required on Docker Desktop/k3d: cgroup v2 nesting does not attach Cilium socket-LB to pod cgroups, so ClusterIP `kubernetes` (10.43.0.1) blackholes and CoreDNS stays unready.
- 2026-09-21 / Task 17 / Verify spans for cluster results are pulled from Tempo. `make analyse` refuses zero-variance verify durations. Flat authenticates with a 24 h ServiceAccount token; full records SVID issue→revoke. Weights frozen in `rig/services.yaml` (records 3, docs 3, search 2, notify 2, others 1). Rollback and lineage remain in-process stores; only probe, verify spans, and credentials are live.
- 2026-09-21 / Task 17 / Agent HTTP client uses a 1 s timeout on tool calls (`live_worker.call_tool`). A blocked undeclared injection (CNP drop) must not wait 5 s and inflate the OTel `run` span / overhead relative column. Successful in-cluster calls are ~10 ms. Does not change already-collected Paper 1 results.
- 2026-09-21 / Task 10 / The “model” is a deterministic instruction matcher so five seeds are reproducible without a hosted LLM. An LLM backend can be added later behind an env flag; it is not on the Paper 1 critical path.
- 2026-09-21 / Task 10 / Tool servers speak a JSON HTTP `/tools/call` (MCP-shaped), not stdio MCP. Kubernetes service mesh + SVID headers are simpler this way; the manuscript should not claim a stdio MCP transport.
- 2026-09-21 / Task 11 / `make run` uses the in-process simulator until `make up` has created `/tmp/ba-cluster-up`. Paper 1 numbers in the manuscript must come from cluster runs, not from the simulator. The simulator exists so schema, metrics, mix, and rollback are tested before the cluster exists (the pre-registration order).
- 2026-09-21 / Task 13 / `result.json` gains a required `source: simulator | cluster` field that the reconstruction of study-design §5 did not originally list. `make analyse` will not emit manuscript tables from simulator artefacts.
- 2026-09-21 / Task 12 / First Docker Desktop bring-up failed: CoreDNS unready because bpf was not shared into the k3d node. Superseded by Task 15.
