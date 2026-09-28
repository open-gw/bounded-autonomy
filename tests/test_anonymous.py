"""Task 30: anonymised-mirror needles without writing dist/."""

from __future__ import annotations

from package_anonymous import NEEDLES, REPLACEMENTS, _rewrite_text
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_needles_match_identified_files():
    license_text = (ROOT / "LICENSE").read_text()
    assert NEEDLES.search(license_text)
    citation = (ROOT / "CITATION.cff").read_text()
    assert NEEDLES.search(citation)
    zenodo = (ROOT / ".zenodo.json").read_text()
    assert NEEDLES.search(zenodo)


def test_replacements_clear_license_copyright(tmp_path: Path):
    path = tmp_path / "LICENSE"
    path.write_text((ROOT / "LICENSE").read_text())
    _rewrite_text(path)
    text = path.read_text()
    assert NEEDLES.search(text) is None
    assert "Anonymous" in text
    for old, _new in REPLACEMENTS:
        if old in ("Dhanaraj", "Goldgin", "Rinu Dhanaraj", "Dhanaraj, Rinu"):
            assert old not in text
