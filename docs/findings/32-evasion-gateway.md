# Task 32 — Evasion split, gateway_403, caption n

Recorded 28 September 2026 on the Apple M3 Pro. `source=cluster` only. Waited until Task 31 released `/tmp/ba-campaign.lock` (stale pid 68074 was dead), then took the lock exclusively for the evasion attach and re-declaration seeds 3–4. Did not merge Task 31.

## What rows 3 and 6 actually were (before the split)

The pasted cell `refused (5/10)` was **not** “half the seeds allowed DNS / the API.” Consensus picked a winner on a tie.

Bundled `result.json` (Task 23 attach for seeds 1–5, Task 26 in-run for 6–10):

| Row | full seeds 1–5 | full seeds 6–10 | What the bundle hid |
| ---: | --- | --- | --- |
| 3 | `coredns_undeclared=refused`; `udp53_1.1.1.1=refused`; stored verdict **refused** | `coredns_undeclared=error`; `udp53_1.1.1.1=refused`; stored verdict **error** | UDP/53 was refused on all ten. CoreDNS undeclared was refused vs `error` (resolver errno), not allowed. |
| 6 | `dns=error`; `tcp_name=skipped`; `tcp_clusterip=refused`; stored **refused** | same detail string; stored **error** | ClusterIP TCP was refused in `detail` on all ten. Name lookup of `kubernetes.default.svc` failed (expected under `matchName`). |

`_evasion_consensus` ranked `(count, name)` so `refused` beat `error` on a 5–5 tie → **`refused (5/10)`**. That cell is not pasteable.

It was **bundling plus verdict-label disagreement**, not a policy-propagation race and not an allowed-by-design leak in the stored full-mode cells.

## Exclusive split re-run

`scripts/attach_evasion.py` seeds 1–10, modes `flat` and `full`, after CNP Valid + 5 s settle. Integer rows 1–9; display ids 3a/3b and 6a/6b. Each row carries `policy_propagation_ms`, `probe_epoch`, and (full) `seconds_after_cnp_valid`.

Full, every seed, **5.00–5.01 s after CNP Valid** (`cnp_valid_ms` 56–141):

| Display | Probe | full | leak |
| --- | --- | --- | --- |
| 3a | CoreDNS undeclared `docs.rig.svc.cluster.local` | refused (10/10) | none — not a name-resolution leak |
| 3b | raw UDP/53 to 1.1.1.1 | refused (10/10) | none |
| 6a | `kubernetes.default.svc:443` (name) | refused (10/10) | none |
| 6b | kubernetes ClusterIP:443 | refused (10/10) | none |

So after an exclusive attach, CoreDNS undeclared is a **policy refuse**, not a matchName name-resolution leak of reach. Direct-IP declared (row 1) stays allowed (identity). The old 5/10 does not reappear.

Flat 3b (UDP/53 to 1.1.1.1) is **allowed 9, refused 1** (seed 2 timed out at ~2004 ms, no CNP). The table lists both counts; it does not print `allowed (9/10)` as a false winner and it does not print `5/10`.

`make paper-tables TABLE=evasion`: source=cluster (**n=20**).

## gateway_403

Count of HTTP 403 rows in that run’s `gateway.parquet` (APISIX `uri-blocker`). Folded into `metrics.gateway_403` for gateway cells.

| Cell | \|S\| | \|B ∩ R\| | gateway_403 |
| --- | ---: | ---: | ---: |
| full+bypass | 3 | 0 | 0 (agent never hits APISIX) |
| gateway-bypass | 8 | 1 | 0 (ClusterIP) |
| gateway-only | 8 | 1 | **2** (two `POST /docs/tools/call`) |

`make paper-tables TABLE=gateway`: source=cluster (**n=30**).

## Re-declaration seeds 3 and 4

Old contention artefacts: seed 3 **62599.2 ms**, seed 4 **66996.8 ms**, median **7070.3**. Exclusive re-run (same lock as evasion, no concurrent campaign):

| seed | old (ms) | exclusive (ms) |
| ---: | ---: | ---: |
| 1 | 7070.3 | 7070.3 (unchanged) |
| 2 | 2739.5 | 2739.5 (unchanged) |
| 3 | 62599.2 | **1374.2** |
| 4 | 66996.8 | **2717.5** |
| 5 | 2923.0 | 2923.0 (unchanged) |

Median **2739.5**. Steps re-executed 0; writes committed yes, every seed. `TABLE=redeclaration` n=5.

## Caption n

Default `make paper-tables` captions used the whole loaded tree (**n=97**). They now use the selector:

| Caption | n |
| --- | ---: |
| Reach / Rollback / Overhead / Credentials / Segment / Q2 / Dispersion / all tables | 20 |
| Step | 10 |
| Sweep / Sweep seeds | 20 |
| Evasion | 20 |
| Gateway | 30 |
| Re-declaration | 5 |

No caption prints n=97.

## Manuscript

Do not paste `refused (5/10)`. Paste the split 9-row table. DNS remains CoreDNS for declared names only; undeclared CoreDNS lookup is refused under full after Valid. `gateway_403` is uri-blocker 403s, not \|S\|.
