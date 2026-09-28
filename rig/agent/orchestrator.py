"""Deterministic 'model': pick a declared tool from the step instruction.

A hosted LLM is optional (OPENAI_API_KEY) and off by default so Paper 1
runs do not depend on a network model. See docs/NEW-MATTER.md.
"""

from __future__ import annotations

from plan import Step


class UndeclaredTool(ValueError):
    """Named so cluster/simulator imports succeed. Paper 1 pick_tool still raises ValueError."""

    def __init__(self, tool: str, instruction: str = ""):
        self.tool = tool
        self.instruction = instruction
        super().__init__(f"undeclared tool {tool!r}: {instruction!r}")


def pick_tool(instruction: str, declared: list[str], last_result: dict | None) -> str:
    text = instruction.lower()
    for name in declared:
        if name in text:
            return name
    if last_result and last_result.get("forced_tool") in declared:
        return last_result["forced_tool"]
    raise ValueError(f"instruction does not name a declared tool: {instruction!r}")


def pick_from_injection(payload: dict, declared: list[str]) -> str:
    """What the drifted instruction asks for — may be undeclared."""
    return payload["undeclared_service"]
