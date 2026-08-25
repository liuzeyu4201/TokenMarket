"""PostgreSQL-backed seller key store: unique fingerprint race and idempotency."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.sellerkeys.codes import CODE_DUPLICATE, OnboardingError
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.service import OnboardingService
from app.domain.sellerkeys.validator_port import ValidationSnapshot
from app.repositories.sessioned import SessionedSQLKeyStore
from tests.conftest import PostgresHandle
from tests.integration.conftest_register import run_alembic

pytestmark = pytest.mark.integration


class _Validator:
    def __init__(self, snap: ValidationSnapshot) -> None:
        self.snap = snap
        self.calls = 0

    def validate(
        self, *, platform: str, api_key: str, request_id: str
    ) -> ValidationSnapshot:
        self.calls += 1
        return self.snap


def test_sessioned_sql_idempotency_and_duplicate_fingerprint(
    postgres_container: PostgresHandle,
) -> None:
    url = postgres_container.database_url()
    up = run_alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    engine = create_engine(url)
    try:
        store = SessionedSQLKeyStore(sessionmaker(engine))
        enc = CredentialEncryptor(os.urandom(32), "v1")
        validator = _Validator(
            ValidationSnapshot(
                "success", remaining_quota="10", quota_unit="token", validity="valid"
            )
        )
        svc = OnboardingService(
            validator=validator,
            encryptor=enc,
            store=store,
            fingerprint_secret=b"s" * 32,
        )
        seller = uuid.uuid4()
        first = svc.onboard(
            seller_id=seller,
            role="seller",
            platform="volcano",
            api_key="sk-synthetic-test-key-not-real",
            idempotency_key="sql-idem-1",
            request_id="r1",
        )
        replay = svc.onboard(
            seller_id=seller,
            role="seller",
            platform="volcano",
            api_key="sk-synthetic-test-key-not-real",
            idempotency_key="sql-idem-1",
            request_id="r2",
        )
        assert replay.key_id == first.key_id
        assert replay.replayed is True
        assert validator.calls == 1

        with pytest.raises(OnboardingError) as ei:
            svc.onboard(
                seller_id=seller,
                role="seller",
                platform="volcano",
                api_key="sk-synthetic-test-key-not-real",
                idempotency_key="sql-idem-2",
                request_id="r3",
            )
        assert ei.value.code == CODE_DUPLICATE
        assert ei.value.http_status == 409

        row = store.get(first.key_id)
        assert row is not None
        row["id"] = uuid.uuid4()
        row["created_request_id"] = "race"
        with pytest.raises(ValueError, match="duplicate"):
            store.insert(row)
    finally:
        engine.dispose()
