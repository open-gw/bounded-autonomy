#!/usr/bin/env python3
"""Build an anonymised tree from HEAD for double-blind ICSA artefact evaluation.

The identified GitHub/Zenodo archive keeps authors. This derived tree must
grep-clean for author names and ORCID. Does not invent DOIs.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TREE = DIST / "bounded-autonomy-anonymous"
TARBALL = DIST / "bounded-autonomy-anonymous.tar.gz"

# Concatenated so this file itself does not contain the identified strings.
_FAMILY = "Dhana" + "raj"
_GIVEN = "Ri" + "nu"
_HOST = "Ri" + "nus-MBP"
_USER = _GIVEN.lower() + _FAMILY.lower()
_ORCID = "0009-0007-9082-8846"
NEEDLES = re.compile(
    rf"{_FAMILY}|Goldgin|{_USER}|{_HOST}|{_ORCID}|orcid\.org/{_ORCID}|"
    rf"(?<![A-Za-z]){_GIVEN}(?![A-Za-z])",
    re.IGNORECASE,
)

REPLACEMENTS = (
    (f"{_GIVEN} {_FAMILY}", "Anonymous"),
    (f"{_FAMILY}, {_GIVEN} Goldgin", "Anonymous"),
    (f"{_FAMILY}, {_GIVEN}", "Anonymous"),
    (f"{_FAMILY}, R.", "Anonymous"),
    (f"{_HOST}-M3.local", "measurement-host.local"),
    (_HOST, "measurement-host"),
    (_USER, "anonymous"),
    (f"https://orcid.org/{_ORCID}", ""),
    (_ORCID, ""),
    (_FAMILY, "Anonymous"),
    ("Goldgin", "Anonymous"),
    (_GIVEN, "Anonymous"),
)


def _git_archive(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    archive = subprocess.check_output(
        ["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD"]
    )
    dest_tar = dest / "_archive.tar"
    dest_tar.write_bytes(archive)
    subprocess.check_call(["tar", "-xf", str(dest_tar), "-C", str(dest)])
    dest_tar.unlink()


def _rewrite_text(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def _rewrite_citation(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r"(?m)^(\s*(?:-\s+)?)family-names: .+$",
        r"\1family-names: Anonymous",
        text,
    )
    text = re.sub(
        r"(?m)^(\s*(?:-\s+)?)given-names: .+$",
        r"\1given-names: Reviewer",
        text,
    )
    text = re.sub(r"(?m)^(\s*)orcid: .+\n", "", text)
    path.write_text(text, encoding="utf-8")


def _rewrite_zenodo(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    creators = []
    for creator in doc.get("creators") or []:
        creators.append({"name": "Anonymous"})
    doc["creators"] = creators
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _scrub_tree(tree: Path) -> None:
    skip_suffixes = {".pdf", ".png", ".svg", ".parquet"}
    skip_rel = {
        "scripts/package_anonymous.py",
        "tests/test_anonymous.py",
    }
    for path in tree.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in skip_suffixes:
            continue
        rel = path.relative_to(tree).as_posix()
        if rel in skip_rel:
            path.unlink()
            continue
        if rel == "CITATION.cff":
            _rewrite_citation(path)
            continue
        if rel == ".zenodo.json":
            _rewrite_zenodo(path)
            continue
        try:
            sample = path.read_bytes()[:8]
        except OSError:
            continue
        if b"\0" in sample:
            continue
        try:
            _rewrite_text(path)
        except UnicodeDecodeError:
            continue


def _grep_tree(tree: Path) -> list[str]:
    hits: list[str] = []
    skip_suffixes = {".pdf", ".png", ".svg", ".parquet"}
    for path in tree.rglob("*"):
        if not path.is_file() or path.suffix.lower() in skip_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if NEEDLES.search(line):
                hits.append(f"{path.relative_to(tree)}:{i}:{line.strip()}")
    return hits


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    _git_archive(TREE)
    _scrub_tree(TREE)
    hits = _grep_tree(TREE)
    if hits:
        sys.stderr.write("anonymous artefact still contains author/ORCID needles:\n")
        sys.stderr.write("\n".join(hits) + "\n")
        return 1
    if TARBALL.exists():
        TARBALL.unlink()
    with tarfile.open(TARBALL, "w:gz") as tar:
        tar.add(TREE, arcname=TREE.name)
    print(f"wrote {TREE}")
    print(f"wrote {TARBALL}")
    print("grep: no author names or ORCID in the anonymised tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
