"""τ = exp − iat. Residual is post-task, not revocation."""

from __future__ import annotations

import pytest

from identity.svid import (
    POD_X509_SVID_TTL_SECONDS,
    extract_jwt_token,
    jwt_ttl_seconds,
    parse_entry_ids,
    residual_seconds,
    tau_from_claims,
)


def test_tau_is_exp_minus_iat_not_issue_to_delete():
    claims = {"iat": 1_000.0, "exp": 2_800.0}
    got = tau_from_claims(claims)
    assert got["tau_seconds"] == 1800.0
    # issue-to-delete of a 12 s task would have been 12
    assert got["tau_seconds"] != 12.0


def test_jwt_ttl_task_vs_step():
    spec = {"expectedDurationSeconds": 1800, "granularity": "task"}
    assert jwt_ttl_seconds(spec) == 1800
    spec["granularity"] = "step"
    spec["expectedStepDurationSeconds"] = 60
    assert jwt_ttl_seconds(spec) == 60
    assert POD_X509_SVID_TTL_SECONDS == 3600


def test_residual_two_windows():
    got = residual_seconds(exp=2800.0, task_end=1012.0, policy_removed_at=1012.363)
    assert got["residual_svid_seconds"] == 1788.0
    assert got["residual_policy_seconds"] == pytest.approx(0.363)


def test_extract_jwt_and_entry_id():
    token = "aaa.bbb.ccc"
    assert extract_jwt_token(f"JWT written to stdout\n{token}\n") == token
    shown = "Found 1 entry\nEntry ID         : 92f4518e-61c9-420d-b984-074afa7c7002\n"
    assert parse_entry_ids(shown) == ["92f4518e-61c9-420d-b984-074afa7c7002"]
