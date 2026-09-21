# Task 04 — Task identity with SPIRE

## Built

- Cilium-installed SPIRE, trust domain `rig` (`cilium-values.yaml`).
- Controller creates `spiffe://rig/task/<task-id>` with TTL = `expectedDurationSeconds`.
- SVID records are an artefact (`svid.parquet`) consumed by `credential_ratio`.
- Same-pod identity change: the controller patches `bounded-autonomy.io/task-id` on the live agent pod (no restart) and replaces the CNP.

## Deviations

- See NEW-MATTER: CNP match is the task-id label; mTLS is SPIFFE. Expired SVID collapses the segment via `authentication.mode: required` without deleting the pod — that is the cluster acceptance test.

## Manuscript impact

Do not claim Cilium selects on the SPIFFE URI string in `matchLabels`.
