# Task 27 — Declaration tightness sweep (Section 7.4)

Recorded 28 September 2026 on the M3 Pro. Independent of APISIX/SPIRE JWT work. Uses existing `full` mode. Weights unchanged (records 3, docs 3, search 2, notify 2, others 1). `docs` is the injected drift target and is undeclared in every variant.

## Variants

| variant | k | declared | expected \(R_w\) |
| --- | ---: | --- | ---: |
| k1 | 1 | records | 3 |
| k3 | 3 | records, search, notify | 7 |
| k5 | 5 | records, search, notify, billing, analytics | 9 |
| k7 | 7 | records, search, notify, billing, analytics, audit, catalog | 11 |

Step plans name only declared tools. \(B = \{\mathrm{docs}\}\). Placeholder nginx listens on pod port 80 while Services are 8085–8088; CNP `toPorts` lists both so Cilium after DNAT still allows the declared placeholders.

Run ids: `long-multistep-k{1,3,5,7}-full-seed{1–5}` (20 cluster runs). `make paper-tables TABLE=sweep`. Default `make analyse` ignores these rows.

## Cluster results

`source=cluster` on every seed. Provenance: verify-span count in `[29, 30]` with non-zero duration variance.

| k | n | \|R\| (every seed) | \(R_w\) (every seed) | \|B ∩ R\| |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 5 | 1 | 3 | 0 |
| 3 | 5 | 3 | 7 | 0 |
| 5 | 5 | 5 | 9 | 0 |
| 7 | 5 | 7 | 11 | 0 |

Acceptance holds: `|R| = k`, \(R_w\) matches declared weights, `|B ∩ R| = 0`.

## Schema

Optional `spec.variant` ∈ {k1,k3,k5,k7} and `services.declared_count` ∈ {1,3,5,7}. Headline Paper 1 manifests omit them. `validate_manifest` checks `declared_count == len(declared)` and the frozen lists in `rig/sweep.py`.

## Manuscript impact

Paper 1 reach table stays 3-vs-8. Sweep numbers come only from `make paper-tables TABLE=sweep`. Do not paste these rows into headline tables.
