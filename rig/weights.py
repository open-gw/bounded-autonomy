"""Service sensitivity weights. Frozen before Task 17 runs (study-design §3.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
SERVICES_PATH = ROOT / "rig" / "services.yaml"

# Task 17 freeze: records 3, docs 3, search 2, notify 2, others 1.
WEIGHTS = {
    "records": 3,
    "docs": 3,
    "search": 2,
    "notify": 2,
    "billing": 1,
    "analytics": 1,
    "audit": 1,
    "catalog": 1,
}


def load_weights() -> dict[str, int]:
    doc = yaml.safe_load(SERVICES_PATH.read_text())
    return {s["name"]: int(s["sensitivity"]) for s in doc["services"]}


def reachable_weight(services: Iterable[str], weights: dict[str, int] | None = None) -> int:
    w = weights or load_weights()
    return int(sum(w[s] for s in services))
