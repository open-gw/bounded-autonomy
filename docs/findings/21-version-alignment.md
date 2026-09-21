# Task 21 — Align manuscript Table II with the rig

Date: 2026-09-21. Scope: row-by-row check of the eleven Table II components (Kubernetes, Cilium, SPIRE, PostgreSQL, Qdrant, MinIO, Marquez, OpenTelemetry collector, Tempo, Chaos Mesh, k3d) against `rig/versions.yaml` and the image tags actually applied by cluster YAML / Makefile / telemetry.

## Table II in this checkout

**No manuscript Table II exists in this repository.** Searched `docs/design.md`, `docs/study-design.md`, `docs/NEW-MATTER.md`, `docs/findings/`, `ARTIFACT.md`, comments, and `analysis/output/tables.tex`. There is no `.tex` manuscript (same gap as Task 19). `study-design.md` names reach / rollback / overhead tables only. `docs/design.md` maps Section VI hardware and Section VII metric tables, not a software-stack Table II.

Canonical versions below are therefore the list to paste into Table II in one edit. Nearby citations that could have been mistaken for Table II are recorded in the mismatch section.

## Paste-ready Table II (from the rig)

Use this as the manuscript row set. Versions and tags are those recorded in `rig/versions.yaml` and confirmed on the applied manifests.

| Component | Version | Image / chart as recorded |
| --- | --- | --- |
| Kubernetes | 1.32.3 | `rancher/k3s:v1.32.3-k3s1` (`cluster.k3s_image`; `kubectl` `v1.32.3`) |
| Cilium | 1.17.13 | Helm chart `1.17.13`; `quay.io/cilium/cilium:v1.17.13` (Hubble relay `quay.io/cilium/hubble-relay:v1.17.13`) |
| SPIRE | 1.15.3 | `ghcr.io/spiffe/spire-server:1.15.3`; `ghcr.io/spiffe/spire-agent:1.15.3` |
| PostgreSQL | 17.5 | `postgres:17.5` |
| Qdrant | v1.13.6 | `qdrant/qdrant:v1.13.6` |
| MinIO | RELEASE.2025-07-23T15-54-02Z | `quay.io/minio/minio:RELEASE.2025-07-23T15-54-02Z` |
| Marquez | 0.50.0 | `marquezproject/marquez:0.50.0` (web image `marquezproject/marquez-web:0.50.0`, not deployed as a separate row) |
| OpenTelemetry collector | 0.127.0 | `otel/opentelemetry-collector-contrib:0.127.0` |
| Tempo | 2.7.2 | `grafana/tempo:2.7.2` |
| Chaos Mesh | — (not deployed) | Absent from `rig/versions.yaml` and from every cluster / telemetry / lineage manifest. Not installed by `make up`. |
| k3d | v5.8.3 | CLI pin `cluster.k3d` (no image; cluster node image is the k3s row) |

Compact `component | version` for a one-cell manuscript replace:

```
Kubernetes | 1.32.3
Cilium | 1.17.13
SPIRE | 1.15.3
PostgreSQL | 17.5
Qdrant | v1.13.6
MinIO | RELEASE.2025-07-23T15-54-02Z
Marquez | 0.50.0
OpenTelemetry collector | 0.127.0
Tempo | 2.7.2
Chaos Mesh | not deployed
k3d | v5.8.3
```

LaTeX tabular (same eleven rows):

```latex
\begin{tabular}{ll}
\toprule
Component & Version \\
\midrule
Kubernetes & 1.32.3 \\
Cilium & 1.17.13 \\
SPIRE & 1.15.3 \\
PostgreSQL & 17.5 \\
Qdrant & v1.13.6 \\
MinIO & RELEASE.2025-07-23T15-54-02Z \\
Marquez & 0.50.0 \\
OpenTelemetry collector & 0.127.0 \\
Tempo & 2.7.2 \\
Chaos Mesh & not deployed \\
k3d & v5.8.3 \\
\bottomrule
\end{tabular}
```

## Where the pins live (confirmed, no float)

