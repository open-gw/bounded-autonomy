# New matter

Anything the build forces that the manuscript does not describe. Review against the manuscript and the provisional before submission.

## Items

- 2026-09-21 / Task 00 / `docs/study-design.md` was authored in this repository because no prior design document was in the checkout. Treat it as the frozen contract; if an earlier document surfaces, diff it here rather than silently overwriting.
- 2026-09-21 / Task 04 / CiliumNetworkPolicy cannot put a SPIFFE ID in a Kubernetes label value (`:` and `/` are illegal). The controller writes `bounded-autonomy.io/task-id` on the existing pod (no restart) as the SPIRE selector, and every generated CNP sets `authentication.mode: required`. Mutual auth is SPIFFE; the allow-list match is the task-id label. The manuscript should say this, not “CNP matchLabels on the SPIFFE URI”.
- 2026-09-21 / Task 10 / The “model” is a deterministic instruction matcher so five seeds are reproducible without a hosted LLM. An LLM backend can be added later behind an env flag; it is not on the Paper 1 critical path.
- 2026-09-21 / Task 10 / Tool servers speak a JSON HTTP `/tools/call` (MCP-shaped), not stdio MCP. Kubernetes service mesh + SVID headers are simpler this way; the manuscript should not claim a stdio MCP transport.
- 2026-09-21 / Task 11 / `make run` uses the in-process simulator until `make up` has created `/tmp/ba-cluster-up`. Paper 1 numbers in the manuscript must come from cluster runs, not from the simulator. The simulator exists so schema, metrics, mix, and rollback are tested before the cluster exists (the pre-registration order).
