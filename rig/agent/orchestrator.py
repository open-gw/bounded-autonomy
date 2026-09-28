"""Deterministic 'model': pick a declared tool from the step instruction.

A hosted LLM is optional (OPENAI_API_KEY) and off by default so Paper 1
runs do not depend on a network model. See docs/NEW-MATTER.md.
"""

from __future__ import annotations

from plan import MCP_TOOLS, Step


class UndeclaredTool(ValueError):
    """Step plan names a tool that is not in the current declaration."""

    def __init__(self, tool: str, instruction: str):
        super().__init__(
            f"instruction names undeclared tool {tool!r}: {instruction!r}"
        )
        self.tool = tool
        self.instruction = instruction


def named_tool(instruction: str, candidates: list[str] | None = None) -> str | None:
    text = instruction.lower()
    for name in candidates or list(MCP_TOOLS):
        if name in text:
            return name
    return None


def pick_tool(instruction: str, declared: list[str], last_result: dict | None) -> str:
    text = instruction.lower()
    for name in declared:
        if name in text:
            return name
    named = named_tool(instruction)
    if named and named not in declared:
        raise UndeclaredTool(named, instruction)
    if last_result and last_result.get("forced_tool") in declared:
        return last_result["forced_tool"]
    raise ValueError(f"instruction does not name a declared tool: {instruction!r}")


def pick_from_injection(payload: dict, declared: list[str]) -> str:
    """What the drifted instruction asks for — may be undeclared."""
    return payload["undeclared_service"]
