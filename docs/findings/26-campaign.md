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

Acceptance: 50 task-level + 10 step, every committed campaign `result.json` has `source=cluster`.

## Dispersion

`make analyse` and `make paper-tables` keep the Paper 1 mean/min/max columns and add **median [IQR]** plus a bootstrap 95% CI for the median (1000 resamples, RNG seed 26). Schema: [`schemas/dispersion.schema.json`](../../schemas/dispersion.schema.json). JSON: `analysis/output/dispersion.json`.

Paper 1 seeds 1–5 `full` still carry pre-Task-25 issue→revoke τ. Seeds 6–10 and all gateway cells use JWT-SVID TTL (`exp − iat`). Reachable-set medians are not affected by that mix.

## Key medians

Filled after the exclusive campaign completes.

| mode | metric | n | median [IQR] | 95% CI |
| --- | --- | ---: | --- | --- |
| _(pending)_ | | | | |

## Host / lock

| Item | Value |
| --- | --- |
| Host | Apple M3 Pro, Darwin 25.5.0 (`Rinus-MBP-M3.local`) |
| Exclusive | pending |
| `make down && make up` | pending |
| git HEAD of the 60-run set | pending |
