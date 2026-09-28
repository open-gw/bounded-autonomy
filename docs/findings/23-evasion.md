# Task 23 — Evasion matrix (review C1)

## Built

- `rig/observer/evasion.py` probes from the agent pod (task-id identity) and writes `evasion.parquet`. `result.json` gains optional `evasion_matrix` (7 rows × verdict + latency). `make validate MANIFEST=…/result.json` checks the new fields.
- `make paper-tables TABLE=evasion` emits the 7-row flat vs full table. Provenance guard (source, span-count symmetry, zero-variance) still applies; only results that carry `evasion_matrix` are gated.
- Cluster driver runs the matrix after the reachable-set probe and **before** segment delete, so full-mode CNP is still in force.

## Policy changes (record every one)

1. **Task egress CNP (`render_cnp`)** — `enableDefaultDeny.egress: true` made explicit. L4 allow-list unchanged: declared tool pods, otel-collector:4318, CoreDNS:53.
2. **DNS restore of Cilium DNS-proxy `rules.dns`** — Task 16 dropped `matchName` because the proxy blackholed lookups. Task 23 puts it back: port 53 protocol ANY to kube-dns with `matchName` for declared services plus `otel-collector` (short name and `*.rig.svc.cluster.local` search-path variants). No `matchPattern: "*"`. Undeclared inventory names, `kubernetes.default.svc`, and the public Internet are not listed.
3. **Idle `default-deny` on the agent (`rig/cluster/namespace.yaml`)** — removed the unrestricted UDP/TCP 53 allow to kube-dns. Idle policy is now `enableDefaultDeny.egress: true` with an empty egress list. DNS allow-list exists only on the task CNP. `make run` still `delete cnp --all` first, so this object is gone during a run; the change closes the hole if both policies were ever selected together (Cilium ORs allows).
4. **`egressDeny` toEntities `world`, `host`, `remote-node`, `kube-apiserver`** on the task egress CNP. Default-deny alone left node kubelet :10250 and `kubernetes` ClusterIP reachable (Cilium reserved identities). Recorded after the isolated-pod smoke.
5. **No CIDR allow-list** for service pod IPs. Row 1 stays allowed because `toEndpoints` matches the declared pod identity, not the Service name — direct pod IP is the intended semantics.
6. Isolated attach (`scripts/attach_evasion.py`) deletes leftover CNPs before each probe so concurrent campaigns’ ingress default-deny does not contaminate flat rows 1–2.

## Documented public IPs

| Use | Address | Why |
| --- | --- | --- |
| External DNS UDP/53 and TCP/443 | `1.1.1.1` (Cloudflare) | Stable anycast; not a secret; same IP for both probes so the paper can name one address |
| Node metadata | `169.254.169.254:80` | Cloud IMDS link-local. k3d has no IMDS |

## Verdict rules

`allowed` | `refused` | `error` | `host-refused`.

- TCP connect success → allowed.
- `ECONNREFUSED` / `ENETUNREACH` / `EHOSTUNREACH` → host-refused.
- Timeout: full → refused (CNP drop). Flat rows 4–5 → host-refused (no policy; no IMDS / no route).
- Row 3 verdict is the CoreDNS undeclared lookup (acceptance signal). Raw UDP/53 to `1.1.1.1` is recorded in `detail`.
- Row 6 verdict is TCP to the API name or ClusterIP (DNS of `kubernetes.default.svc` is recorded in detail).

## Acceptance (every seed)

Live `source=cluster` attach, 2026-09-28, isolated probe pods (`scripts/attach_evasion.py`). `make paper-tables TABLE=evasion`: source=cluster (n=10).

| Row | Probe | full | flat |
| ---: | --- | --- | --- |
| 1 | direct-IP declared pod | allowed (5/5) | allowed (5/5) |
| 2 | direct-IP undeclared pod | refused (5/5) | allowed (5/5) |
| 3 | DNS undeclared + UDP/53 `1.1.1.1` | refused (5/5) | allowed (5/5) |
| 4 | TCP/443 `1.1.1.1` | refused (5/5) | allowed (5/5) |
| 5 | `169.254.169.254:80` | refused (5/5) | host-refused (5/5) |
| 6 | `kubernetes.default.svc:443` + ClusterIP | refused (5/5) | allowed (5/5) |
| 7 | node IP :10250 | refused (5/5) | allowed (5/5) |

Paper 1 `|S|` / rollback / overhead numbers in these ten `result.json` files were not rewritten; only `evasion_matrix` and `artefacts.evasion` were added.

## Manuscript impact

State: **DNS is restricted to CoreDNS for declared names only.** Do not claim namespace-wide default-deny. Do not claim k3d has an IMDS. Direct-IP to a declared service pod is allowed (identity match). Do not write `\\val{}` except from `make analyse` / `make paper-tables`.

## Deviations

- `evasion_matrix` and `artefacts.evasion` are optional on the result schema so the five `full-step` Paper 1 files and simulator fixtures stay valid without a re-run.
- Task 16’s L4-only DNS note is superseded for the task CNP. If the DNS-proxy blackholes declared names again, that is recorded here and the 10-run campaign must not proceed until declared FQDNs resolve.
