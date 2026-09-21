# Task 04 — Task identity with SPIRE

## Built

- Standalone SPIRE (not Cilium-bundled), trust domain `rig` (`rig/identity/spire.yaml`).
- Controller creates `spiffe://rig/task/<task-id>` with TTL = `expectedDurationSeconds`, parent `spiffe://rig/spire/agent/k8s_psat/bounded-autonomy/k3d-bounded-autonomy-server-0`.
- SVID records are an artefact (`svid.parquet`) consumed by `credential_ratio`.
- Same-pod identity change: the controller patches `bounded-autonomy.io/task-id` on the live agent pod (no restart) and replaces the CNP. New pods can take the label at admission; sequential tasks on one pod cannot wait for a webhook.

## Deviations

- Cilium's SPIRE integration is not installed. CNP match is the task-id label only. Mutual TLS is Paper 2. Expired SVID still collapses *audience* checks in `verify`; it does not collapse the Cilium segment.

## Manuscript impact

Do not claim Cilium selects on the SPIFFE URI string in `matchLabels`. Do not claim “task-id label with mutual TLS” for Paper 1; say “task-id label bound to the task's SVID”.
