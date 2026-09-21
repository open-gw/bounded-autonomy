# Task 19 — Reference verification

Date: 2026-09-21. Scope: the thirteen `\bibitem` entries of the ICSA manuscript *Containing and Unwinding the Blast Radius of Agentic Workflows*, including five living documents that need a revision or access date.

## Result

**0 verified, 0 corrected, 13 unverified.** No bibliography was edited. None of the thirteen keys were identified, so none were fetched from a DOI, ACM DL, arXiv, RFC, or project doc.

Acceptance required every row verified against a canonical source, with no entry left on memory. That bar is not met. Inventing `\bibitem` text from the artefact stack (Cilium, SPIFFE, MCP, OpenLineage, …) and marking it verified would be memory, which this task forbids.

## Why the rows are empty

This repository is the Paper 1 **artefact**. It has `docs/design.md`, `docs/study-design.md`, `analysis/output/tables.tex` (generated tabulars, gitignored), and no manuscript `.tex` / `.bbl` / `.bib`. `rg '\\bibitem'` over the checkout is empty. Task 14 already recorded that the original design document is not on this machine either.

The author fills `\val{}` slots in a draft kept outside this tree (chat of 2026-09-21). That draft was not in `docs/`, not on a git branch, and not in `open-gw/` siblings.

## Search (2026-09-21)

| Location | What was looked for | Hit |
| --- | --- | --- |
| This repo (`*.tex`, `*.bbl`, `*.bib`, `docs/**`) | `\bibitem`, `thebibliography` | none (only generated `analysis/output/tables.tex`, no bibliography) |
| Git history / branches of `bounded-autonomy` | added `.tex` / `.bbl` / paper files | none; `main` only |
| `github.com/open-gw/*` | other repos holding the manuscript | artefact repo only for this title |
| `open-gw/` siblings (`ctier`, `ctier-engine`, `gateway-db-mcp`) | `\bibitem` | none |
| `~/m3pro/workspace`, `~/m3pro/private`, `~/m3pro/proposals` | title / `\bibitem` / `long-multistep` | README + `docs/design.md` only |
| `~/Documents`, `~/Desktop` | `*.tex`, `*.bbl`, `*icsa*`, `*blast*radius*` | none |
| `~/Downloads` and `~/Downloads/EB1A` (docx/pdf/zip, title needles) | `Containing and Unwinding`, `long-multistep`, `\bibitem` | other papers (AGA, GatewayDB-MCP, JSS, IEEE Access, INTCEC); **not** this manuscript |
| Web search for the paper title | public HTML/PDF | no matching ICSA source (private until arXiv posting, per README) |

No Overleaf/Google-Drive copy was opened from this session. If the draft lives there, it still is not in the artefact tree this task can patch.

## Per-reference table

Keys are unknown. Rows exist so the count stays thirteen; status is **unverified**, not **verified**.

| # | `\bibitem` key | Kind | Status | Canonical URL fetched | Authors / title / venue / year | Living-doc revision or access date | Corrected `\bibitem` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 2 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 3 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 4 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 5 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 6 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 7 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 8 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 9 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 10 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 11 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 12 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |
| 13 | — | unknown | **unverified** | not fetched (key missing) | — | — | — |

Five of these are living documents. Which five is unknown until the `.tex` is present.

## Manuscript file

No `\bibitem` in the paper file was changed. There is no paper file in this repository.

## When the `.tex` arrives

Same procedure Task 14 recorded for the missing pre-registration:

1. Place the manuscript (or its `.bbl`) in the tree, typically `docs/` or `paper/`.
2. Extract the thirteen `\bibitem` keys and bodies.
3. For each, fetch the canonical record (Crossref/DOI, ACM DL, arXiv abs, RFC Editor, or the project’s current docs page). Confirm authors, title, venue, year.
4. For each of the five living documents, record revision or access date from that fetch, not from memory.
5. Mark the row **verified** or **corrected**; if corrected, put the replacement `\bibitem` in this file **and** in the manuscript.
6. If a URL cannot be fetched, leave the row **unverified** and say so.

## Manuscript impact

None until the bibliography is in tree. Do not paste a reconstructed reference list into the draft from this findings file.
