# Task 25 — SPIRE credential semantics (M2 Q1, Q3)

Recorded 28 September 2026 on the M3 Pro. Public SPIRE 1.15 docs only (`spiffe.io` server configuration / registering workloads: `-jwtSVIDTTL`, `jwt mint`, `entry delete`). Smoke artefacts: `runs/results/_smoke-t25-full/`, `_smoke-t25-flat/`, `_label-race/` (`_` prefixes so `make analyse` ignores them). Paper 1 campaign `runs/results/long-multistep-*` is unchanged.

## τ definition (Q1)

τ is the **SVID TTL**: `exp − iat` of the minted JWT-SVID (full) or the projected ServiceAccount token (flat). It is **not** issue-to-delete and **not** registration-entry deletion.

- Task credentials: JWT-SVIDs. TTL = `expectedDurationSeconds` (task, 1800 s here) or `expectedStepDurationSeconds` (step, default 60 s). Minted with `spire-server jwt mint -ttl <n>s` against a registration entry whose `-jwtSVIDTTL` matches.
- X.509 SVIDs: pod-level only (`spiffe://rig/workload/agent`, TTL 3600 s = server `default_x509_svid_ttl`).
- Registration-entry deletion still happens at task end (no renewal). The timestamp is `entry_deleted_at_epoch`. SPIRE documents `entry delete` as data-management, not a security revocation of already-issued SVIDs.
- `credential_ratio = τ / T` with `credential_ratio_derivation` in `result.json` (`formula`, `tau_definition`, `tau_seconds`, `T_seconds`, `credential_kind`).

Paper 1 `full` tables recorded issue→revoke so `τ ≈ T` and `τ/T ≈ 1`. That claim is withdrawn (NEW-MATTER). Under the revised definition a full run with TTL 1800 s and a ~2.5 s task has `τ/T ≫ 1`.

## Residual (every full run)

| Window | Formula | Smoke full seed 1 |
| --- | --- | --- |
| (a) SVID residual | `exp − task_end` | **1795.461 s** (`exp − iat` = 1800; task ended ~4.5 s after `iat`) |
| (b) Policy residual | `policy_removed_at − task_end` | **0.469 s** (`segment_q_ms` = 469.1 ms; Paper 1 `q` was ~351–363 ms) |

`entry_deleted_at_epoch` is recorded separately and is not used as `not_after`.

## Per-step

A new JWT-SVID is minted per step. `svid.parquet` rows carry `iat`, `exp`, `step_start_epoch`, `step_end_epoch`. Step `τ/T` uses TTL / step wall, not step issue-to-end.

## Label race (Q3)

One agent pod hosted task A (`records` allow-list). An HTTP/1.1 keep-alive TCP to `records` ClusterIP `10.43.116.111:8081` was held open. The pod was relabelled A→B and B’s CNP allowed only `search`.

Observed (`runs/results/_label-race/result.json`):

- First request under A: **ok**
- Held-open second request after relabel: **survived** (`held_open_survived: true`)
- New TCP to records after relabel: **allowed** (identity/CNP update did not isolate the reused pod in this window)

**Threat to validity:** yes. A task-id label change on a live pod does not immediately drop an established connection, and in this run it also failed to block a new connect. Mitigation already used by `make run`: **one pod per task** (`_ensure_agent` deletes the agent pod before each run). Do not claim same-pod sequential tasks are isolated by relabel alone.

## Smoke

| Run | `source` | `|S|` | τ (s) | T (s) | τ/T | residual (a)/(b) |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `_smoke-t25-full` | cluster | 4 | 1800 | 2.497 | 720.756 | 1795.461 / 0.469 |
| `_smoke-t25-flat` | cluster | 8 | 86400 | 0.388 | 222611 | null / null |

Full `|S|=4` (catalog leaked) is concurrent Task 23/24 datapath work on the shared cluster, not a credential-semantics defect. `docs` was not in the reachable set (`breach_intersection` empty). Flat `|S|=8` matches the Paper 1 flat claim. Both `result.json` files carry `credential_ratio_derivation` with `tau_definition: exp - iat`.
