# Task 09 — Rollback and attestation

## Built

- `rig/rollback/procedures.py`: lineage writes ordered by step; idempotent/versioned restore from history; derived snapshot+quarantine; irreversible escalate.
- `attestation.json` lists write, class, action, and ground-truth `before` match.
- Tests: on a (simulated) drifted/clean run, `rho_rev = 1.0` for idempotent and versioned; derived quarantined; irreversible `escalated: true`.

## Deviations

- Rollback is applied to the in-memory stores after the run (and will be applied to live stores by the same procedures once the cluster driver calls them). Order is reverse-by-step so later writes are undone first.

## Manuscript impact

Attestation field names: `action`, `matches_before`, `quarantined`, `escalated`. Use those in the appendix.
