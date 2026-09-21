# Task 05 — Observer and telemetry

## Built

- Probe rows `(step, service, success)` written at each step boundary (simulator always; cluster Job stub installed by `make up`).
- Hubble `FORWARDED` flows mapped to `destination_service` in `flows.parquet`.
- OTel collector + Tempo manifests. Span names documented in `docs/design.md`. `verify` spans carry `mode`.
- Acceptance encoded in `tests/test_rig.py`: same declaration, `|S|=3` full and `|S|=8` flat.

## Deviations

- Cluster Hubble export is a `kubectl`/Hubble-CLI scrape in the cluster driver; `make test` uses the simulator’s equivalent FORWARDED rows so the metric is pinned before Hubble exists.

## Manuscript impact

Span name `verify` is now a claim. The manuscript must use that name in the overhead table.