| Component | `rig/versions.yaml` | Applied tag |
| --- | --- | --- |
| Kubernetes | `cluster.k3s_image`, `cluster.kubectl` | `rig/cluster/k3d.yaml` `image: rancher/k3s:v1.32.3-k3s1` |
| Cilium | `cni.cilium_chart` / `cni.cilium_image` | `scripts/cluster_up.sh` `helm … --version "$CILIUM_CHART"`; comment in `rig/cluster/cilium-values.yaml` |
| SPIRE | `identity.spire` + server/agent images | `rig/identity/spire.yaml` |
| PostgreSQL | `stores.postgres` / `postgres_image` | `rig/stores/manifests.yaml` |
| Qdrant | `stores.qdrant` / `qdrant_image` | `rig/stores/manifests.yaml` |
| MinIO | `stores.minio` / `minio_image` | `rig/stores/manifests.yaml` |
| Marquez | `lineage.marquez` / `marquez_image` | `rig/lineage/marquez.yaml` |
| OpenTelemetry collector | `telemetry.otel_collector` / `otel_collector_image` | `rig/telemetry/manifests.yaml` |
| Tempo | `telemetry.tempo` / `tempo_image` | `rig/telemetry/manifests.yaml` |
| Chaos Mesh | **no key** | **no manifest** |
| k3d | `cluster.k3d` | `scripts/install_tools.py` / `scripts/lib.sh` |

Manifest tags match `versions.yaml` for every deployed component. Makefile does not override pins (`# Versions: rig/versions.yaml`).

## Previously cited versions (not a Table II)

These are the only nearby version strings that a Table II could have been drawn from. They are **not** a manuscript Table II.

| Component | Previously cited | Rig | Verdict |
| --- | --- | --- | --- |
| Kubernetes | k3s `rancher/k3s:v1.32.3-k3s1` in `docs/findings/12-reproducibility.md` | 1.32.3 / same image | match |
| Cilium | **Bibliography** `v1.19` / **1.19.8** (`docs/findings/19-references.md`, `docs/NEW-MATTER.md` Task 19). Cluster pin already recorded as 1.17.13 in findings 12 / 19 | Helm/image **1.17.13** | **mismatch** (bib vs artefact) |
| SPIRE | 1.15.3 in findings 12 | 1.15.3 | match |
| PostgreSQL | “Postgres 17” in `docs/design.md`; “Postgres 17 manifests” in findings 06 | 17.5 | major-only citation; patch is 17.5 |
| Qdrant | none with a version number | v1.13.6 | no prior citation |
| MinIO | same release tag; Task 12 moved registry `docker.io` → `quay.io` | `quay.io/minio/minio:RELEASE.2025-07-23T15-54-02Z` | tag match; registry already corrected |
| Marquez | Task 12 / NEW-MATTER: `0.50.1` was never published | **0.50.0** | **mismatch if Table II still says 0.50.1** |
| OpenTelemetry collector | none with a version number | 0.127.0 | no prior citation |
| Tempo | none with a version number | 2.7.2 | no prior citation |
| Chaos Mesh | none | absent | unused; do not invent a version |
| k3d | v5.8.3 in findings 12 | v5.8.3 | match |

## Explicit mismatches

No manuscript Table II text was found, so there is **no Table II vs rig row delta to apply inside the repo**.

Mismatches that will appear if the author’s off-repo Table II or bibliography is not updated:

1. **Cilium — bibliography 1.19.8 vs cluster 1.17.13.** Task 19 correctly pinned the *docs site* citation to Cilium 1.19.8 at `https://docs.cilium.io/en/v1.19/`. The artefact installs Helm chart `1.17.13` / `quay.io/cilium/cilium:v1.17.13`. Table II must say **1.17.13**. Leave the bibliography on 1.19.8 only if it cites the documentation series, not the cluster pin; if Table II and the bib both claim one Cilium version, they currently disagree.
2. **Marquez — 0.50.1 vs 0.50.0.** `0.50.1` was never a published Docker Hub tag. The pin and deployed image are `0.50.0`.
3. **Chaos Mesh — not a pin.** Absent from `rig/versions.yaml`. `make up` does not deploy it. Table II should read “not deployed” (or drop the row), not a guessed chart version.

Everything else in the eleven-row set either matches the existing findings citations or had no prior version string.

## Manuscript impact

Paste the compact table into Table II. Do not change `rig/versions.yaml`. Do not rewrite the Cilium *bibliography* from 1.19.8 to 1.17.13 (Task 19: the bib is the docs series; the artefact pin is a consistency check if Section VI / Table II cites the cluster).
