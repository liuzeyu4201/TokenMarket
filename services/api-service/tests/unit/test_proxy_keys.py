"""SF10/SF11 proxy key issue, auth, revoke."""

from __future__ import annotations

import uuid

import pytest

from app.domain.proxykeys.service import (
    ProxyKeyError,
    ProxyKeyService,
    hash_proxy_secret,
)


def test_issue_auth_revoke() -> None:
    svc = ProxyKeyService(b"p" * 32)
    buyer = uuid.uuid4()
    issued = svc.issue(buyer_id=buyer)
    assert issued.secret_once is not None
    assert issued.secret_once.startswith("tmk-")
    assert len(issued.secret_once) >= 4 + 32
    secret = issued.secret_once
    assert svc.authenticate(secret) is not None
    assert svc.authenticate("wrong") is None
    svc.revoke(issued.key_id, buyer)
    assert svc.authenticate(secret) is None


def test_revoke_other_buyer_hidden() -> None:
    svc = ProxyKeyService(b"p" * 32)
    a = uuid.uuid4()
    b = uuid.uuid4()
    issued = svc.issue(buyer_id=a)
    with pytest.raises(ProxyKeyError):
        svc.revoke(issued.key_id, b)


def test_hash_not_invertible() -> None:
    h = hash_proxy_secret("tmk-0123456789abcdef0123456789abcdef", b"p" * 32)
    assert "tmk-" not in h
    assert "0123456789abcdef" not in h
