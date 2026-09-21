# CNP / cluster driver (after Task 15)

## Built

- `cluster_driver.py` probes live ClusterIPs from the `agent` pod, then rewrites `probe.parquet` / `flows.parquet` / `svid.parquet` and `result.json` with `source: cluster`. Spans, lineage, ground truth, rollback stay in-process.
- CNP `toPorts` use numeric Service ports (`8081`/`8083`/`8084`). Named port `http` did not match the kube-proxy-replacement datapath; the first full smoke was `reachable=0`.
- Per-service ingress CNPs select `records`/`search`/`notify` and allow only `bounded-autonomy.io/task-id`. `enableDefaultDeny.ingress` is set on those objects. Namespace `default-deny` selects only the agent pod so tool servers still reach Postgres/MinIO/Qdrant.
- Cilium DNS-proxy `rules.dns` on port 53 blackholed name lookups; DNS allow is UDP+TCP 53 without the proxy hitch. The reachable-set probe uses ClusterIP, not DNS.

## Live ingress check (full CNPs from seed 5, 2026-09-21)

| Path | Result |
| --- | --- |
| `docs → records:8081` | denied |
| `agent → records:8081` | allowed |
| `records → postgres:5432` | allowed |

Ingress to declared services is enforced. A namespace-wide default-deny is not.

## Smoke then ten runs

Smoke: `full` `source=cluster` `|S|=3`; `flat` `source=cluster` `|S|=8`; six artefacts present.

Ten `make run` seeds 1–5 both modes: same `|S|` and `source=cluster` on every file.

## Manuscript impact

Do not claim namespace-wide default-deny. Claim: agent egress allow-list plus ingress to declared services only from the task-id label. Datapath mTLS remains Paper 2.
