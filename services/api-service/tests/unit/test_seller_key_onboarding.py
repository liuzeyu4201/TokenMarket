"""Onboarding service: SF06 gate, duplicate, idempotency, no plaintext leak."""

from __future__ import annotations

import os
import uuid

import pytest

from app.domain.sellerkeys.codes import (
    CODE_DUPLICATE,
    CODE_INVALID_KEY,
    CODE_UNAUTHORIZED,
    CODE_ZERO_QUOTA,
    OnboardingError,
)
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.memory_store import MemoryKeyStore
from app.domain.sellerkeys.service import OnboardingService
from app.domain.sellerkeys.validator_port import ValidationSnapshot


class FakeValidator:
    def __init__(self, snap: ValidationSnapshot) -> None:
        self.snap = snap
        self.calls = 0

    def validate(
        self, *, platform: str, api_key: str, request_id: str
    ) -> ValidationSnapshot:
        self.calls += 1
        return self.snap


def _svc(
    snap: ValidationSnapshot,
) -> tuple[OnboardingService, MemoryKeyStore, FakeValidator]:
    store = MemoryKeyStore()
    v = FakeValidator(snap)
    enc = CredentialEncryptor(os.urandom(32), "v1")
    svc = OnboardingService(
        validator=v, encryptor=enc, store=store, fingerprint_secret=b"s" * 32
    )
    return svc, store, v


def test_success_quota_unavailable_persists_unknown_health() -> None:
    svc, store, v = _svc(ValidationSnapshot("quota_unavailable", validity="valid"))
    seller = uuid.uuid4()
    out = svc.onboard(
        seller_id=seller,
        role="seller",
        platform="volcano",
        api_key="sk-synthetic-test-key-not-real",
        idempotency_key="idem-1",
        request_id="r1",
    )
    assert out.health_state == "unknown"
    assert out.administrative_state == "active"
    assert "sk-synthetic" not in out.masked_hint or "****" in out.masked_hint
    assert v.calls == 1
    row = store.rows[out.key_id]
    assert b"sk-synthetic-test-key-not-real" not in row["ciphertext"]


def test_success_positive_quota_healthy() -> None:
    svc, store, _ = _svc(
        ValidationSnapshot(
            "success", remaining_quota="100", quota_unit="token", validity="valid"
        )
    )
    out = svc.onboard(
        seller_id=uuid.uuid4(),
        role="both",
        platform="volcano",
        api_key="sk-synthetic-test-key-not-real",
        idempotency_key="idem-2",
        request_id="r2",
    )
    assert out.health_state == "healthy"
    assert out.remaining_quota == "100"


def test_invalid_key_not_persisted() -> None:
    svc, store, _ = _svc(ValidationSnapshot("invalid"))
    with pytest.raises(OnboardingError) as ei:
        svc.onboard(
            seller_id=uuid.uuid4(),
            role="seller",
            platform="volcano",
            api_key="sk-bad",
            idempotency_key="i",
            request_id="r",
        )
    assert ei.value.code == CODE_INVALID_KEY
    assert store.rows == {}


def test_zero_quota_not_persisted() -> None:
    svc, store, _ = _svc(
        ValidationSnapshot("success", remaining_quota="0", validity="valid")
    )
    with pytest.raises(OnboardingError) as ei:
        svc.onboard(
            seller_id=uuid.uuid4(),
            role="seller",
            platform="volcano",
            api_key="sk-z",
            idempotency_key="i",
            request_id="r",
        )
    assert ei.value.code == CODE_ZERO_QUOTA
    assert store.rows == {}


def test_duplicate_fingerprint() -> None:
    snap = ValidationSnapshot("quota_unavailable", validity="valid")
    svc, _, v = _svc(snap)
    args = dict(
        seller_id=uuid.uuid4(),
        role="seller",
        platform="volcano",
        api_key="sk-synthetic-test-key-not-real",
        request_id="r",
    )
    svc.onboard(idempotency_key="a", **args)
    with pytest.raises(OnboardingError) as ei:
        svc.onboard(idempotency_key="b", **args)
    assert ei.value.code == CODE_DUPLICATE
    assert v.calls == 2


def test_idempotent_replay_same_digest() -> None:
    snap = ValidationSnapshot("quota_unavailable", validity="valid")
    svc, _, v = _svc(snap)
    seller = uuid.uuid4()
    a = svc.onboard(
        seller_id=seller,
        role="seller",
        platform="volcano",
        api_key="sk-synthetic-test-key-not-real",
        idempotency_key="same",
        request_id="r1",
    )
    b = svc.onboard(
        seller_id=seller,
        role="seller",
        platform="volcano",
        api_key="sk-synthetic-test-key-not-real",
        idempotency_key="same",
        request_id="r2",
    )
    assert a.key_id == b.key_id
    assert b.replayed is True
    assert v.calls == 1


class DuplicateInsertStore(MemoryKeyStore):
    def find_by_fingerprint(self, platform: str, fingerprint: str) -> uuid.UUID | None:
        return None

    def insert(self, record: dict[str, object]) -> uuid.UUID:
        raise ValueError("duplicate")


def test_insert_race_maps_to_duplicate_409() -> None:
    store = DuplicateInsertStore()
    v = FakeValidator(
        ValidationSnapshot("success", remaining_quota="9", quota_unit="t")
    )
    enc = CredentialEncryptor(os.urandom(32), "v1")
    svc = OnboardingService(
        validator=v, encryptor=enc, store=store, fingerprint_secret=b"s" * 32
    )
    with pytest.raises(OnboardingError) as ei:
        svc.onboard(
            seller_id=uuid.uuid4(),
            role="seller",
            platform="volcano",
            api_key="sk-synthetic-test-key-not-real",
            idempotency_key="race",
            request_id="r",
        )
    assert ei.value.code == CODE_DUPLICATE
    assert ei.value.http_status == 409


def test_buyer_rejected() -> None:
    svc, _, _ = _svc(ValidationSnapshot("success", remaining_quota="1"))
    with pytest.raises(OnboardingError) as ei:
        svc.onboard(
            seller_id=uuid.uuid4(),
            role="buyer",
            platform="volcano",
            api_key="sk-x",
            idempotency_key="k",
            request_id="r",
        )
    assert ei.value.code == CODE_UNAUTHORIZED
