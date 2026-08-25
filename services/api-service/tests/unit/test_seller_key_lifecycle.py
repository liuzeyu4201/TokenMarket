"""SF09 administrative vs health states."""

from __future__ import annotations

import os
import uuid

import pytest

from app.domain.sellerkeys.codes import (
    CODE_CONFLICT,
    CODE_VALIDATION_FAILED,
    OnboardingError,
)
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.lifecycle import LifecycleService, routable, transition
from app.domain.sellerkeys.memory_store import MemoryKeyStore
from app.domain.sellerkeys.service import OnboardingService
from app.domain.sellerkeys.validator_port import ValidationSnapshot


def test_pause_resume_revoke() -> None:
    assert transition("active", "paused") == "paused"
    assert transition("paused", "active") == "active"
    assert transition("active", "revoked") == "revoked"
    assert transition("paused", "revoked") == "revoked"
    assert transition("revoked", "revoked") == "revoked"


def test_revoked_is_terminal() -> None:
    with pytest.raises(OnboardingError) as ei:
        transition("revoked", "active")
    assert ei.value.code == CODE_CONFLICT


def test_routable_requires_both() -> None:
    assert routable("active", "healthy") is True
    assert routable("paused", "healthy") is False
    assert routable("active", "unknown") is False
    assert routable("revoked", "healthy") is False


class _V:
    def __init__(self, snap: ValidationSnapshot) -> None:
        self.snap = snap

    def validate(
        self, *, platform: str, api_key: str, request_id: str
    ) -> ValidationSnapshot:
        return self.snap


def _ready_key() -> tuple[LifecycleService, uuid.UUID, uuid.UUID]:
    store = MemoryKeyStore()
    enc = CredentialEncryptor(os.urandom(32), "v1")
    v = _V(ValidationSnapshot("success", remaining_quota="9", quota_unit="token"))
    onboard = OnboardingService(
        validator=v, encryptor=enc, store=store, fingerprint_secret=b"s" * 32
    )
    seller = uuid.uuid4()
    out = onboard.onboard(
        seller_id=seller,
        role="seller",
        platform="volcano",
        api_key="sk-synthetic-test-key-not-real",
        idempotency_key="i",
        request_id="r",
    )
    lc = LifecycleService(store=store, encryptor=enc, validator=v)
    return lc, seller, out.key_id


def test_pause_then_resume_and_idor() -> None:
    lc, seller, key_id = _ready_key()
    paused = lc.pause(key_id, seller, "seller")
    assert paused["administrative_state"] == "paused"
    resumed = lc.resume(key_id, seller, "seller", "r2")
    assert resumed["administrative_state"] == "active"
    with pytest.raises(OnboardingError):
        lc.pause(key_id, uuid.uuid4(), "seller")


def test_revoke_wipes_ciphertext() -> None:
    lc, seller, key_id = _ready_key()
    lc.revoke(key_id, seller, "seller")
    row = lc._store.get(key_id)
    assert row is not None
    assert row["ciphertext"] is None
    with pytest.raises(OnboardingError):
        lc.resume(key_id, seller, "seller", "r3")


def test_resume_keeps_paused_on_failed_validate() -> None:
    store = MemoryKeyStore()
    enc = CredentialEncryptor(os.urandom(32), "v1")
    ok = _V(ValidationSnapshot("success", remaining_quota="3", quota_unit="t"))
    onboard = OnboardingService(
        validator=ok, encryptor=enc, store=store, fingerprint_secret=b"s" * 32
    )
    seller = uuid.uuid4()
    out = onboard.onboard(
        seller_id=seller,
        role="seller",
        platform="volcano",
        api_key="sk-synthetic-test-key-not-real",
        idempotency_key="i",
        request_id="r",
    )
    bad = _V(ValidationSnapshot("invalid"))
    lc = LifecycleService(store=store, encryptor=enc, validator=bad)
    lc.pause(out.key_id, seller, "seller")
    with pytest.raises(OnboardingError) as ei:
        lc.resume(out.key_id, seller, "seller", "r")
    assert ei.value.code == CODE_VALIDATION_FAILED
    assert store.get(out.key_id)["administrative_state"] == "paused"
