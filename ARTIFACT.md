# Paper 1 artefact map

What an ICSA artefact reviewer needs first: how each manuscript table and figure is produced, which files hold the numbers, and which commands refuse simulator or synthetic-span inputs.

Cite this artefact with [`CITATION.cff`](CITATION.cff). Study contract: [`docs/study-design.md`](docs/study-design.md). Architecture and manuscript section map: [`docs/design.md`](docs/design.md). Tag `v1.1-icsa-submission` is the ICSA revision archive.

Nothing fills manuscript `\val{}` slots except `make analyse` / `make paper-tables` over `source=cluster` results. Simulator fixtures and leftover/missing Tempo traces must not enter the manuscript.

## Reproduce Section VII (ICSA revision)

One-node k3d cluster on the measurement host in [`docs/findings/12-reproducibility.md`](docs/findings/12-reproducibility.md). Profile `long-multistep`. Headline cells: modes `flat` and `full`, seeds `1`–`10`, plus ten `full` runs at `GRANULARITY=step`. Gateway, sweep, evasion, re-declaration, step-split, and data-intensive cells use the dedicated `TABLE=` selectors below. Do not re-run the exclusive 60-seed campaign unless those `result.json` files are missing; they are committed on this tag.

```bash
make up
make campaign PROFILE=long-multistep \
  MODES=flat,gateway-only,gateway-bypass,full,full+bypass \
  SEEDS=1-10
make campaign PROFILE=long-multistep MODES=full SEEDS=1-10 GRANULARITY=step
make paper-tables-all   # headline + every TABLE= selector; same provenance gate
make down
```

`make campaign` skips a run whose `result.json` already has `source=cluster` and a passing per-run provenance guard. Paper 1 seeds 1–5 (`flat`, `full`, `full-step`) stay the pre-revision files.

`make run` writes `runs/results/{run_id}/`. `analysis/compute_result.py` folds the exporters into `result.json`. Only `result.json` is committed; Parquet stays local (see `.gitignore`). `make paper-tables` still needs local `spans.parquet` for the verify-span variance and count gate.

`make analyse` and `make paper-tables` both call `analysis/tables.py` and **exit 1** unless every gated `result.json` has `source=cluster`, `spans.parquet` verify-span durations with non-zero variance, and verify-span count in `[steps_completed-1, steps_completed]` (`flat` must match `steps_completed` exactly).

Paste from the dedicated `TABLE=` files when a selector exists. Default `make paper-tables` writes headline Reach / Rollback / Overhead / Credentials / Segment / Step plus Dispersion (median [IQR] and bootstrap 95% CI for the median, 1000 resamples, RNG seed 26). Each caption prints **that selector’s n** (Reach/Q2 n=20, Step n=10, Sweep n=20), never the whole-tree n=97. Gateway, sweep, evasion, re-declaration, step-split, and data-intensive rows are excluded from the headline Reach table so 3-vs-8 stays 3-vs-8. Evasion split and `gateway_403`: [`docs/findings/32-evasion-gateway.md`](docs/findings/32-evasion-gateway.md).

## Table and figure map

