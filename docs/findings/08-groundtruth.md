# Task 08 — Ground truth subscribers

## Built

- Independent `groundtruth.parquet` keyed by `task_id`, populated from store-level history (Postgres trigger / MinIO notification / Qdrant oplog; memory equivalents in the simulator).
- Test: disabling the lineage emitter on `notify` leaves ground truth unchanged and drops `rho_enum` below 1.

## Deviations

- In-cluster WAL slot consumer is specified (`rig_gt` / `test_decoding`); the simulator reads the in-memory history table. Both write the same columns.

## Manuscript impact

`rho_enum < 1` is the detectable-gap test. Keep that claim; the test now exists.
