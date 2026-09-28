# Zenodo upload checklist (Paper 1 preprint)

Recorded 27 September 2026. No DOI is minted here: there is no `ZENODO_TOKEN` in the environment, no `zenodo` CLI, and this agent cannot complete the authenticated UI publish.

**Source PDF (do not invent):**
`/Users/rinudhanaraj/Downloads/EB1A/Bounded Autonomy/USPTO Bounded Autonomy/bounded-autonomy-icsa-preview.pdf`

**ORCID (from sibling `CITATION.cff` and the PDF title page):** `https://orcid.org/0009-0007-9082-8846`

## Deposit

1. Sign in at [zenodo.org](https://zenodo.org) (Chrome already had `https://zenodo.org/me/uploads` open on 27 September 2026).
2. New upload. Resource type: **Publication → Preprint**.
3. Upload `bounded-autonomy-icsa-preview.pdf`.
4. Title: *Bounded Autonomy: Containing and Unwinding the Blast Radius of Agentic Workflows*.
5. Creators: Rinu Dhanaraj, ORCID `0009-0007-9082-8846`.
6. License: **CC BY 4.0**.
7. Publication date: 2026-09-27 (or the PDF date 2026-09-21 if you want the manuscript date).
8. Related identifier: `https://github.com/open-gw/bounded-autonomy`, relation **is supplemented by** (or the closest Zenodo relation if that label is not offered).
9. Abstract — verbatim from the PDF (hyphenation joined):

Autonomous agents that invoke tools and access data on behalf of users introduce a class of failure that existing access control does not address: an authenticated, in-policy agent that drifts from its delegated task or is redirected by the content it reads. Current controls decide whether a call may start. They do not bound how far a compromised or drifting agent can reach, nor do they record what it accessed in a form that supports reversal. This paper presents a reference architecture for the execution plane of agentic systems, comprising three components: per-task network segmentation derived from the tool set an agent declares before execution, enforcement and observation of the resulting reachable set, and task-keyed lineage that tags every read and write with the identity of the delegating task across heterogeneous stores. We define four measurable properties of such a system: reachable-set size weighted by data sensitivity, the ratio of credential lifetime to task duration, rollback completeness reported by write class, and verification overhead per delegation hop. We describe a proof-of-concept implementation on Kubernetes using Cilium, SPIRE and OpenLineage, and evaluate it on a long-running multi-step workload under injected drift, reporting each property with and without the controls. The architecture is independent of any particular agent framework or gateway, and the metrics are intended to serve as a common basis for comparing containment approaches.

10. Publish. Note the **version DOI** (`10.5281/zenodo.…`). Put it in `README.md` and `CITATION.cff`. Do not invent a DOI.

## GitHub webhook (repository DOI)

1. Repository must be **public**: `gh repo edit open-gw/bounded-autonomy --visibility public` (org must allow it).
2. In Zenodo: [GitHub settings](https://zenodo.org/account/settings/github/) → enable `open-gw/bounded-autonomy`. This usually requires a click in the Zenodo UI.
3. Cut GitHub release `v1.0-paper1` pointing at this Paper 1 artefact. The webhook then mints a software/repository DOI (often `10.5281/zenodo.XXXX`).
4. Record that repository DOI separately from the preprint DOI.

Status 27 September 2026:

- GitHub repository is **public**: https://github.com/open-gw/bounded-autonomy
- Release **`v1.0-paper1`**: https://github.com/open-gw/bounded-autonomy/releases/tag/v1.0-paper1
- No `ZENODO_TOKEN` / `zenodo` CLI. Zenodo `/account/settings/github/` required a fresh login from this machine. Enable `open-gw/bounded-autonomy` there (UI click), then the webhook can mint a repository DOI. Do not invent a DOI.
- Preprint deposit (Publication → Preprint, steps 1–10 above) is still unpublished.
