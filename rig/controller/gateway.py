"""Render APISIX routes + uri-blocker allow-list from a TaskDeclaration.

Public docs:
  https://apisix.apache.org/docs/apisix/plugins/uri-blocker/
  https://apisix.apache.org/docs/apisix/plugins/proxy-rewrite/
  https://apisix.apache.org/docs/apisix/admin-api/

The plugin config is generated from `declared_names(spec)` — the same
helper the CNP renderer uses.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from controller.cnp import SERVICE_PORTS
from controller.declaration import declared_names, undeclared_names
from modes import GATEWAY_PLUGIN, INVENTORY

ADMIN_KEY_DEFAULT = "ba-rig-admin-key"
UPSTREAM_NS = "rig"


def _upstream_host(service: str) -> str:
    return f"{service}.{UPSTREAM_NS}.svc.cluster.local"


def render_route(service: str, *, allowed: bool) -> dict[str, Any]:
    port = SERVICE_PORTS[service]
    plugins: dict[str, Any] = {
        "proxy-rewrite": {
            "regex_uri": [f"^/{service}/(.*)", "/$1"],
        }
    }
    if not allowed:
        plugins[GATEWAY_PLUGIN] = {
            "block_rules": [".*"],
            "rejected_code": 403,
            "rejected_msg": f"undeclared service {service}",
        }
    return {
        "id": f"ba-{service}",
        "uri": f"/{service}/*",
        "name": f"ba-{service}",
        "plugins": plugins,
        "upstream": {
            "type": "roundrobin",
            "scheme": "http",
            "nodes": {f"{_upstream_host(service)}:{port}": 1},
        },
    }


def render_gateway_routes(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Eight routes. uri-blocker attached iff the service is undeclared."""
    allowed = set(declared_names(spec))
    return [render_route(name, allowed=name in allowed) for name in INVENTORY]


def render_allowlist_plugin(spec: dict[str, Any]) -> dict[str, Any]:
    """Exact plugin payload recorded in findings (uri-blocker)."""
    return {
        "plugin": GATEWAY_PLUGIN,
        "block_rules": [f"^/{name}(/|$)" for name in undeclared_names(spec)],
        "rejected_code": 403,
        "undeclared": undeclared_names(spec),
        "declared": declared_names(spec),
    }


def admin_url() -> str:
    return os.environ.get(
        "BA_APISIX_ADMIN",
        "http://apisix-admin.apisix.svc.cluster.local:9180",
    )


def admin_key() -> str:
    return os.environ.get("BA_APISIX_ADMIN_KEY", ADMIN_KEY_DEFAULT)


def _request(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, str]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-API-KEY": admin_key(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def apply_gateway_routes(spec: dict[str, Any], *, base: str | None = None) -> list[dict[str, Any]]:
    """PUT the eight routes to the APISIX Admin API."""
    root = (base or admin_url()).rstrip("/")
    applied: list[dict[str, Any]] = []
    for route in render_gateway_routes(spec):
        route_id = route["id"]
        payload = {k: v for k, v in route.items() if k != "id"}
        status, text = _request("PUT", f"{root}/apisix/admin/routes/{route_id}", payload)
        if status not in (200, 201):
            raise RuntimeError(f"APISIX route {route_id} PUT failed: {status} {text}")
        applied.append(route)
    return applied
