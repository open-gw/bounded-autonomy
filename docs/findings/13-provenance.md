# Task 13 — Result provenance guard

## Built

- `source: simulator | cluster` is a required field on `result.json` (`schemas/result.schema.json`).
- The in-process driver writes `simulator`. Fixtures are tagged `simulator`.
- `make analyse` exits 1 unless every input is `source=cluster`, with a list of offending paths on stderr.
- The notebook prints `source=…` in every table/figure caption. Simulator captions are not manuscript-pasteable.

## Deviations

- None relative to this task spec. After Task 12, `cluster_driver.py` overwrites `result.json` with `source: cluster`; the in-process path still writes `simulator`.

## Manuscript impact

None until ten `cluster` files exist. This guard is what keeps the 44 `\\val{}` slots empty until then.
