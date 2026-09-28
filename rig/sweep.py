"""Declaration-tightness variants for the Section 7.4 k/|S| sweep.

Weights stay frozen in ``rig/services.yaml`` (records 3, docs 3, search 2,
notify 2, others 1). ``docs`` is never declared so the injected drift target
is the same undeclared service in every variant.
"""

from __future__ import annotations

from typing import Iterable

from weights import reachable_weight

INVENTORY = (
    "records",
    "docs",
    "search",
    "notify",
    "billing",
    "analytics",
    "audit",
    "catalog",
)

VARIANTS: dict[str, list[str]] = {
    "k1": ["records"],
    "k3": ["records", "search", "notify"],
    "k5": ["records", "search", "notify", "billing", "analytics"],
    "k7": ["records", "search", "notify", "billing", "analytics", "audit", "catalog"],
}

INJECTION_SERVICE = "docs"
INJECTION_STORE = "minio"
SWEEP_VARIANTS = tuple(VARIANTS.keys())


def undeclared(variant: str) -> list[str]:
    declared = set(declared_services(variant))
    return [name for name in INVENTORY if name not in declared]


def declared_services(variant: str) -> list[str]:
    try:
        return list(VARIANTS[variant])
    except KeyError as exc:
        raise ValueError(f"unknown sweep variant {variant!r}") from exc


def declared_count(variant: str) -> int:
    return len(declared_services(variant))


def declared_weight(variant: str, weights: dict[str, int] | None = None) -> int:
    return reachable_weight(declared_services(variant), weights)


def variant_of_declared(services: Iterable[str]) -> str | None:
    names = list(services)
    for key, expected in VARIANTS.items():
        if names == expected:
            return key
    return None
