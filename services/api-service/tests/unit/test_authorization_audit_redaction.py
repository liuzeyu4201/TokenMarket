"""Audit payload must not embed secrets."""

from __future__ import annotations

import uuid

from app.domain.authorization.audit import build_event_payload
from app.domain.authorization.codes import ReasonCode
from app.domain.authorization.matrix import Action


def test_payload_has_no_key_fields() -> None:
    payload = build_event_payload(
        action=Action.seller_key_read,
        reason=ReasonCode.ROLE_DENIED,
        allowed=False,
        is_state_change=False,
        actor_user_id=uuid.uuid4(),
        session_id=None,
        resource_type="seller_key",
        resource_id=uuid.uuid4(),
        request_id="rid",
        safe_metadata={"excluded_count": 1},
    )
    blob = str(payload).lower()
    assert "api_key" not in blob
    assert "password" not in blob
    assert payload["policy_version"] == "authz-matrix-v1"
    assert "phone" not in payload["safe_metadata"]
