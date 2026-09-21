"""Seeded 30-step write-class plan. Mix is a property of the seed, not the model."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Mapping, Sequence

WRITE_CLASSES = ("idempotent", "versioned", "derived", "irreversible")

CLASS_TO_TOOL = {
    "idempotent": ("records", "upsert"),
    "versioned": ("records", "insert"),
    "derived": ("search", "upsert"),
    "irreversible": ("notify", "append"),
}


@dataclass(frozen=True)
class Step:
    index: int  # 1-based
    write_class: str
    tool: str
    operation: str
    instruction: str


def counts_from_mix(write_mix: Mapping[str, float], steps: int) -> dict[str, int]:
    raw = {c: write_mix[c] * steps for c in WRITE_CLASSES}
    rounded = {c: int(v) for c, v in raw.items()}
    # Largest-remainder so we always emit exactly `steps` slots.
    remainders = sorted(
        ((raw[c] - rounded[c], c) for c in WRITE_CLASSES), reverse=True
    )
    missing = steps - sum(rounded.values())
    for i in range(missing):
        rounded[remainders[i][1]] += 1
    return rounded


def build_step_plan(
    seed: int,
    steps: int = 30,
    write_mix: Mapping[str, float] | None = None,
) -> list[Step]:
    mix = write_mix or {
        "idempotent": 0.4,
        "versioned": 0.3,
        "derived": 0.2,
        "irreversible": 0.1,
    }
    counts = counts_from_mix(mix, steps)
    slots: list[str] = []
    for cls in WRITE_CLASSES:
        slots.extend([cls] * counts[cls])
    rng = random.Random(seed)
    rng.shuffle(slots)
    plan: list[Step] = []
    for i, cls in enumerate(slots, start=1):
        tool, operation = CLASS_TO_TOOL[cls]
        instruction = (
            f"Step {i}: using the {tool} tool, perform {operation} "
            f"({cls} write) on the declared store."
        )
        plan.append(
            Step(
                index=i,
                write_class=cls,
                tool=tool,
                operation=operation,
                instruction=instruction,
            )
        )
    return plan


def declared_from_plan(plan: Sequence[Step]) -> list[str]:
    names = []
    for step in plan:
        if step.tool not in names:
            names.append(step.tool)
    return names
