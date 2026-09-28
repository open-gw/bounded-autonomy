# Task 29 — Write-heavy three-store profile (Q3 generality)

Recorded 28 September 2026. Independent of gateway / SPIRE JWT. Uses the existing full rollback path (`run_local` stores + class-dispatched procedures).

## Built

- Profile `data-intensive`: 20 steps, write mix 20/30/40/10 → 4 / 6 / 8 / 2.
- Declared `[records, docs, search, notify]` so one task writes postgres, minio, and qdrant.
- Drift at step 3: payload `v-data` directs a write to undeclared `billing` / minio. The planned step-3 write still lands; if it is postgres or minio, key `shared-row` is pinned so a later legitimate write can overwrite it (M1).
- Qdrant snapshot once at task start; quarantine is **per task** (one `restore_snapshot`), not per collection.
- MinIO versioning and Postgres temporal history remain on (memory stores used by the rollback path).
- Ground-truth rows for all three stores (every successful dispatch).
- Schema: `profile` enum includes `data-intensive`; `steps` is 1–30. Extra-schema rules pin mix, declared triple, and `injection.at_step=3`.
- `make paper-tables TABLE=data-intensive` emits per-class `ρ_enum`, `ρ_rev`, `ρ_quarantined`, `ρ_escalated`. Default analyse/paper-tables still exclude this profile so Paper 1 tables stay on `long-multistep`.

## Rollback ordering (M1)

Class-dispatched procedure: if read lineage shows a later write observed a row after a drifted write to the same `(store, key)`, that later write is **`dependent`**, not reversed. The drifted write is `skipped_dependent` so a restore cannot clobber the later value.

Unit test: `tests/test_data_intensive.py::test_m1_later_write_is_dependent_not_reversed`.
Live value after rollback remains the later legitimate write.

Cluster: M1 fired on 5/10 seeds (those whose step-3 tool is `records` or `docs`). Procedure string is `M1-dependent-write`. No silent revert.

## Campaign

`full` × 10 seeds, `source=cluster`, verify-span count 20 and non-zero duration variance on every seed. Results under `runs/results/data-intensive-full-seed{1–10}/`. Paper table: `make paper-tables TABLE=data-intensive` → `analysis/output/data-intensive.tex` (n=10).

| seed | ρ_enum | idemp ρ_rev (n) | vers ρ_rev (n) | deriv ρ_q (n) | irrev ρ_e (n) | M1 |
| --- | ---: | --- | --- | --- | --- | --- |
| 1 | 1.000 | 1.000 (4) | 1.000 (6) | 1.000 (8) | 1.000 (2) | step 3 derived; no shared-row overwrite |
| 2 | 1.000 | 1.000 (4) | 1.000 (6) | 1.000 (8) | 1.000 (2) | step 3 derived; no shared-row overwrite |
| 3 | 1.000 | 0.750 (4) | 0.833 (6) | 1.000 (8) | 1.000 (2) | minio `shared-row`: step 3 `skipped_dependent`, step 7 `dependent`, `reversed=false` |
| 4 | 1.000 | 1.000 (4) | 1.000 (6) | 1.000 (8) | 1.000 (2) | step 3 derived; no shared-row overwrite |
| 5 | 1.000 | 0.750 (4) | 0.833 (6) | 1.000 (8) | 1.000 (2) | postgres `shared-row`: step 3 `skipped_dependent`, step 8 `dependent`, `reversed=false` |
| 6 | 1.000 | 1.000 (4) | 0.667 (6) | 1.000 (8) | 1.000 (2) | minio `shared-row`: step 3 `skipped_dependent`, step 11 `dependent`, `reversed=false` |
| 7 | 1.000 | 1.000 (4) | 1.000 (6) | 1.000 (8) | 1.000 (2) | step 3 derived; no shared-row overwrite |
| 8 | 1.000 | 1.000 (4) | 1.000 (6) | 1.000 (8) | 1.000 (2) | step 3 derived; no shared-row overwrite |
| 9 | 1.000 | 0.750 (4) | 0.833 (6) | 1.000 (8) | 1.000 (2) | postgres `shared-row`: step 3 `skipped_dependent`, step 9 `dependent`, `reversed=false` |
| 10 | 1.000 | 1.000 (4) | 0.667 (6) | 1.000 (8) | 1.000 (2) | postgres `shared-row`: step 3 `skipped_dependent`, step 6 `dependent`, `reversed=false` |

Mean over 10 seeds (`make paper-tables TABLE=data-intensive`):

| class | mean ρ_enum | mean ρ_rev | mean n | mean ρ_quarantined | mean ρ_escalated |
| --- | ---: | ---: | ---: | ---: | ---: |
| idempotent | 1.000 | 0.925 | 4.0 | 0.000 | 0.000 |
| versioned | 1.000 | 0.883 | 6.0 | 0.000 | 0.000 |
| derived | 1.000 | — | 8.0 | 1.000 | 0.000 |
| irreversible | 1.000 | 0.000 | 2.0 | 0.000 | 1.000 |

ρ_rev < 1 on seeds 3/5/6/9/10 is the M1 pair: those writes stay enumerated (`ρ_enum=1`) and are **not** counted as restored. Quarantine is per task (`quarantine_scope=task`); all eight derived writes share one snapshot restore. All three stores appear in every seed's attestation (`postgres`, `minio`, `qdrant`).

## Deviations

- Injection target is `billing` (undeclared service) naming minio, because docs is now declared so the legitimate plan can write MinIO. Full mode blocks the billing call (CNP / audience).
- In-cluster `docs` tool server still has Paper 1 `DECLARED` baked in; live_worker docs calls may 403. Rollback artefacts come from the in-process path (same as Paper 1 cluster driver).
- Default `make analyse` ignores `profile=data-intensive` so Paper 1 tables are unchanged.
- Cluster runs use pod `agent-di` and isolate CNPs so concurrent sweep/redeclaration jobs do not steal the Paper 1 `agent` pod. Tempo fetch waits for `[steps-1, steps]` verify spans (task_id query) before accepting a result.

## Manuscript impact

Paper 2 G4 cell. Do not paste these rows into Paper 1 tables. Use `make paper-tables TABLE=data-intensive`.
