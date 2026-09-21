# Task 06 — Stores

## Built

- Postgres 17 manifests with `wal_level=logical` and a temporal-table pattern (`records` + `records_history` trigger). Schema in `rig/stores/init.sql`.
- MinIO with versioning hooks and a webhook notification target for the ground-truth subscriber.
- Qdrant single-replica; snapshot restore used by the derived-class procedure.
- `make stores-smoke` writes/reads one object per store (memory fallback when the cluster is down).
- Agent never holds a store DSN; only tool servers do.

## Deviations

- Live `make stores-smoke` against in-cluster ports requires `make up`. Memory stores implement the same history/version/snapshot contracts so the rollback tests do not wait on Docker.

## Manuscript impact

None beyond naming the three stores.
