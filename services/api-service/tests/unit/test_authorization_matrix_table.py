"""Table-driven matrix tests for authz-matrix-v1."""

from __future__ import annotations

import pytest

from app.domain.authorization.matrix import (
    POLICY_VERSION,
    Action,
    all_actions,
    all_roles,
    is_action_allowed,
)

# Expected allow set mirrors contracts/authorization-matrix.md
_EXPECTED: dict[str, set[Action]] = {
    "buyer": {
        Action.proxy_key_create,
        Action.proxy_key_revoke,
        Action.proxy_key_use,
        Action.route_candidate_exclude_self,
        Action.project_create,
        Action.project_read,
        Action.project_update,
        Action.project_archive,
        Action.project_delete,
        Action.project_enable_protocol,
        Action.binding_create,
        Action.binding_read,
        Action.binding_publish,
        Action.binding_deactivate,
    },
    "seller": {
        Action.seller_key_register,
        Action.seller_key_read,
        Action.seller_key_update,
        Action.seller_key_disable,
        Action.connection_create,
        Action.connection_read,
        Action.connection_update,
        Action.connection_delete,
    },
    "both": set(all_actions()),
}


def test_policy_version() -> None:
    assert POLICY_VERSION == "authz-matrix-v1"


@pytest.mark.parametrize("role", all_roles())
@pytest.mark.parametrize("action", all_actions())
def test_matrix_cell(role: str, action: Action) -> None:
    expected = action in _EXPECTED[role]
    assert is_action_allowed(role, action) is expected
    assert is_action_allowed(role, action.value) is expected


def test_unknown_role_denied() -> None:
    assert is_action_allowed("admin", Action.proxy_key_use) is False
