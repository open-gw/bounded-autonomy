# Task 02 — Metric implementations and analysis notebook

## Built

- `analysis/metrics.py`: `reachable_set`, `credential_ratio`, `rollback_completeness`, `verification_overhead`.
- Unit tests with constructed answers (`tests/test_metrics.py`).
- `analysis/tables.py` emits the three manuscript tables as paste-ready Markdown.
- `analysis/notebook.ipynb` reads five `result.json` per mode. `scripts/build_fixtures.py` writes a synthetic ten-run set so the notebook/analyse path runs before any cluster exists.
- `make test`, `make fixtures`, `make notebook`, `make analyse`.

## Deviations

- `make analyse` is a Python module, not only a notebook, so a machine without a registered Jupyter kernel still emits the tables. The notebook calls the same functions.
- Synthetic fixtures encode the Paper 1 *claims* (full `|S|=3`, flat `|S|=8`, `rho_rev=1.0` for reversible classes). Real runs must replace them; the notebook must not be edited to match disappointing data.

## Manuscript impact

Table column headers are now fixed (mean `|S|`, min, max, mean extra; per-class `rho_rev`; `verify_ms` and relative overhead). If the manuscript draft uses different headers, align the draft to these, not the other way around — this notebook is the pre-registration.
