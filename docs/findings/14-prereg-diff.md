# Task 14 — Restore pre-registration

## Original not found

Task 00 asked to copy `docs/study-design.md` from “the existing design document unchanged.” That file was not in the checkout then, and it is still not on this machine.

Searched (2026-09-21): this repo and `open-gw/` siblings; `~/m3pro`; `~/Downloads` (including the EB1A paper tree, AGA provisional, INTCEC/ESWA drafts); `~/Documents`; `~/Desktop`; Cursor conversation index (only this chat). Needles: `long-multistep`, `write_mix`, `rho_rev`, `reachable_set`, `ICSA`, `blast radius`, `bounded-autonomy`. No matching document.

Therefore `docs/study-design.md` was **not** replaced. Replacing it with a newly authored stand-in would be a second reconstruction, which this task forbids.

## Diff against Cursor’s reconstruction

There is nothing to diff. The file in tree *is* the reconstruction (plus the Task 13 `source` field). When the original is provided, the procedure is:

1. Copy it onto `docs/study-design.md` unchanged.
2. Diff it against git history of this file (commit `74838ad` is the reconstruction at first freeze; Task 13 added `source`).
3. Append the actual field-by-field delta to this findings file.
4. If write-mix or a metric formula differs, change the notebook/`analysis/metrics.py`, not the original document.
5. Re-run tests.

## Tests

Re-run after Task 13 (provenance tests added; suite is 27, not 26):

```
make test
```

Expected: pass. No notebook/metric formula change, because no original formula was available to disagree with.

## Manuscript impact

None. Do not treat the reconstruction as the pre-registration of record until the original is restored or the author explicitly ratifies this file as the original.
