"""Single source for the declared-service list.

The segment controller (CNP) and the APISIX allow-list plugin both call
`declared_names` so they cannot drift.
"""

from __future__ import annotations

from typing import Any, Iterable

from modes import INVENTORY


def declared_names(spec: dict[str, Any]) -> list[str]:
    services: Iterable[dict[str, str] | str] = spec.get("services") or []
    names: list[str] = []
    for item in services:
        name = item["name"] if isinstance(item, dict) else str(item)
        if name and name not in names:
            names.append(name)
    return names


def undeclared_names(spec: dict[str, Any], inventory: Iterable[str] = INVENTORY) -> list[str]:
    declared = set(declared_names(spec))
    return [name for name in inventory if name not in declared]
