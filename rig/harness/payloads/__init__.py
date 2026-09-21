"""Load versioned injection payloads from this package directory."""

from __future__ import annotations

from pathlib import Path

import yaml

DIR = Path(__file__).resolve().parent


def load_payload(version: str, seed: int) -> dict:
    path = DIR / f"{version}.yaml"
    if not path.exists():
        files = sorted(DIR.glob("v*.yaml"))
        if not files:
            raise FileNotFoundError(f"no payloads in {DIR}")
        path = files[seed % len(files)]
    doc = yaml.safe_load(path.read_text())
    doc["path"] = str(path)
    return doc
