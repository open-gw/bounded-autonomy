# Paper 1 artefact map

What an ICSA artefact reviewer needs first: how each manuscript table and figure is produced, which files hold the numbers, and which commands refuse simulator or synthetic-span inputs.

Cite this artefact with [`CITATION.cff`](CITATION.cff). Study contract: [`docs/study-design.md`](docs/study-design.md). Architecture and manuscript section map: [`docs/design.md`](docs/design.md).

## Reproduce Section VII

One-node k3d cluster, profile `long-multistep`, modes `flat` and `full`, seeds `1`–`5`, plus five `full` runs at `GRANULARITY=step`. Hardware for every timing number: [`docs/findings/12-reproducibility.md`](docs/findings/12-reproducibility.md).

```bash
make up
for mode in flat full; do
  for seed in 1 2 3 4 5; do
    make run PROFILE=long-multistep MODE=$mode SEED=$seed
  done
done
for seed in 1 2 3 4 5; do
  make run PROFILE=long-multistep MODE=full SEED=$seed GRANULARITY=step
done
make analyse        # Markdown tables + Q2 figure; provenance gate
make paper-tables   # LaTeX-ready tabular rows; same gate
make down
```

`make run` writes `runs/results/{run_id}/`. `analysis/compute_result.py` folds the six Parquet exporters into `result.json`. Only `result.json` is committed; Parquet stays local (see `.gitignore`).

`make analyse` and `make paper-tables` both call `analysis/tables.py` and **exit 1** unless every `result.json` has `source=cluster`, `spans.parquet` verify-span durations with non-zero variance, and verify-span count in `[steps_completed-1, steps_completed]` (`flat` must match `steps_completed` exactly). Simulator fixtures and leftover/missing Tempo traces must not enter the manuscript.

## Table and figure map

| Manuscript item | Command | Produced files | Inputs |
| --- | --- | --- | --- |
| Reach table (mean/min/max \|S\|, extra, \(R_w\)) | `make analyse` / `make paper-tables` | `analysis/output/tables.md` § Reach; `analysis/output/tables.tex` `% Reach` | `runs/results/*/result.json` (`metrics.reachable_set_size`, `reachable_weight`); underlying `probe.parquet` + `flows.parquet` |
| Rollback table (per-class \(\rho_{\mathrm{rev}}\), restored/quarantined/escalated) | `make analyse` / `make paper-tables` | `tables.md` § Rollback; `tables.tex` `% Rollback` | `result.json` → `metrics.rollback_completeness`; underlying `lineage.parquet` + `groundtruth.parquet` |
| Overhead table (mean `verify_ms`, relative vs same-seed `flat`) | `make analyse` / `make paper-tables` | `tables.md` § Overhead; `tables.tex` `% Overhead` | `result.json` → `metrics.verification_overhead`; underlying `spans.parquet` (`name=verify`) |
| Credentials (Q2) \(\tau\), \(T\), \(\tau/T\) | `make analyse` / `make paper-tables` | `tables.md` § Credentials; `tables.tex` `% Credentials` | `result.json` → `tau_seconds`, `T_seconds`, `credential_ratio`; underlying `svid.parquet` + `spans.parquet` |
| Segment \(p/q/d\) (Q4) | `make analyse` / `make paper-tables` | `tables.md` § Segment; `tables.tex` `% Segment` | `result.json` → `segment_p_ms`, `segment_q_ms`, `d_ms_mean`, `d_ms_max` |
| Step granularity | `make analyse` / `make paper-tables` | `tables.md` § Step; `tables.tex` `% Step` | `runs/results/long-multistep-full-step-seed{1–5}/result.json` (`declaration.granularity=step`) |
| Q2 grouped-bar figure (\|S\| by seed and mode) | `make analyse` | `analysis/output/q2-reachable-set.png` | same `result.json` set as Reach; series also in `tables.md` § Q2 / `tables.tex` `% Q2 series` |
| `\val{}` slots | filled from the cluster `result.json` files, not from `analysis/fixtures/` | `runs/results/long-multistep-{flat,full}-seed{1–5}/result.json` (ten task-granularity runs) plus five step runs | produced by `make run` after `make up` |
| Section VI measurement host | (recorded, not generated) | [`docs/findings/12-reproducibility.md`](docs/findings/12-reproducibility.md) | Apple M3 Pro, 12-core, 18 GiB, Darwin 25.5.0, Docker 29.7.2 / Desktop 4.87.0 |

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

Run ids: `long-multistep-flat-seed{1–5}`, `long-multistep-full-seed{1–5}`, `long-multistep-full-step-seed{1–5}`. Directories whose path parts start with `_` are ignored by `analysis/tables.py`.

## Hardware spec (findings 12)

Timing figures without this host are not reproducible. Canonical record: [`docs/findings/12-reproducibility.md`](docs/findings/12-reproducibility.md) (Section VI of the manuscript map in `docs/design.md`). That file lists CPU, cores, memory, kernel, Docker, k3d/k3s/Cilium/SPIRE pins, and the git HEAD of the fifteen-run set.

## Out of scope

Paper 2 surfaces (Cilium mutual authentication, multi-node, hosted LLM backend) are not in this repository. `make run` without a successful `make up` writes `source=simulator`; those numbers must not be pasted into the manuscript.
