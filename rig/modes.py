"""Run-mode helpers. Paper 1 uses flat/full; Paper 2 adds gateway modes.

`gateway-bypass` is a mode of its own and is also combinable with `full`
via the `gateway_bypass` flag (agent calls ClusterIP while the gateway
allow-list is still applied from the TaskDeclaration).
"""

from __future__ import annotations

PAPER1_MODES = ("flat", "full")
ALL_MODES = ("flat", "full", "gateway-only", "gateway-bypass")
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
DECLARED_DEFAULT = ("records", "search", "notify")
GATEWAY_PLUGIN = "uri-blocker"
GATEWAY_HOST = "apisix-gateway.apisix.svc.cluster.local"
GATEWAY_PORT = 9080
GATEWAY_ADMIN_HOST = "apisix-admin.apisix.svc.cluster.local"
GATEWAY_ADMIN_PORT = 9180
GATEWAY_NS = "apisix"
GATEWAY_LABEL = "apisix"


def normalize_mode(mode: str) -> str:
    return (mode or "").strip()


def gateway_bypass_enabled(mode: str, gateway_bypass: bool = False) -> bool:
    return bool(gateway_bypass) or normalize_mode(mode) == "gateway-bypass"


def uses_segment(mode: str, gateway_bypass: bool = False) -> bool:
    """CNP / SVID path. Independent of whether the agent uses the gateway."""
    del gateway_bypass
    return normalize_mode(mode) == "full"


def uses_gateway_path(mode: str, gateway_bypass: bool = False) -> bool:
    """Agent HTTP client talks to APISIX rather than service ClusterIP."""
    if gateway_bypass_enabled(mode, gateway_bypass):
        return False
    return normalize_mode(mode) in ("gateway-only", "full")


def deploys_gateway_policy(mode: str, gateway_bypass: bool = False) -> bool:
    """TaskDeclaration is applied so the allow-list is generated."""
    name = normalize_mode(mode)
    return name in ("gateway-only", "gateway-bypass", "full") or bool(gateway_bypass)


def uses_flat_credential(mode: str) -> bool:
    return normalize_mode(mode) != "full"


def run_id_for(
    *,
    profile: str,
    mode: str,
    seed: int,
    granularity: str = "task",
    gateway_bypass: bool = False,
    probe: bool = True,
    step_split: bool = False,
) -> str:
    if step_split and granularity == "step":
        tag = "step-split" if probe else "step-noprobe"
        return f"{profile}-{mode}-{tag}-seed{seed}"
    if granularity == "step":
        if not probe:
            return f"{profile}-{mode}-step-noprobe-seed{seed}"
        return f"{profile}-{mode}-step-seed{seed}"
    if gateway_bypass and mode == "full":
        return f"{profile}-full-bypass-seed{seed}"
    return f"{profile}-{mode}-seed{seed}"
