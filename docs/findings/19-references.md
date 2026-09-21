# Task 19 — Reference verification

Date: 2026-09-21. Scope: the thirteen `\bibitem` keys the author pasted (the manuscript `.tex` is still not in this checkout). Each row was checked against a fetched canonical record (NIST CSRC/Crossref, OWASP PDF, MCP spec pages, ACM/Crossref, Cilium HTML titles, SPIFFE spec, RFC Editor JSON, USENIX HTML, OpenLineage spec YAML, IEEE Crossref). None is marked from memory.

## Result

**11 verified, 2 corrected, 0 unverified.**

Corrections (one line each):

- `mcpspec` — cited `https://modelcontextprotocol.io/specification` no longer is rev. 2025-06-18; that URL now serves rev. 2026-07-28. Pin `https://modelcontextprotocol.io/specification/2025-06-18` (the dated revision still exists).
- `cilium` — cited `https://docs.cilium.io` is *Cilium 1.20.2 documentation* today, not v1.19. The 1.19 series is *Cilium 1.19.8 documentation* at `https://docs.cilium.io/en/v1.19/`.

## Per-reference table

| # | Key | Kind | Status | Fetched | Authors / title / venue / year | Living-doc revision or access date | Corrected `\bibitem` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `nist800207` | NIST | **verified** | [CSRC SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final); Crossref [10.6028/NIST.SP.800-207](https://doi.org/10.6028/NIST.SP.800-207) | S. Rose, O. Borchert, S. Mitchell (Stu), S. Connelly (Sean), *Zero Trust Architecture*, NIST SP 800-207, Aug. 2020 (CSRC final 2020-08-11) | n/a | — |
| 2 | `owaspllm` | living | **verified** | [project page](https://owasp.org/www-project-top-10-for-large-language-model-applications/); [2025 PDF](https://owasp.github.io/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf) (cover: Version 2025, November 18, 2024); [genai resource](https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/) (dated November 17, 2024) | OWASP, *OWASP Top 10 for LLM Applications 2025* | Revision **Version 2025**, dated **18 Nov. 2024** on the PDF (user’s “Nov. 2024” matches). Latest HTML list: [genai.owasp.org/llm-top-10](https://genai.owasp.org/llm-top-10/) | — |
| 3 | `mcpspec` | living | **corrected** | [rev. 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18) (exists; stateful); unversioned [`/specification`](https://modelcontextprotocol.io/specification) matches [rev. 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) (stateless; changelog “since … 2025-11-25”); [llms.txt](https://modelcontextprotocol.io/llms.txt) lists 2026-07-28 first | Model Context Protocol, *Specification* | User’s **2025-06-18** is a real dated revision. Current default at the cited URL is **2026-07-28**. | Pin the dated URL (see block). |
| 4 | `greshake2023` | ACM | **verified** | Crossref [10.1145/3605764.3623985](https://doi.org/10.1145/3605764.3623985); ACM DL title/venue from the same DOI | K. Greshake, S. Abdelnabi, S. Mishra, C. Endres, T. Holz, M. Fritz, *Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*, Proc. 16th ACM Workshop on Artificial Intelligence and Security (AISec ’23), pp. 79–90, 2023 (published 2023-11-26) | n/a | — |
| 5 | `cilium` | living | **corrected** | HTML `<title>` on 2026-09-21: [stable](https://docs.cilium.io/en/stable/) = “Cilium **1.20.2** documentation”; [v1.19](https://docs.cilium.io/en/v1.19/) = “Cilium **1.19.8** documentation” | Cilium documentation | Access date **21 Sep. 2026** confirmed by fetch. Cited “v1.19” + unversioned `docs.cilium.io` disagree. | Pin `/en/v1.19/` and 1.19.8 (see block). |
| 6 | `spiffe` | living | **verified** | [SPIFFE Concepts](https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/); [standards/SPIFFE.md](https://raw.githubusercontent.com/spiffe/spiffe/main/standards/SPIFFE.md) (“Stability: Stable”); [STABILITY.md](https://raw.githubusercontent.com/spiffe/spiffe/main/standards/STABILITY.md) | SPIFFE specifications (concepts page + Stable spec set) | No dated revision number. Access date **21 Sep. 2026** confirmed. Stability banner: **Stable**. | — |
| 7 | `rfc8693` | RFC | **verified** | RFC Editor [rfc8693.json](https://www.rfc-editor.org/rfc/rfc8693.json); [rfc8693](https://www.rfc-editor.org/rfc/rfc8693) | M. Jones, A. Nadalin, B. Campbell (Ed.), J. Bradley, C. Mortimore, *OAuth 2.0 Token Exchange*, RFC 8693, Jan. 2020. DOI 10.17487/RFC8693 | n/a | — |
| 8 | `pass2006` | USENIX | **verified** | [USENIX ATC 2006 HTML paper](https://www.usenix.org/legacy/event/usenix06/tech/full_papers/muniswamy-reddy/muniswamy-reddy_html/); USENIX conference-page BibTeX from the same day’s search fetch of [the ATC 06 paper page](https://www.usenix.org/conference/2006-usenix-annual-technical-conference/provenance-aware-storage-systems) | K.-K. Muniswamy-Reddy, D. A. Holland, U. Braun, M. Seltzer, *Provenance-Aware Storage Systems*, 2006 USENIX Annual Technical Conference (USENIX ATC 06), May 2006 | n/a | — |
| 9 | `openlineage` | living | **verified** | [docs landing](https://openlineage.io/docs); [object model](https://openlineage.io/docs/spec/object-model); spec YAML [OpenLineage.yml](https://raw.githubusercontent.com/OpenLineage/OpenLineage/main/spec/OpenLineage.yml) `info.version: 2.0.2` | OpenLineage specification (OpenAPI 3.0.2) | Access date **21 Sep. 2026** confirmed. Spec file version **2.0.2** (no year-version on the docs page). | — |
| 10 | `retro2010` | USENIX | **verified** | USENIX conference-page BibTeX from the search fetch of [the OSDI 10 paper page](https://www.usenix.org/conference/osdi10/intrusion-recovery-using-selective-re-execution); [MIT CSAIL PDF](https://pdos.csail.mit.edu/papers/retro:osdi10.pdf); [DSpace](https://dspace.mit.edu/handle/1721.1/61699?show=full) (pp. 89–104) | T. Kim, X. Wang, N. Zeldovich, M. F. Kaashoek, *Intrusion Recovery Using Selective Re-execution*, 9th USENIX Symposium on Operating Systems Design and Implementation (OSDI 10), Oct. 2010 | n/a | — |
| 11 | `warp2011` | ACM | **verified** | Crossref [10.1145/2043556.2043567](https://doi.org/10.1145/2043556.2043567); ACM DL / SIGOPS PDF first page | R. Chandra, T. Kim, M. Shah, N. Narula, N. Zeldovich, *Intrusion recovery for database-backed web applications*, Proc. 23rd ACM Symposium on Operating Systems Principles (SOSP ’11), pp. 101–114, Oct. 2011 | n/a | — |
| 12 | `hardy1988` | ACM | **verified** | Crossref [10.1145/54289.871709](https://doi.org/10.1145/54289.871709) (DOI `10.1145/581327.581330` 404s) | Norm Hardy, *The Confused Deputy* (subtitle: *or why capabilities might have been invented*), ACM SIGOPS Operating Systems Review, vol. 22, no. 4, pp. 36–38, Oct. 1988 | n/a | — |
| 13 | `saltzer1975` | IEEE | **verified** | Crossref [10.1109/PROC.1975.9939](https://doi.org/10.1109/PROC.1975.9939) (IEEE Xplore HTML challenged JS; Crossref is the IEEE deposit). Primary resource: `ieeexplore.ieee.org/document/1451869` | J. H. Saltzer and M. D. Schroeder, *The protection of information in computer systems*, Proc. IEEE, vol. 63, no. 9, pp. 1278–1308, 1975 | n/a | — |

## Notes that are not status changes

- IEEE `et al.` on six-author / five-author papers is style, not an error. Full names above are from the fetched records.
- Hardy’s Crossref given name is **Norm** (user’s `N. Hardy` is the IEEE initial form). Subtitle omitted in the paste is optional.
- This artefact pins Cilium **1.17.13** in `rig/versions.yaml`. That is not a reason to rewrite the bibliography from the docs site; it is a manuscript/artefact consistency check if Section VI cites the cluster pin.

## Manuscript file

No `\bibitem` in a paper file was edited. There is still no manuscript `.tex` in this repository. Paste the block below into the draft.

## Corrected `thebibliography` (two keys changed)

`mcpspec` and `cilium` differ from the paste. Other keys keep the pasted facts; DOIs and full titles below are from the same fetches.

```latex
\begin{thebibliography}{13}

\bibitem{nist800207}
S.~Rose, O.~Borchert, S.~Mitchell, and S.~Connelly, ``Zero Trust Architecture,''
NIST Special Publication 800-207, Aug. 2020. [Online]. Available:
https://doi.org/10.6028/NIST.SP.800-207

\bibitem{owaspllm}
OWASP, ``OWASP Top 10 for LLM Applications 2025,'' Version 2025, Nov. 2024.
[Online]. Available:
https://owasp.org/www-project-top-10-for-large-language-model-applications/

\bibitem{mcpspec}
Model Context Protocol, ``Specification,'' rev. 2025-06-18. [Online]. Available:
https://modelcontextprotocol.io/specification/2025-06-18

\bibitem{greshake2023}
K.~Greshake \textit{et al.}, ``Not What You've Signed Up For: Compromising
Real-World LLM-Integrated Applications with Indirect Prompt Injection,'' in
\textit{Proc. 16th ACM Workshop on Artificial Intelligence and Security}
(AISec~'23), 2023, pp. 79--90. [Online]. Available:
https://doi.org/10.1145/3605764.3623985

\bibitem{cilium}
Cilium Authors, ``Cilium Documentation,'' v1.19.8, 2026, accessed Sep.~21, 2026.
[Online]. Available: https://docs.cilium.io/en/v1.19/

\bibitem{spiffe}
SPIFFE, ``SPIFFE Specifications,'' 2026, accessed Sep.~21, 2026. [Online].
Available: https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/

\bibitem{rfc8693}
M.~Jones, A.~Nadalin, B.~Campbell, J.~Bradley, and C.~Mortimore, ``OAuth 2.0
Token Exchange,'' RFC 8693, Jan. 2020. [Online]. Available:
https://www.rfc-editor.org/rfc/rfc8693

\bibitem{pass2006}
K.-K.~Muniswamy-Reddy, D.~A.~Holland, U.~Braun, and M.~Seltzer,
``Provenance-Aware Storage Systems,'' in \textit{2006 USENIX Annual Technical
Conference} (USENIX ATC~06), May 2006. [Online]. Available:
https://www.usenix.org/conference/2006-usenix-annual-technical-conference/provenance-aware-storage-systems

\bibitem{openlineage}
OpenLineage, ``OpenLineage Specification,'' spec v2.0.2, 2026, accessed
Sep.~21, 2026. [Online]. Available: https://openlineage.io/docs

\bibitem{retro2010}
T.~Kim, X.~Wang, N.~Zeldovich, and M.~F.~Kaashoek, ``Intrusion Recovery Using
Selective Re-execution,'' in \textit{9th USENIX Symp. Operating Systems Design
and Implementation} (OSDI~10), Oct. 2010. [Online]. Available:
https://www.usenix.org/conference/osdi10/intrusion-recovery-using-selective-re-execution

\bibitem{warp2011}
R.~Chandra, T.~Kim, M.~Shah, N.~Narula, and N.~Zeldovich, ``Intrusion recovery
for database-backed web applications,'' in \textit{Proc. 23rd ACM Symp.
Operating Systems Principles} (SOSP~'11), 2011, pp. 101--114. [Online].
Available: https://doi.org/10.1145/2043556.2043567

\bibitem{hardy1988}
N.~Hardy, ``The Confused Deputy (or why capabilities might have been
invented),'' \textit{ACM SIGOPS Oper. Syst. Rev.}, vol.~22, no.~4, pp. 36--38,
Oct. 1988. [Online]. Available: https://doi.org/10.1145/54289.871709

\bibitem{saltzer1975}
J.~H.~Saltzer and M.~D.~Schroeder, ``The protection of information in computer
systems,'' \textit{Proc. IEEE}, vol.~63, no.~9, pp. 1278--1308, 1975.
[Online]. Available: https://doi.org/10.1109/PROC.1975.9939

\end{thebibliography}
```

If the draft should cite the *current* MCP spec at the unversioned URL instead of pinning 2025-06-18, replace the `mcpspec` body with rev. 2026-07-28 and `https://modelcontextprotocol.io/specification/2026-07-28`.