| Manuscript item | Command | Produced files | Inputs |
| --- | --- | --- | --- |
| Reach table (mean/min/max \|S\|, extra, \(R_w\)) | `make analyse` / `make paper-tables` | `analysis/output/tables.md` § Reach; `analysis/output/tables.tex` `% Reach` | `runs/results/long-multistep-{flat,full}-seed{1–10}/result.json` |
| Rollback table (per-class \(\rho_{\mathrm{rev}}\), restored/quarantined/escalated) | `make analyse` / `make paper-tables` | `tables.md` § Rollback; `tables.tex` `% Rollback` | `result.json` → `metrics.rollback_completeness` |
| Overhead table (mean `verify_ms`, relative vs same-seed `flat`) | `make analyse` / `make paper-tables` | `tables.md` § Overhead; `tables.tex` `% Overhead` | `result.json` → `metrics.verification_overhead`; `spans.parquet` (`name=verify`) |
| Credentials (Q2) \(\tau\), \(T\), \(\tau/T\) | `make analyse` / `make paper-tables` | `tables.md` § Credentials; `tables.tex` `% Credentials` | `result.json` → `tau_seconds`, `T_seconds`, `credential_ratio` |
| Segment \(p/q/d\) (Q4) | `make analyse` / `make paper-tables` | `tables.md` § Segment; `tables.tex` `% Segment` | `result.json` → `segment_p_ms`, `segment_q_ms`, `d_ms_mean`, `d_ms_max` |
| Step granularity | `make analyse` / `make paper-tables` | `tables.md` § Step; `tables.tex` `% Step` | `runs/results/long-multistep-full-step-seed{1–10}/result.json` |
| Dispersion (M6) median [IQR] + bootstrap 95% CI | `make paper-tables TABLE=dispersion` | `analysis/output/dispersion.tex` / `.md` / `.json` | task `flat`/`full` seeds 1–10 plus gateway cells; schema `schemas/dispersion.schema.json` |
| Gateway cells (APISIX `uri-blocker`, not Kong) | `make paper-tables TABLE=gateway` | `analysis/output/gateway.tex` / `.md` | `long-multistep-{gateway-only,gateway-bypass,full-bypass}-seed{1–10}`; column `gateway_403` from `gateway.parquet` 403s |
| Declaration tightness sweep (k/\|S\|, §7.4) | `make paper-tables TABLE=sweep` | `analysis/output/sweep.md` / `.tex` | `long-multistep-k{1,3,5,7}-full-seed{1–5}` |
| Evasion matrix (9 probes × verdict; 3a/3b and 6a/6b split) | `make paper-tables TABLE=evasion` | `analysis/output/evasion.tex` / `evasion.md` | `result.json` → `evasion_matrix` (rows 1–9); `evasion.parquet`. Do not paste 5/10. Per-seed table includes CNP Valid timestamps. |
| Re-declaration cost (M4 Q4) | `make paper-tables TABLE=redeclaration` | `analysis/output/redeclaration.md` / `.tex` | `redeclaration-full-seed{1–5}` (`redeclaration_cost_ms`) |
| Per-step cost split (probe on/off) | `make paper-tables TABLE=step-split` | `analysis/output/step-split.md` / `.tex` | `long-multistep-full-step-{split,noprobe}-seed{n}` |
| Data-intensive profile (G4 / Q3) | `make paper-tables TABLE=data-intensive` | `analysis/output/data-intensive.md` / `.tex` | `data-intensive-full-seed{1–10}` |
| Q2 grouped-bar figure (\|S\| by seed and mode) | `make analyse` | `analysis/output/q2-reachable-set.png` | same `result.json` set as Reach |
| `\val{}` slots | cluster `result.json` only, never `analysis/fixtures/` | committed under `runs/results/` | produced by `make run` / `make campaign` after `make up` |
| Section VI measurement host | (recorded, not generated) | [`docs/findings/12-reproducibility.md`](docs/findings/12-reproducibility.md) | Apple M3 Pro, 12-core, 18 GiB, Darwin 25.5.0, Docker 29.7.2 / Desktop 4.87.0 |

`make paper-tables-all` runs the default target and every `TABLE=` selector above. Generated files under `analysis/output/` are local (gitignored); the committed record of the numbers is `docs/findings/26-campaign.md` through `32-evasion-gateway.md` plus this map.

Pre-registered Markdown notebook (synthetic fixtures only, **not** manuscript-pasteable): `make notebook` → `analysis/notebook.ipynb` on `analysis/fixtures/results/`.

## Per-run layout

`runs/results/{profile}-{mode}-seed{n}/` and `…-full-step-seed{n}/`:

| File | Role |
| --- | --- |
| `result.json` | committed summary; `source` must be `cluster` for tables |
| `probe.parquet` | reachable-set probe |
| `flows.parquet` | Hubble `FORWARDED` flows |
| `spans.parquet` | OTel/Tempo; provenance checks `verify` durations and count |
| `lineage.parquet` | OpenLineage events |
| `groundtruth.parquet` | store-level rollback truth |
| `svid.parquet` | SPIRE issue/expiry for \(\tau\) |
| `evasion.parquet` | nine-probe evasion matrix (Task 32 split of Task 23 rows 3 and 6; optional on older runs) |
| `gateway.parquet` | APISIX access log (Task 24; optional on non-gateway runs) |

Headline run ids: `long-multistep-flat-seed{1–10}`, `long-multistep-full-seed{1–10}`, `long-multistep-full-step-seed{1–10}`. Directories whose path parts start with `_` are ignored by `analysis/tables.py`.

## Hardware spec (findings 12)

Timing figures without this host are not reproducible. Canonical record: [`docs/findings/12-reproducibility.md`](docs/findings/12-reproducibility.md) (Section VI of the manuscript map in `docs/design.md`). Task 26 campaign host is the same machine (`docs/findings/26-campaign.md`). Lima VM numbers are not mixed in.

## Anonymised mirror

`make anonymous` writes `dist/bounded-autonomy-anonymous/` from `HEAD` with author names, ORCID, and measurement-host hostname removed, then greps the tree. That tree is for double-blind artefact evaluation. The GitHub/Zenodo archive of `v1.1-icsa-submission` stays identified.

## Out of scope

Paper 2 surfaces (Cilium mutual authentication, multi-node, hosted LLM backend) are not in this repository. `make run` without a successful `make up` writes `source=simulator`; those numbers must not be pasted into the manuscript. Gateway product is Apache APISIX; plugin is `uri-blocker`. Not Kong.
