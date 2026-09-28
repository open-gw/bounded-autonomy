"""Task 24: APISIX routes, uri-blocker allow-list, and gateway modes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from controller.cnp import render_cnp
from controller.declaration import declared_names, undeclared_names
from controller.gateway import render_allowlist_plugin, render_gateway_routes, render_route
from harness.simulator import run_local
from modes import (
    GATEWAY_PLUGIN,
    deploys_gateway_policy,
    run_id_for,
    uses_flat_credential,
    uses_gateway_path,
    uses_segment,
)

ROOT = Path(__file__).resolve().parents[1]


def _spec() -> dict:
    return {
        "taskId": "t-gw",
        "expectedDurationSeconds": 60,
        "services": [{"name": "records"}, {"name": "search"}, {"name": "notify"}],
    }


def test_declared_names_are_the_single_source():
    spec = _spec()
    assert declared_names(spec) == ["records", "search", "notify"]
    assert undeclared_names(spec) == ["docs", "billing", "analytics", "audit", "catalog"]
    cnp = render_cnp("decl-gw", "rig", spec)
    dests = []
    for rule in cnp["egress"]["spec"]["egress"]:
        for ep in rule.get("toEndpoints") or []:
            name = (ep.get("matchLabels") or {}).get("app.kubernetes.io/name")
            if name in {"records", "search", "notify", "docs"}:
                dests.append(name)
    assert dests == ["records", "search", "notify"]
    plugin = render_allowlist_plugin(spec)
    assert plugin["plugin"] == GATEWAY_PLUGIN == "uri-blocker"
    assert plugin["declared"] == declared_names(spec)
    assert plugin["undeclared"] == undeclared_names(spec)


def test_eight_routes_uri_blocker_on_undeclared_only():
    routes = render_gateway_routes(_spec())
    assert [r["id"] for r in routes] == [
        "ba-records",
        "ba-docs",
        "ba-search",
        "ba-notify",
        "ba-billing",
        "ba-analytics",
        "ba-audit",
        "ba-catalog",
    ]
    by_name = {r["name"].removeprefix("ba-"): r for r in routes}
    for name in ("records", "search", "notify"):
        assert GATEWAY_PLUGIN not in by_name[name]["plugins"]
        assert "proxy-rewrite" in by_name[name]["plugins"]
    blocked = by_name["docs"]
    assert blocked["plugins"][GATEWAY_PLUGIN] == {
        "block_rules": [".*"],
        "rejected_code": 403,
        "rejected_msg": "undeclared service docs",
    }


def test_render_route_rewrites_to_tools_call():
    route = render_route("docs", allowed=True)
    assert route["uri"] == "/docs/*"
    assert route["plugins"]["proxy-rewrite"]["regex_uri"] == ["^/docs/(.*)", "/$1"]
    assert "docs.rig.svc.cluster.local:8082" in route["upstream"]["nodes"]


def test_mode_helpers():
    assert uses_gateway_path("gateway-only") is True
    assert uses_gateway_path("gateway-bypass") is False
    assert uses_gateway_path("full", True) is False
    assert uses_gateway_path("full") is True
    assert uses_segment("full") is True
    assert uses_segment("full", True) is True
    assert uses_segment("gateway-only") is False
    assert deploys_gateway_policy("gateway-only") is True
    assert deploys_gateway_policy("full", True) is True
    assert deploys_gateway_policy("flat") is False
    assert uses_flat_credential("gateway-only") is True
    assert uses_flat_credential("full") is False
    assert run_id_for(profile="long-multistep", mode="full", seed=1, gateway_bypass=True) == (
        "long-multistep-full-bypass-seed1"
    )


def test_versions_pin_apisix_not_kong():
    pins = yaml.safe_load((ROOT / "rig" / "versions.yaml").read_text())
    gw = pins["gateway"]
    assert gw["product"] == "apache-apisix"
    assert gw["apisix"] == "3.18.0"
    assert gw["plugin"] == "uri-blocker"
    assert "kong" not in yaml.dump(gw).lower()


def test_simulator_gateway_only_403(tmp_path: Path):
    result = run_local(mode="gateway-only", seed=1, out_dir=tmp_path / "go", injection=True)
    assert result["metrics"]["reachable_set_size"] == 8
    gw = pd.read_parquet(tmp_path / "go" / "gateway.parquet")
    docs = gw[gw["service"] == "docs"]
    assert not docs.empty
    assert int(docs["status"].iloc[0]) == 403
    assert result["artefacts"].get("gateway") == "gateway.parquet"
    assert int(result["metrics"].get("gateway_403") or 0) >= 1


def test_simulator_gateway_bypass_breach(tmp_path: Path):
    result = run_local(mode="gateway-bypass", seed=1, out_dir=tmp_path / "gb", injection=True)
    assert result["metrics"]["reachable_set_size"] == 8
    assert result["metrics"]["breach_intersection_size"] == 1
    assert "docs" in result["metrics"]["breach_intersection"]
    gw = pd.read_parquet(tmp_path / "gb" / "gateway.parquet")
    assert gw.empty or (gw["service"] != "docs").all() or (gw["status"] != 403).all()


def test_simulator_full_bypass_refused_at_segment(tmp_path: Path):
    result = run_local(
        mode="full",
        seed=1,
        out_dir=tmp_path / "fb",
        injection=True,
        gateway_bypass=True,
    )
    assert result["metrics"]["reachable_set_size"] == 3
    assert result["metrics"]["breach_intersection_size"] == 0
    gw = pd.read_parquet(tmp_path / "fb" / "gateway.parquet")
    docs = gw[gw["service"] == "docs"] if not gw.empty else gw
    assert docs.empty
