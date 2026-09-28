# Task 30 — ICSA submission packaging

Recorded 28 September 2026. Does not re-run the Task 26 60-seed campaign. Does not invent DOIs. Does not fill `docs/findings/23-venue.md` (ICSA 2027 CFP is user-owned).

## What this task did

| Item | Status |
| --- | --- |
| Refresh [`ARTIFACT.md`](../../ARTIFACT.md) | Done. Maps headline tables plus every `TABLE=` selector. Documents median [IQR] / bootstrap CI from Task 26. |
| `make paper-tables-all` | Done on this host over committed `source=cluster` `result.json` plus local `spans.parquet` (campaign parquet copied from the Task 26 worktree; parquet is gitignored). Simulator/fixtures refused. |
| Tag `v1.1-icsa-submission` | Annotated tag on `d7a5ff6e2526b36e937c782d02edfd258be661bf`. |
| GitHub release | https://github.com/open-gw/bounded-autonomy/releases/tag/v1.1-icsa-submission (published 2026-09-28T11:31:14Z). |
| Zenodo software version DOI for this tag | **Pending.** Polled Zenodo API after the hook: concept [10.5281/zenodo.23004818](https://doi.org/10.5281/zenodo.23004818) still has one version, [10.5281/zenodo.23004819](https://doi.org/10.5281/zenodo.23004819) (`v1.0.1-paper1`). Preprint [10.5281/zenodo.23004531](https://doi.org/10.5281/zenodo.23004531). GitHub `release`/`released` delivery was `OK`; follow-up `created`/`published` returned `409` (same pattern as Task 22). Do not invent a DOI. When Zenodo lists a new version, record it in `README.md`, `CITATION.cff`, and `.zenodo.json`. |
| Anonymised mirror | `make anonymous` → `dist/bounded-autonomy-anonymous/` and `.tar.gz`. Grep-clean for author names and ORCID (packager and its unit test are omitted from that tree). |

## `make paper-tables` (cluster only)

All selectors exited 0. Captions below are from the generated files, not from fixtures.

| Selector | File | Caption n |
| --- | --- | ---: |
| (default) | `analysis/output/tables.tex` | headline Reach `flat` n=10 / `full` n=10; Dispersion n=20 |
| `TABLE=dispersion` | `dispersion.tex` | task n=20; gateway n=30 |
| `TABLE=sweep` | `sweep.tex` | n=20 |
| `TABLE=evasion` | `evasion.tex` | n=20 |
| `TABLE=gateway` | `gateway.tex` | n=30 |
| `TABLE=redeclaration` | `redeclaration.tex` | n=5 |
| `TABLE=step-split` | `step-split.tex` | n=2 |
| `TABLE=data-intensive` | `data-intensive.tex` | n=10 |

Median [IQR] for reachable-set size matches Task 26 findings: `flat` 8.000 [8.000, 8.000], `full` 3.000 [3.000, 3.000], `full+bypass` 3.000 with `|B ∩ R|` 0, gateway-only/bypass `|S|` 8 with `|B ∩ R|` 1. Gateway product is Apache APISIX / `uri-blocker`. Not Kong.

Headline Reach/Rollback/Overhead numbers in `tables.tex` are ten-seed means. Paste Dispersion from `TABLE=dispersion`. Do not paste default `tables.tex` captions that still print `n=97` (that is every gated file in the tree, including sweep and data-intensive); the per-mode `n` columns in the Reach tabular are the ones that belong in the manuscript.

## User-owned (not done here)

1. ICSA 2027 CFP dates and checklist → `docs/findings/23-venue.md`.
2. Integrity pass on the final manuscript `.tex` (author names, `\val{}` vs these tables).
3. arXiv upload.
4. ICSA submission click.
5. Zenodo preprint record `23004531` related-identifier **isSupplementedBy** the software version DOI (still the Task 22 UI click if the new version DOI is not minted yet; when it is, add that version DOI as well).
6. Zenodo GitHub settings flip if the hook does not ingest `v1.1-icsa-submission`.

## Integrity (this repository tree, identified)

Author names and ORCID stay in `LICENSE`, `CITATION.cff`, `.zenodo.json`, `README.md`, and `docs/findings/22-repository-doi.md` on the identified archive. The anonymised mirror is the double-blind artefact.
