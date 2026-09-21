# Task 07 — Lineage with task facet

## Built

- `rig/lineage/emitter.py` emits an OpenLineage-shaped RunEvent per tool call.
- Task facet `{task_id, step, write_class}` is derived from the presented SVID (`spiffe://rig/task/...`). A client-supplied task id is not read.
- `rig/lineage/write_classes.yaml` is the static (store, operation) table.
- Marquez Deployment in `rig/lineage/marquez.yaml`, labelled so it is outside workload segments.

## Deviations

- Events are written to `lineage.parquet` even if Marquez is down. Marquez is the store of record in the cluster; parquet is the analysis input.

## Manuscript impact

The facet name is `task` (not `agenttask`). Align the manuscript.
