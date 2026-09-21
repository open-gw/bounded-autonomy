# Task 11 — Drift harness and run driver

## Built

- Injection at step 15 from `rig/harness/payloads/v1.yaml`: instructs a call to `docs` / MinIO.
- One seed controls plan shuffle, payload selection, and (later) sampling.
- `make run PROFILE=long-multistep MODE=flat|full SEED=n` writes the six artefacts plus `result.json`.
- `make analyse` rebuilds the three tables.

## Deviations

- `make run` uses the in-process simulator until `make up` has succeeded (NEW-MATTER). Ten real `result.json` files for the manuscript must be produced on the cluster.

## Manuscript impact

Injection step is 15; undeclared service is `docs`. Freeze those numbers in Section VII.
