# Task 12 — Reproducibility pass

## Built

- README lists the only commands a second person needs: venv, `make test`, `make up`, `make run` × 10, `make analyse`, `make down`.
- Pins are in `rig/versions.yaml`.
- `make test` (schema, metrics, mix, rollback, reachable-set) is the offline reproducibility gate.

## Deviations

- A fresh-VM wall-clock capture of ten cluster runs is **not** in this commit. That is the remaining Paper 1 gate: clone on a clean machine, follow only the README, record wall-clock, and paste the tables. Anything that required unwritten knowledge during that pass gets added to the README and to this file.

## Manuscript impact

Do not submit until this pass has been done. The artefact reviewers will do the same.
