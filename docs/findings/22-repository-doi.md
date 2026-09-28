# Task 22 — Repository DOI

Date: 2026-09-27 (America/New_York); Zenodo timestamps 2026-09-28 UTC. Scope: citation metadata, GitHub release `v1.0.1-paper1`, Zenodo software archive.

## DOIs (from Zenodo API, not invented)

| Record | Role | DOI |
| --- | --- | --- |
| Preprint (already published) | Publication → Preprint, version v1.0 | [10.5281/zenodo.23004531](https://doi.org/10.5281/zenodo.23004531) |
| Software version | GitHub tag `v1.0.1-paper1` | [10.5281/zenodo.23004819](https://doi.org/10.5281/zenodo.23004819) |
| Software concept | All versions of this repository archive | [10.5281/zenodo.23004818](https://doi.org/10.5281/zenodo.23004818) |

Software record created `2026-09-28T01:42:29Z`, title and creators taken from `.zenodo.json` (`Dhanaraj, Rinu`, ORCID `0009-0007-9082-8846`, license MIT, `upload_type` software). Version string on Zenodo: `v1.0.1-paper1`.

## Tag and commits

| Ref | Hash | Subject |
| --- | --- | --- |
| `v1.0.1-paper1` (peel) | `531e922fa8e7c328e403e9681ef9da8db4dd1d01` | Task 22: Zenodo metadata and citation files |
| Commit 1 (archived tree) | `531e922fa8e7c328e403e9681ef9da8db4dd1d01` | same |
| `v1.0-paper1` (peel) | `77759230b49173916b299727f596093799c0a662` | not re-tagged |
| Prior local commit also on `main` | `5da02ff6bfa516885f93e232b58bb6b54e91163f` | Record Paper 2 rig and process gaps before Task 24 |

Release URL: https://github.com/open-gw/bounded-autonomy/releases/tag/v1.0.1-paper1

Commit 2 (`Task 22: repository DOI`) is the follow-up that writes these DOIs into `README.md` and `CITATION.cff`. It is **not** the tagged archive; the hook already minted `23004819` from commit 1.

## Cross-links

1. **Software → preprint (done).** Record `23004819` `related_identifiers`: DOI `10.5281/zenodo.23004531`, relation `isSupplementTo`, resource type `publication-preprint`. Applied from `.zenodo.json` when the GitHub hook ingested the release.
2. **Preprint → software (pending UI).** Record `23004531` still has no `related_identifiers`. `ZENODO_TOKEN` was unset, so the reverse link was not written via API.

Exact click for the reverse link: sign in at [zenodo.org](https://zenodo.org) as the owner of [record 23004531](https://zenodo.org/records/23004531) → **Edit** → **Related works** → add identifier `10.5281/zenodo.23004819` → scheme **DOI** → relation **Is supplemented by** (`isSupplementedBy`) → save / publish. Do not invent a third DOI.

## Hook

A GitHub webhook to `zenodo.org` was already **active** on `release` events before this task (ping `202` at `2026-09-28T00:34:53Z`). Creating `v1.0.1-paper1` delivered `release`/`released` with HTTP `202`; follow-up `created`/`published` deliveries returned `409` (already ingested). This session could not open the Zenodo GitHub settings page in the browser; the user can still confirm the flip-switch at [https://zenodo.org/account/settings/github/](https://zenodo.org/account/settings/github/) for `open-gw/bounded-autonomy`.

`v1.0-paper1` predates that hook and has no software DOI.

## Name

Task text offered `Dhanaraj, Rinu Goldgin` if that was the legal name. `LICENSE` is `Rinu Dhanaraj`; existing `CITATION.cff` given-names were `Rinu`; ORCID `0009-0007-9082-8846` public name is `Rinu` / `Dhanaraj`; the preprint creators field is `Dhanaraj, Rinu`. Creators stay `Dhanaraj, Rinu`.

## Validation

`cffconvert --validate` (schema 1.2.0) accepted `CITATION.cff` after commit 1 and again after the concept-DOI edit.
