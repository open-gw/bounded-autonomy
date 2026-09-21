# Task 17 — Real spans, credentials, weights, controller clocks

## Defects this task closes

1. Verify-span durations were constants per mode. `spans.parquet` for cluster runs now comes from Tempo. `make analyse` refuses zero-variance verify durations.
2. Flat used a task-scoped SVID, so `τ/T` was 1.0 in both modes. Flat now presents a 24 h projected ServiceAccount token; full mints a task SVID and records its lifetime as issue→revoke. `τ` and `T` are epoch timestamps.
3. `R_w`, per-step `d`, and segment `p`/`q` were not exported. Weights are frozen in `rig/services.yaml` (records 3, docs 3, search 2, notify 2, others 1). Five extra `full` runs at `segmentation_granularity: step` produce mean/max ratio and `d`.

## Built

- Tool servers export a `verify` span around `verify_audience` via OTLP → collector → Tempo (`SimpleSpanProcessor`).
- Cluster driver runs the 30-step plan as HTTP from the `agent` pod, then pulls Tempo.
- Flat agent pod mounts a projected SA token (`expirationSeconds: 86400`). JWT `iat`/`exp` become `τ`.
- Full: SVID lifetime is issue at segment-ready through revoke at task end (`q`).
- Controller/driver: `p` = task start → CNP Valid, `d` = CRD apply → CNP Valid, `q` = task end → CNP gone.
- Step granularity patches the TaskDeclaration to the step's tool, records per-step `τ/T` and `d`, then restores the declared three before the reachable-set probe so `|S|` stays 3.

## Leftover Tempo traces (same `task_id`)

A SIGTERM'd `make run` that is retried with the same `task_id` can leave verify spans in Tempo. The next fetch used a two-hour lookback keyed only on `task_id`, so `long-multistep-full-step-seed2` ingested 58 verify spans (killed attempt + retry). Paper 1 tables do not use that file's verify stats, but a reviewer opening the repo would.

Two fixes, both required:

1. `fetch_spans` / `_tempo_from_controller` query Tempo only for this run's time window, so a retry cannot ingest leftover traces.
2. `assert_cluster_provenance` refuses any result whose verify-span count exceeds `steps_completed` (default 30). Zero-variance check is unchanged.

Re-run of `MODE=full SEED=2 GRANULARITY=step` after a fresh cluster (`make down && make up`) replaces that artefact. Expect 29 verify spans (injection blocked), `source=cluster`, `|S|=3`.

## Manuscript impact

Reach (`|S|` 8 vs 3, `|B∩R|` 1 vs 0) and rollback (`ρ_rev`, quarantine, escalate, `ρ_enum`) are unchanged in intent. Overhead, `τ/T`, `R_w`, `p`/`q`/`d` replace the synthetic columns. Write-mix 11/10/6/3 vs 11/9/6/3 is the injection landing as versioned in flat and being blocked in full (29 writes).
