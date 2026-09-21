# Task 00 — Repository bootstrap and licence decision

## Built

- Private GitHub repository `open-gw/bounded-autonomy` already existed with an initial README; this task filled the Paper 1 layout.
- Directory tree matching the repository plan, `.gitignore`, `Makefile` (`make help` lists every later target), `rig/versions.yaml` with pinned cluster, store, telemetry, and Python package versions.
- `docs/study-design.md` (run manifest, metrics, `result.json`).
- `docs/design.md` (architecture summary with manuscript section pointers).
- `docs/NEW-MATTER.md` with header and empty list.
- MIT `LICENSE`.

## Licence decision

**MIT**, not Apache-2.0.

Apache-2.0 §3 is an express patent grant from contributors to users of the Work. A provisional filing that later becomes a utility patent would sit alongside that grant: anyone who uses this artefact would already hold a licence to the patented claims to the extent they are necessarily infringed by the licensed code. MIT has no express patent grant, so the copyright licence for reproduction (the thing reviewers and ICSA artefact evaluation need) is separated from the patent position.

MIT still allows the repository to go public at arXiv posting without a further licence change. If a downstream distributor needs a patent peace clause, that is a later decision and would be recorded here.

## Deviations

- The task asked to add `docs/study-design.md` from “the existing design document unchanged.” No separate design document was present in this checkout or in sibling trees. The study-design file was therefore written from the repository plan (manifest fields, the four metric exporters, write-mix, two modes, one profile) so that Tasks 01–02 have a frozen contract. If an earlier design document is located, diff it against `docs/study-design.md` and record any drift in NEW-MATTER rather than silently overwriting.
- No application code in this task, per acceptance (“no code yet”). `make help` is the only executable surface.

## Manuscript impact

None. Licence choice is an artefact-track decision, not a Section VII claim.
