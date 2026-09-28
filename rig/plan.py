"""Seeded write-class plan. Mix is a property of the seed, not the model."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Mapping, Sequence

WRITE_CLASSES = ("idempotent", "versioned", "derived", "irreversible")
DEFAULT_DECLARED = ["records", "search", "notify"]
MCP_TOOLS = ("records", "docs", "search", "notify")
THREE_STORE_DECLARED = ["records", "docs", "search", "notify"]

# Split postgres/minio so a three-store profile actually touches MinIO.
# Index into each class's slot list (not the global step index).
THREE_STORE_CLASS_TOOLS = {
    "idempotent": (("records", "upsert"), ("docs", "put_overwrite")),
    "versioned": (("records", "insert"), ("docs", "put")),
    "derived": (("search", "upsert"),),
    "irreversible": (("notify", "append"),),
}

CLASS_TO_TOOL = {
    "idempotent": ("records", "upsert"),
    "versioned": ("records", "insert"),
    "derived": ("search", "upsert"),
    "irreversible": ("notify", "append"),
}

# Fallback operation when the class-preferred tool is not declared.
CLASS_OPS = {
    "records": {
        "idempotent": "upsert",
        "versioned": "insert",
        "derived": "upsert",
        "irreversible": "insert",
    },
    "docs": {
        "idempotent": "put_overwrite",
        "versioned": "put",
        "derived": "put",
        "irreversible": "put",
    },
    "search": {
        "idempotent": "upsert",
        "versioned": "upsert",
        "derived": "upsert",
        "irreversible": "upsert",
    },
    "notify": {
        "idempotent": "append",
        "versioned": "append",
        "derived": "append",
        "irreversible": "append",
    },
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


def tool_for_class(write_class: str, declared: Sequence[str]) -> tuple[str, str]:
    """Map a write class to a declared MCP tool. Preferred tool wins."""
    preferred_tool, preferred_op = CLASS_TO_TOOL[write_class]
    if preferred_tool in declared:
        return preferred_tool, preferred_op
    for name in declared:
        ops = CLASS_OPS.get(name)
        if ops is not None:
            return name, ops[write_class]
    raise ValueError(
        f"no declared MCP tool for write class {write_class!r} in {list(declared)}"
    )


def _three_store_tool(write_class: str, class_slot: int) -> tuple[str, str]:
    options = THREE_STORE_CLASS_TOOLS[write_class]
    return options[class_slot % len(options)]


def build_step_plan(
    seed: int,
    steps: int = 30,
    write_mix: Mapping[str, float] | None = None,
    declared: Sequence[str] | None = None,
    three_store: bool = False,
) -> list[Step]:
    mix = write_mix or {
        "idempotent": 0.4,
        "versioned": 0.3,
        "derived": 0.2,
        "irreversible": 0.1,
    }
    allow = list(declared) if declared is not None else list(DEFAULT_DECLARED)
    counts = counts_from_mix(mix, steps)
    slots: list[str] = []
    for cls in WRITE_CLASSES:
        slots.extend([cls] * counts[cls])
    rng = random.Random(seed)
    rng.shuffle(slots)
    class_seen = {cls: 0 for cls in WRITE_CLASSES}
    plan: list[Step] = []
    for i, cls in enumerate(slots, start=1):
        if three_store:
            tool, operation = _three_store_tool(cls, class_seen[cls])
            class_seen[cls] += 1
            if tool not in allow:
                tool, operation = tool_for_class(cls, allow)
        else:
            tool, operation = tool_for_class(cls, allow)
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
