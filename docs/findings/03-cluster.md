# Task 03 — Cluster and segment controller

## Built

- `rig/cluster/k3d.yaml`, `cilium-values.yaml` (kube-proxy replacement, Hubble + relay). Datapath bring-up is Task 15.
- Eight services in `rig/cluster/services.yaml` with sensitivity 1–3.
- `TaskDeclaration` CRD and kopf controller (`rig/controller/`). `render_cnp` emits egress from the task identity to declared services and ingress to those services only from that identity; delete removes them. TTL timer deletes the CRD.
- Unit test: a declaration of 3 services produces CNP allow-lists of exactly those three, selected by `bounded-autonomy.io/task-id`. No Cilium `authentication` block (Paper 2).

## Deviations

- End-to-end `cilium connectivity`-style probe is a cluster acceptance test (`make up`); it is not run in `make test`. CNP rendering is tested without a cluster.
- Default-deny CNP selects only the agent pod. Ingress isolation of declared services is a per-service CNP keyed on `bounded-autonomy.io/task-id` (see `docs/findings/16-cnp-driver.md`). A namespace-wide deny isolates tool servers from their stores.
- Cluster create/delete semantics were wrong in the first pass (Helm uninstall in place). Task 15 replaces that.

## Manuscript impact

Policy propagation is defined as CRD-event time to CNP-apply time in the operator log; Hubble-observed “in effect” still needs a cluster exporter (Task 05).
