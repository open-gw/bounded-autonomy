# Architecture summary

Paper 1 artefact for *Containing and Unwinding the Blast Radius of Agentic Workflows*. Implements exactly Section VII of the ICSA manuscript: one node, profile `long-multistep`, modes `flat` and `full`, four metric exporters, five seeds. Study-level definitions live in [`study-design.md`](study-design.md).

## Control plane

```
TaskDeclaration CRD  →  segment controller (kopf)
                     →  CiliumNetworkPolicy (egress to declared services only,
                        ingress to those services only from the task SPIFFE)
                     →  SPIRE registration  spiffe://rig/task/<task-id>
                     →  SVID TTL = declaration.expected_duration_seconds
```

Default-deny in the workload namespace. Deleting the CRD, or TTL expiry, removes the CNP. `step` granularity is a narrowed declaration update that replaces the CNP.

Policy propagation is the interval from the CRD event timestamp to the first Hubble observation that the new allow-list is in effect. Exported per step.

## Data plane

Eight services (`rig/services.yaml`). The agent talks only to MCP tool servers. Stores (Postgres 17 temporal tables, MinIO versioning, Qdrant snapshots) accept connections only from their tool server.

| Path | Mode `flat` | Mode `full` |
| --- | --- | --- |
| Segment CNP | not emitted | emitted |
| `verify` span | recorded, check skipped | audience + destination filter |
| Expected `\|S\|` | 8 | 3 |

## Identity

SPIRE server + agent. One SVID per task, not per pod. Two sequential tasks on the same pod receive two SPIFFE IDs and two segments. An expired SVID collapses the segment (mTLS / audience check fail) without terminating the pod.

Cilium mutual authentication is enabled (`authentication.mode: required` on generated CNPs). See `docs/NEW-MATTER.md` for the residual use of a pod annotation as the SPIRE selector: Kubernetes label values cannot hold a SPIFFE ID, and the same pod must change identity without a restart.

## Observation (four exporters)

| Exporter | Artefact | Metric |
| --- | --- | --- |
| Probe job at each step boundary | `probe.parquet` | `reachable_set` |
| Hubble, task identity, `FORWARDED` | `flows.parquet` | `reachable_set` |
| OTel → collector → Tempo | `spans.parquet` | `credential_ratio`, `verification_overhead` |
| OpenLineage → Marquez (outside every segment) | `lineage.parquet` | `rollback_completeness`, `rho_enum` |
| WAL / bucket notification / oplog subscribers | `groundtruth.parquet` | `rollback_completeness`, `rho_enum` |
| SPIRE issue/expiry log | `svid.parquet` | `credential_ratio` |

## Span naming

Documented here so `flat` and `full` remain separable and `verify` is findable.

| Span name | Where | Required attributes |
| --- | --- | --- |
| `orchestrator.step` | agent | `step`, `task_id`, `mode`, `write_class` |
| `tool.call` | tool server | `tool`, `operation`, `task_id`, `mode` |
| `verify` | tool server, enclosing audience check and any filtering | `mode`, `task_id`, `audience_ok` |
| `store.op` | tool server, around the store RPC | `store`, `operation`, `write_class` |
| `lineage.emit` | tool server | `write_class` |

Durations in milliseconds in `spans.parquet`.

## Rollback

Lineage events for a task, ordered by `step`. Procedure by class:

| Class | Action | Attestation |
| --- | --- | --- |
| idempotent | rewrite prior value from history | `restored`, ground-truth `before` match |
| versioned | Postgres history restore or MinIO version restore | same |
| derived | Qdrant snapshot restore, mark quarantined | `quarantined: true` |
| irreversible | escalate, record only | `escalated: true` |

Attestation JSON lists every write, class, action, and ground-truth confirmation.

## Workload

Four MCP tool servers (`records`, `docs`, `search`, `notify`). Orchestrator: 30 explicit steps, seeded plan implements 40/30/20/10. Declaration is produced from that plan before step 1. Drift payload at step 15 is versioned under `rig/harness/payloads/`.

## Manuscript map

| Manuscript | This repo |
| --- | --- |
| Section VII study | `docs/study-design.md` |
| Reach table | `make analyse` → table reach |
| Rollback table | `make analyse` → table rollback |
| Overhead table | `make analyse` → table overhead |
| Q2 figures | `make analyse` → `analysis/output/` |
| `\val{}` slots | filled from the ten `result.json` files |
