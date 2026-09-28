# Task 26 — Ten-seed campaign with dispersion (M6)

Recorded 28 September 2026 on the **Apple M3 Pro** (same host as [`12-reproducibility.md`](12-reproducibility.md): Darwin 25.5.0, 12-core, 18 GiB). Lima VM numbers are not used in this file.

## Command

```bash
make campaign PROFILE=long-multistep \
  MODES=flat,gateway-only,gateway-bypass,full,full+bypass \
  SEEDS=1-10
make campaign PROFILE=long-multistep MODES=full SEEDS=1-10 GRANULARITY=step
make analyse
make paper-tables
```

`make campaign` skips a run whose `result.json` already has `source=cluster` and a passing per-run provenance guard (verify-span variance and count). That is how Paper 1 seeds 1–5 (`flat`, `full`, `full-step`) stay untouched.

## Exclusive cluster

Task 24’s full+bypass smoke was polluted (`|S|=7`) by a concurrent Task 27 sweep. This campaign waits for other `make run` / `make campaign` processes, then takes `/tmp/ba-campaign.lock`. Cluster bring-up on this host is recorded below; the cluster was exclusive for the 60-run set.

## Cells

| Cell | Run id | n | Notes |
| --- | --- | ---: | --- |
| task `flat` | `long-multistep-flat-seed{1–10}` | 10 | seeds 1–5 pre-revision Paper 1; 6–10 this campaign |
| task `full` | `long-multistep-full-seed{1–10}` | 10 | same split |
| task `gateway-only` | `long-multistep-gateway-only-seed{1–10}` | 10 | APISIX `uri-blocker` |
| task `gateway-bypass` | `long-multistep-gateway-bypass-seed{1–10}` | 10 | ClusterIP; expect \|B ∩ R\| = 1 |
| task `full+bypass` | `long-multistep-full-bypass-seed{1–10}` | 10 | exclusive; expect \|S\| = 3, \|B ∩ R\| = 0 |
| step `full` | `long-multistep-full-step-seed{1–10}` | 10 | seeds 1–5 Paper 1; 6–10 this campaign |

Acceptance: 50 task-level + 10 step, every committed campaign `result.json` has `source=cluster`. **Met: 60/60 `source=cluster`.** `make analyse` caption `source=cluster (n=60)`. Simulator leftovers for full-step seeds 6–8 were overwritten on resume; they are not in the manuscript tables.

## Dispersion

`make analyse` and `make paper-tables` keep the Paper 1 mean/min/max columns and add **median [IQR]** plus a bootstrap 95% CI for the median (1000 resamples, RNG seed 26). Schema: [`schemas/dispersion.schema.json`](../../schemas/dispersion.schema.json). JSON: `analysis/output/dispersion.json` (local artefact; numbers below are the committed record).

Paper 1 seeds 1–5 `full` still carry pre-Task-25 issue→revoke τ. Seeds 6–10 and all gateway cells use JWT-SVID TTL (`exp − iat`). Reachable-set medians are not affected by that mix; `full` τ and τ/T IQRs are.

## Key medians

From `make analyse TABLE=dispersion` over cluster results. Reachable-set size is constant in every cell.

| mode | metric | n | median [IQR] | 95% CI |
| --- | --- | ---: | --- | --- |
| flat | \|S\| | 10 | 8.000 [8.000, 8.000] | 8.000–8.000 |
| flat | R_w | 10 | 14.000 [14.000, 14.000] | 14.000–14.000 |
| flat | verify_ms | 10 | 1.9 [1.6, 2.6] | 1.5–2.6 |
| full | \|S\| | 10 | 3.000 [3.000, 3.000] | 3.000–3.000 |
| full | R_w | 10 | 7.000 [7.000, 7.000] | 7.000–7.000 |
| full | verify_ms | 10 | 1.7 [1.3, 2.1] | 1.3–2.5 |
| gateway-only | \|S\| | 10 | 8.000 [8.000, 8.000] | 8.000–8.000 |
| gateway-only | \|B ∩ R\| | 10 | 1.000 [1.000, 1.000] | 1.000–1.000 |
| gateway-bypass | \|S\| | 10 | 8.000 [8.000, 8.000] | 8.000–8.000 |
| gateway-bypass | \|B ∩ R\| | 10 | 1.000 [1.000, 1.000] | 1.000–1.000 |
| full+bypass | \|S\| | 10 | 3.000 [3.000, 3.000] | 3.000–3.000 |
| full+bypass | \|B ∩ R\| | 10 | 0.000 [0.000, 0.000] | 0.000–0.000 |

`full` τ median 900.672 s with IQR [1.227, 1800.000] is the Paper 1 / Task 25 mix, not run-to-run jitter of one TTL definition. Do not paste simulator numbers.

Gateway product is Apache APISIX; plugin is `uri-blocker`. Not Kong.

## Provenance notes (step seeds 6–10)

The first step pass left seeds 6 and 8 with Tempo `0 verify spans` (collector export `Unavailable` / ingester ring `127.0.0.1:9095`) and seed 7 with a kubectl port-forward timeout to APISIX admin. Seed 9–10 then succeeded on the same cluster. Resume of 6, 7, 8 after a Tempo WAL/ingester config apply plus 90 s Tempo poll and three port-forward attempts produced `source=cluster` for all three. Nested `local.path=/tmp/tempo` with `wal.path=/tmp/tempo/wal` made Tempo poll a fake tenant `wal`; blocks now live at `/var/tempo/blocks` and WAL at `/var/tempo/wal`.

Step-granularity `d` for seed 9 has a 901990.4 ms max (one CNP wait during that run). That is a cluster measurement, not a Lima or simulator figure; it is not a reachable-set number.

## Host / lock

| Item | Value |
| --- | --- |
| Host | Apple M3 Pro, Darwin 25.5.0 (`Rinus-MBP-M3.local`) |
| Exclusive | yes (`/tmp/ba-campaign.lock`; no concurrent Task 27/28/29 campaign) |
| `make down && make up` | 2026-09-28T05:55:32Z |
| git HEAD of the 60-run set | this commit on `task-26-campaign` (campaign driver at `a03beb2` plus Tempo/port-forward provenance fixes used for full-step 6–8 resume) |
