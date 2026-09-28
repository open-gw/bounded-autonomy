"""JWT-SVID TTL helpers. τ = exp − iat, not issue-to-delete.

Public SPIRE docs (1.15): registration-entry ``-jwtSVIDTTL`` is the JWT-SVID
lifetime; ``spire-server jwt mint`` / Workload API ``FetchJWTSVID`` emit a JWT
whose ``exp`` and ``iat`` claims are that TTL. ``spire-server entry delete``
removes the registration entry (data-management). It is not SVID revocation.
"""

from __future__ import annotations

import base64
import json
from typing import Any

# Server ``default_x509_svid_ttl`` is 1h. Task identity is a JWT-SVID; X.509
# stays at this pod-level default and is never used as τ.
POD_X509_SVID_TTL_SECONDS = 3600
DEFAULT_TASK_JWT_TTL_SECONDS = 1800
DEFAULT_STEP_JWT_TTL_SECONDS = 60
JWT_AUDIENCE = "rig"
POD_SPIFFE_ID = "spiffe://rig/workload/agent"


def jwt_ttl_seconds(spec: dict[str, Any], *, granularity: str | None = None) -> int:
    gran = granularity or spec.get("granularity") or "task"
    if gran == "step":
        step = (
            spec.get("expectedStepDurationSeconds")
            or spec.get("expected_step_duration_seconds")
        )
        if step:
            return int(step)
        return DEFAULT_STEP_JWT_TTL_SECONDS
    return int(
        spec.get("expectedDurationSeconds")
        or spec.get("expected_duration_seconds")
        or DEFAULT_TASK_JWT_TTL_SECONDS
    )


def decode_jwt_claims(token: str) -> dict[str, Any]:
    payload = token.strip().split(".")[1]
    pad = "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload + pad))


def tau_from_claims(claims: dict[str, Any]) -> dict[str, float]:
    """τ is SVID TTL: exp − iat. Never issue-to-delete."""
    iat = float(claims["iat"])
    exp = float(claims["exp"])
    return {
        "iat": iat,
        "exp": exp,
        "tau_seconds": exp - iat,
    }


def residual_seconds(*, exp: float, task_end: float, policy_removed_at: float | None) -> dict[str, float | None]:
    """Residual window after the task ends.

    (a) exp − task_end: JWT-SVID still valid after the run.
    (b) policy_removed_at − task_end: CNP/segment collapse (historically ~363 ms).
    """
    return {
        "residual_svid_seconds": float(exp) - float(task_end),
        "residual_policy_seconds": (
            None if policy_removed_at is None else float(policy_removed_at) - float(task_end)
        ),
    }


def extract_jwt_token(text: str) -> str:
    """Pull a compact JWS out of ``spire-server jwt mint`` / agent fetch output."""
    for raw in text.splitlines():
        line = raw.strip()
        if line.count(".") >= 2 and not line.startswith("token("):
            return line
        if line.startswith("token(") and ")" in line:
            inner = line[line.find("(") + 1 : line.rfind(")")]
            if inner.count(".") >= 2:
                return inner
    compact = text.strip()
    if compact.count(".") >= 2:
        return compact.split()[-1]
    raise ValueError(f"no JWT in SPIRE output: {text[:200]!r}")


def parse_entry_ids(show_text: str) -> list[str]:
    ids: list[str] = []
    for raw in show_text.splitlines():
        line = raw.strip()
        if line.lower().startswith("entry id"):
            _, value = line.split(":", 1)
            value = value.strip()
            if value:
                ids.append(value)
    return ids
