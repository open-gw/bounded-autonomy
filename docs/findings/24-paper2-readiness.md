# Paper 2 readiness — rig and process gaps

Recorded 27 September 2026. Planning only. **G1–G9 are not implemented in this commit. No campaign is started. Paper 1 `runs/results/` and `analysis/` tables are unchanged.**

This file is the start-here for Paper 2 after Paper 1 integrity, arXiv, and the ICSA CFP checklist (`docs/findings/23-venue.md`; do not invent CFP dates here). Work begins at **G2** (critical path).

## Hard gates

- **G1 is Task 24 (Apache APISIX).** G2–G9 remain the gate for later Paper 2 campaign tasks. Speccing those against the Paper 1 one-profile / two-mode / one-agent tree would freeze the wrong contract.
- **Freeze study-design at `paper2-prereg`.** `docs/study-design.md` remains the Paper 1 contract. Paper 2 gets its own analysis notebook and a tagged freeze (`paper2-prereg`) *before* the first campaign run (P3, P4). Any later change is an amendment with a reason, not a silent edit.
- **Citation.** Paper 2 cites the Paper 1 preprint DOI [10.5281/zenodo.23004531](https://doi.org/10.5281/zenodo.23004531) until proceedings exist. Do not invent a proceedings citation. Repository DOI (Task 22) is a related identifier, not a substitute for the preprint.

## Designed study (not yet runnable)

Four profiles × three modes × 30 seeded repeats (360 task-level runs), plus the step-granularity variant. Intended results: a predictive test of the reachable-set metric, per-class rollback under varied write mixes, verification overhead by chain depth, and fair baselines (including gateway-only). The tree today covers Paper 1’s single profile (`long-multistep`), two modes (`flat`, `full`), five seeds, one agent, one injection payload.

Paper 1 figures stay out of Paper 2 (P6).

## Rig gaps (must build)

| # | Gap | Why Paper 2 needs it | Size | Status |
| --- | --- | --- | --- | --- |
| G1 | **Gateway-only mode.** Paper 2’s second baseline is “gateway policy on, no segmentation, no service-side checks.” | Without it the study compares only `flat` vs `full` and cannot say what the gateway alone buys. | Medium: Apache APISIX + `uri-blocker` allow-list; agent through APISIX in `gateway-only` and `full`. | Built in Task 24. See [`24-apisix.md`](24-apisix.md). Not Kong. |
| G2 | **Delegation chain profile.** The rig has one agent and no sub-agents. `chain_depth` 2–5 requires sub-agent processes, per-hop token exchange, and a provenance record that services verify. | Verification overhead by chain depth is a headline result; the predictive test also needs multi-hop breach paths. | Large: sub-agent runtime, exchange service (RFC 8693 shape) on SPIRE, provenance record format, hop signing. | Not built. **Critical path — start here.** |
| G3 | **Plane 3 verification implemented in full.** The current `verify` span covers audience check and task-scoped filtering only (`rig/tools/dispatch.py`). Provenance chain check and monotonic-narrowing check do not exist in code. | Paper 2 measures the cost of the four checks per hop; two of the four are not built. This is also the reduction to practice for claims 11–13. | Medium, depends on G2 for the chain to verify. | Not built. Blocked on G2. |
| G4 | **Data-intensive profile.** Qdrant writes exist, but the profile needs all three stores in one task with a 20/30/40/10 mix and derived-write volume high enough to stress quarantine. | Rollback completeness by write mix is a headline result. | Small: step-plan generator for the profile; Qdrant snapshot cadence. | Not built. |
| G5 | **Short-single profile.** Trivial step plan, but segment provisioning dominates such tasks; the profile exists to show the fixed cost. | Practitioner guidance on which workloads justify full controls. | Small. | Not built. |
| G6 | **Model-driven agent.** Paper 1’s agent is a deterministic planner (`rig/agent/orchestrator.py`). Paper 2’s predictive test needs an agent that can actually be redirected by content, or the “adaptive injection” claim is hollow. | The reachable-set-predicts-breach test requires breach sets that vary with the injected content. | Medium: local model via Ollama on the M3 Pro (deterministic seed, fixed temperature), with the step plan as a constraint and the model choosing among declared tools. Record model name and hash in `rig/versions.yaml`. | Not built. |
| G7 | **Injection variants.** One payload today (`rig/harness/payloads/`). The predictive test needs several payload variants per seed targeting different undeclared services and stores. | Correlation between \(R_w\) and observed breach requires variance in breach. | Small: `harness/payloads/` with 5–8 variants, selected by seed. | Not built. |
| G8 | **Probe cost separated from control cost.** Paper 1 could not separate the per-step probe from re-derivation cost. | Paper 2 must report re-derivation cost net of measurement. | Small: run step-granularity with probe on and probe off; report the difference. | Not built. |
| G9 | **Lineage emission timing.** Not instrumented in Paper 1. | Overhead breakdown per invocation. | Small: a span around the OpenLineage emit call. | Not built. |
| G10 | **Sensitivity weights from data classification.** Weights are hand-assigned in the rig manifest (`rig/services.yaml`). | Fine for Paper 2 if stated; note it as a limitation rather than build a classifier. | None; document. | Document-only. No build. |

G10 is a limitation note, not a build. G1–G9 are the build gate for Task 24+.

## Process gaps (must decide or set up)

| # | Gap | Resolution |
| --- | --- | --- |
| P1 | **Run budget.** 360 task-level runs at roughly 1.2–5 s each plus step-granularity runs at ~20 s each plus provisioning per run: on the M3 Pro, about 8–12 hours unattended. The Lima VM is slower. | Add `make campaign PROFILE=all MODES=all SEEDS=1-30` with resume-on-failure and per-run provenance guard. Run overnight in batches; never mix hosts within a profile. Do not start that campaign from this document. |
| P2 | **Artefact archival.** `runs/results/*.parquet` is gitignored. Paper 2’s reviewers will want the raw flows, spans and lineage, not just `result.json`. | Zenodo dataset record per campaign (Parquet tarball, checksummed), cited from the paper. Fits the repository-DOI pattern from Task 22. After the first campaign, not before. |
| P3 | **Pre-registration.** The Paper 1 design document exists, but the analysis notebook for Paper 2 (paired Wilcoxon, Cliff’s delta, Spearman with bootstrap CI) is not written. | Task 02 pattern again: write and commit the Paper 2 notebook against the result schema *before* the first campaign run. Tag the commit `paper2-prereg`. |
| P4 | **Metric definitions frozen.** ICSA reviewers may ask for changes to Paper 1’s metric definitions. If those change, Paper 2 must not silently inherit the change. | Freeze `docs/study-design.md` at the `paper2-prereg` tag; any change after that is recorded as an amendment with a reason. Paper 1 tables in `analysis/` stay on the Paper 1 contract. |
| P5 | **Citation of Paper 1.** Paper 2 cites the Zenodo preprint DOI **10.5281/zenodo.23004531** now; if ICSA accepts, the citation updates to the proceedings. | No blocker. Do not invent a proceedings citation. |
| P6 | **Journal extension rule.** TDSC and Computers & Security require substantial new content over the conference version. | Paper 2’s scope (four profiles, three modes, statistics, predictive test, chain depth) clears it; keep Paper 1’s figures out of Paper 2. |
| P7 | **Calendar.** Both non-provisional deadlines fall in August–September 2027 (AGA: 19 August 2027; this family: 27 September 2027; see `docs/legal/DEADLINES.md`), and the AGA and BA non-provisionals will each take several weeks. | Paper 2’s campaign and writing should be complete by June 2027 so the patent work does not collide with it. Work backwards from that date (calendar below). Venue CFP dates live in `docs/findings/23-venue.md` — not here. |
| P8 | **Clean-room continuity.** G1 introduces a gateway product into the personal rig. | Use a gateway you have not touched at work, configured from public docs only; record the choice in findings. **Envoy Gateway or APISIX rather than Kong.** |

## Dependency graph

```
G1 gateway ──┐
G2 chain ────┼── G3 Plane 3 full ── chain-depth results
G6 model ────┼── G7 payloads ────── predictive test
G4, G5 profiles ─────────────────── profile campaign
G8, G9 instrumentation ──────────── overhead breakdown
P3 prereg notebook ── before any campaign run
P1 campaign target ── before any campaign run
P2 archival ────────── after first campaign
```

**G2 is the critical path:** it is the largest build and three results depend on it (G3 / chain-depth overhead, multi-hop breach paths for the predictive test, and the Plane 3 reduction to practice). Start G2 first. G1 and G6 can proceed in parallel with G2; G3 cannot. G7 waits on G6. The campaign waits on G1–G9 plus P3 and P1.

## Calendar (backwards from patent collision, not from a CFP)

Do not treat these as ICSA dates. CFP deadlines, page limits, and review model are the user’s checklist in `docs/findings/23-venue.md`.

| Window | Work |
| --- | --- |
| Through December 2026 | Build G1–G9. G2 first. G10 is a manuscript limitation, not a build. |
| January–February 2027 | Campaign (`make campaign` from P1). Hosts not mixed within a profile. P3/`paper2-prereg` already tagged. |
| March–May 2027 | Analysis and writing. P2 archival of Parquet after the first campaign. |
| June 2027 | Submit Paper 2. Leaves August–September 2027 for the two non-provisionals. |

## Drop-if-short

If time is short, these are the only planned cuts. Do not invent others after the campaign starts.

- **Drop G2/G3 chain-depth results** and state chain depth as future work. The paper loses one headline but keeps the predictive test, the profile comparison, and the gateway baseline. Not recommended; it is the only cut that removes weeks rather than days.
- **Reduce repeats from 30 to 20 per cell.** Keeps the statistics valid; cuts the campaign by about a third.

Do not drop G1 (gateway baseline) or G6/G7 (predictive test) if the paper is still called a three-mode, predictive study.

## Clean-room (G1)

G1 adds a gateway to the personal rig. Configure it from public documentation only, on a product not used at work.

- Allowed: **Envoy Gateway** or **Apache APISIX**.
- Not allowed: **Kong** (or any other gateway already touched in an employment context).

Record the chosen product, chart/image pins, and the public-docs trail in a later findings file when G1 is built. This commit does not deploy either.

## Paper 1 deferrals not on the G1–G9 list

Existing Paper 1 notes (`docs/design.md`, `ARTIFACT.md`, findings 04 / 15 / 16) still name Cilium mutual authentication, multi-node, and a hosted LLM backend as Paper 2 surfaces. They are **not** G1–G9:

- Cilium `authentication.mode: required` is a datapath claim, not the gateway baseline (G1) and not Plane 3 (G3). Decide during G1–G9 whether it is in-scope for `full` or stays future work; do not silently add it to Task 24.
- Multi-node is not required for the designed 360-run campaign.
- Hosted LLM is not G6. G6 is a local Ollama model with a recorded hash. A network backend remains optional and off the critical path (same posture as Paper 1 NEW-MATTER for Task 10).

## G2 start-here

Paper 1 has one agent process (`rig/agent/orchestrator.py`) that picks a declared tool from a seeded instruction; standalone SPIRE (`rig/identity/spire.yaml`, trust domain `rig`) issues one `spiffe://rig/task/<task-id>` SVID per task; `verify` in `rig/tools/dispatch.py` is audience plus destination filter only. G2 adds sub-agent processes at `chain_depth` 2–5, an RFC 8693-shaped token exchange on that SPIRE, and a hop-signed provenance record that services will check in G3. Start by specifying the exchange API, the provenance record schema, and how a parent SVID is narrowed into a child without widening the declared set — then implement the sub-agent runtime and hop signing. Do not implement G3, do not start the campaign, and do not spec Task 24 until that chain exists.

## What this document does not do

- Does not implement G1–G9 or G10’s classifier.
- Does not add `make campaign` or run any Paper 2 cells.
- Does not edit `runs/results/`, `analysis/metrics.py`, `analysis/tables.py`, or Paper 1 notebook outputs.
- Does not invent ICSA CFP dates or a proceedings citation.
- Does not ratify `docs/study-design.md` as the Paper 2 pre-registration; that freeze is the `paper2-prereg` tag (P3/P4), which does not exist yet.
