"""Idempotency keys are scoped to the acting principal."""

from __future__ import annotations

import uuid

import pytest

from app.domain.proxykeys.service import MemoryProxyStore, ProxyKeyError, ProxyKeyService
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.memory_store import MemoryKeyStore
from app.domain.sellerkeys.service import OnboardingService
from app.domain.sellerkeys.validator_port import ValidationSnapshot


class _OK:
    def validate(self, *, platform: str, api_key: str, request_id: str) -> ValidationSnapshot:
        return ValidationSnapshot(
            "success", remaining_quota="10", quota_unit="token", validity="valid"
        )


def test_two_buyers_same_idempotency_key_are_isolated() -> None:
    store = MemoryProxyStore()
    svc = ProxyKeyService(b"p" * 32, store=store)
    a = uuid.uuid4()
    b = uuid.uuid4()
    first = svc.issue(buyer_id=a, idempotency_key="shared-key")
    second = svc.issue(buyer_id=b, idempotency_key="shared-key")
    assert first.key_id != second.key_id
    assert second.replayed is False
    replay_a = svc.issue(buyer_id=a, idempotency_key="shared-key")
    assert replay_a.key_id == first.key_id
    assert replay_a.replayed is True


def test_preclaim_different_payload_does_not_deny_other_actor() -> None:
    store = MemoryProxyStore()
    svc = ProxyKeyService(b"p" * 32, store=store)
    a = uuid.uuid4()
    b = uuid.uuid4()
    store.put_idempotency("preclaim", a, "digest-other-payload", None)
    with pytest.raises(ProxyKeyError) as own:
        svc.issue(buyer_id=a, name="changed", idempotency_key="preclaim")
    assert own.value.http_status in (409, 503)
    other = svc.issue(buyer_id=b, name="changed", idempotency_key="preclaim")
    assert other.replayed is False
    assert other.key_id is not None


def test_two_sellers_same_idempotency_key_are_isolated() -> None:
    store = MemoryKeyStore()
    svc = OnboardingService(
        validator=_OK(),
        encryptor=CredentialEncryptor(b"k" * 32, "v1"),
        store=store,
        fingerprint_secret=b"s" * 32,
    )
    a = uuid.uuid4()
    b = uuid.uuid4()
    first = svc.onboard(
        seller_id=a,
        role="seller",
        platform="volcano",
        api_key="sk-synthetic-test-key-not-real-a",
        idempotency_key="shared-seller",
        request_id="r1",
    )
    second = svc.onboard(
        seller_id=b,
        role="seller",
        platform="volcano",
        api_key="sk-synthetic-test-key-not-real-b",
        idempotency_key="shared-seller",
        request_id="r2",
    )
    assert first.key_id != second.key_id
    assert second.replayed is False
