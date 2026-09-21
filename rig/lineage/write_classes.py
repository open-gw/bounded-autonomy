"""Map (store, operation) → write class. Never taken from a client header."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PATH = Path(__file__).resolve().parent / "write_classes.yaml"


@lru_cache(maxsize=1)
def table() -> dict[str, dict[str, str]]:
    return yaml.safe_load(PATH.read_text())


def write_class(store: str, operation: str) -> str:
    try:
        return table()[store][operation]
    except KeyError as exc:
        raise KeyError(f"no write class for ({store}, {operation})") from exc
