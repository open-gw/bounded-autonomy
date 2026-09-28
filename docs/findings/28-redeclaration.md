# Task 28 — Re-declaration cost and per-step cost split (M4 Q4)

Recorded 28 September 2026 on the M3 Pro. Uses Task 25 τ = JWT-SVID TTL (`exp − iat`). Residual windows stay in `result.json`. Paper 1 campaign `runs/results/long-multistep-*` is unchanged.

## Re-declaration

Profile `redeclaration` is the Paper 1 mix (30 steps, 40/30/20/10) with the Paper 1 initial allow-list `[records, search, notify]`. Injection is **off**. The seeded step plan names `docs` at step 15 as a legitimate requirement, not drift.

The orchestrator terminates when `pick_tool` raises `UndeclaredTool`, re-declares with `docs` added, re-provisions the CNP, remints the JWT-SVID, and resumes at step 15. Steps 1–14 are not replayed.

| Field | Meaning |
| --- | --- |
| `redeclaration_cost_ms` | Wall from termination to the first tool call of the resumed task |
| `steps_reexecuted` | 0 (resume, not replay) |
| `writes_committed_before_termination` | Prior store keys still present after re-bind |

Median over 5 cluster seeds is the headline number. `make paper-tables TABLE=redeclaration`. Default `make analyse` ignores this profile.

## Per-step split (G8)

Step-granularity with `STEP_SPLIT=1`. Probe on is the default; probe off is `observer.probe: false` / `PROBE=0`. With probe off the reachable set is `FORWARDED` flows only (successful tool-call destinations).

Each boundary records:

| Clock | What |
| --- | --- |
| propagation | TaskDeclaration apply + CNP Valid |
| SVID reissue | `jwt mint` (`τ = exp − iat`) |
| probe | TCP connect to the eight inventory services (0 when probe is off) |
| other | Residual of observed boundary duration |

`propagation + SVID + probe + other` must match observed `boundary_ms` within 5% (`step_cost_split.reconcile_error_pct`). `make paper-tables TABLE=step-split`. Run ids `long-multistep-full-step-split-seed{n}` and `…-step-noprobe-seed{n}` so Paper 1 `…-full-step-seed{n}` is not overwritten.

## Schema

Additive optional fields on `result.json`: `redeclaration_cost_ms`, `steps_reexecuted`, `writes_committed_before_termination`, `observer.probe`, `step_cost_split`. Manifest `spec.profile` includes `redeclaration`; `spec.observer.probe` is optional. Frozen study-design §§3.5–3.6 and §4.1 note the amendment.

## Campaign

`source=cluster`. Results under `runs/results/redeclaration-full-seed{1–5}/` and the step-split / noprobe dirs above.

Median **redeclaration_cost_ms = 7070.3**. Writes before termination stayed committed on every seed; no steps were re-executed.

| seed | redeclaration_cost_ms | steps re-executed | writes committed |
| ---: | ---: | ---: | --- |
| 1 | 7070.3 | 0 | yes |
| 2 | 2739.5 | 0 | yes |
| 3 | 62599.2 | 0 | yes |
| 4 | 66996.8 | 0 | yes |
| 5 | 2923.0 | 0 | yes |

Seeds 3–4 sat behind concurrent CNP/SPIRE work on the shared node; the median is the uncontended-plus-one middle value.

### Per-step split (seed 1)

| probe | propagation (ms) | SVID reissue (ms) | probe (ms) | other (ms) | boundary (ms) | reconcile % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| on | 85416.1 | 19383.8 | 268380.6 | 0.4 | 373181.0 | 0.00 |
| off | 66974.4 | 16829.8 | 0.0 | 0.5 | 83804.7 | 0.00 |

Probe dominates the on-path boundary. With probe off, `|S|=3` from flows only. Both rows reconcile at 0%.

## Manuscript impact

Paper 2 M4 Q4. Do not paste these rows into Paper 1 tables. τ definition is unchanged from Task 25.
