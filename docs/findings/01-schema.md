# Task 01 — Result schema and run manifest validation

## Built

- `schemas/manifest.schema.json` and `schemas/result.schema.json` from study-design §§1 and 5.
- `scripts/validate_manifest.py` plus extra-schema rules: write-mix sums to 1.0 ± 1e-9, declared ∪ undeclared equals the eight-service inventory, injection target ∈ undeclared.
- Example manifests `runs/manifests/long-multistep-{flat,full}.yaml`.
- `tests/test_schema.py`.

## Deviations

- JSON Schema cannot express “sum to 1.0”; that check is in the validator, not the schema file. Study-design §1 already called this an extra-schema rule.

## Manuscript impact

None. Field names are now frozen; `\val{}` slots consume `result.json` of this shape.
