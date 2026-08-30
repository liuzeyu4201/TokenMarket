"""Per-call SQLAlchemy sessions for domain stores (commit on success)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.domain.proxykeys.service import IssuedProxyKey
from app.domain.usage.service import UsageRecord
from app.repositories.proxykeys import SQLProxyStore
from app.repositories.sellerkeys import SQLKeyStore
from app.repositories.usage import SQLUsageStore

T = TypeVar("T")


class SessionedSQLKeyStore:
    def __init__(self, maker: sessionmaker[Session]) -> None:
        self._maker = maker

    def _run(self, fn: Callable[[SQLKeyStore], T]) -> T:
        session = self._maker()
        try:
            out = fn(SQLKeyStore(session))
            session.commit()
            return out
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def find_by_fingerprint(self, platform: str, fingerprint: str) -> uuid.UUID | None:
        return self._run(lambda s: s.find_by_fingerprint(platform, fingerprint))

    def insert(self, record: dict[str, Any]) -> uuid.UUID:
        return self._run(lambda s: s.insert(record))

    def get_idempotency(
        self, actor_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None:
        return self._run(lambda s: s.get_idempotency(actor_id, key))

    def put_idempotency(
        self,
        key: str,
        seller_id: uuid.UUID,
        digest: str,
        code: str,
        key_id: uuid.UUID | None,
    ) -> None:
        self._run(lambda s: s.put_idempotency(key, seller_id, digest, code, key_id))

    def get(self, key_id: uuid.UUID) -> dict[str, Any] | None:
        return self._run(lambda s: s.get(key_id))

    def list_by_seller(self, seller_id: uuid.UUID) -> list[dict[str, Any]]:
        return self._run(lambda s: s.list_by_seller(seller_id))

    def save(self, record: dict[str, Any]) -> None:
        self._run(lambda s: s.save(record))

    def save_if_unmodified(self, record: dict[str, Any], expected_version: int) -> bool:
        return self._run(lambda s: s.save_if_unmodified(record, expected_version))

    def persisted_key_versions(self) -> set[str]:
        return self._run(lambda s: s.persisted_key_versions())

    def list_routable(self) -> list[dict[str, Any]]:
        return self._run(lambda s: s.list_routable())

    def apply_health(self, key_id: uuid.UUID, health: str) -> None:
        self._run(lambda s: s.apply_health(key_id, health))


class SessionedProxyStore:
    def __init__(self, maker: sessionmaker[Session]) -> None:
        self._maker = maker

    def _run(self, fn: Callable[[SQLProxyStore], T]) -> T:
        session = self._maker()
        try:
            out = fn(SQLProxyStore(session))
            session.commit()
            return out
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_by_hash(self, secret_hash: str) -> IssuedProxyKey | None:
        return self._run(lambda s: s.get_by_hash(secret_hash))

    def get_by_id(self, key_id: uuid.UUID) -> IssuedProxyKey | None:
        return self._run(lambda s: s.get_by_id(key_id))

    def insert(self, rec: IssuedProxyKey, secret_hash: str) -> None:
        self._run(lambda s: s.insert(rec, secret_hash))

    def save(self, rec: IssuedProxyKey) -> None:
        self._run(lambda s: s.save(rec))

    def list_by_buyer(self, buyer_id: uuid.UUID) -> list[IssuedProxyKey]:
        return self._run(lambda s: s.list_by_buyer(buyer_id))

    def get_idempotency(
        self, actor_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None:
        return self._run(lambda s: s.get_idempotency(actor_id, key))

    def put_idempotency(
        self,
        key: str,
        buyer_id: uuid.UUID,
        digest: str,
        key_id: uuid.UUID | None,
    ) -> None:
        self._run(lambda s: s.put_idempotency(key, buyer_id, digest, key_id))

    def list_by_project(self, project_id: uuid.UUID) -> list[IssuedProxyKey]:
        return self._run(lambda s: s.list_by_project(project_id))

    def replace_hash(self, rec: IssuedProxyKey, secret_hash: str) -> None:
        self._run(lambda s: s.replace_hash(rec, secret_hash))

    def stored_hash(self, key_id: uuid.UUID) -> str | None:
        return self._run(lambda s: s.stored_hash(key_id))

    def consume_quota(
        self, key_id: uuid.UUID, period_start: datetime, limit: int
    ) -> bool:
        return self._run(lambda s: s.consume_quota(key_id, period_start, limit))


class SessionedUsageStore:
    def __init__(self, maker: sessionmaker[Session]) -> None:
        self._maker = maker

    def _run(self, fn: Callable[[SQLUsageStore], T]) -> T:
        session = self._maker()
        try:
            out = fn(SQLUsageStore(session))
            session.commit()
            return out
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get(self, request_id: str) -> UsageRecord | None:
        return self._run(lambda s: s.get(request_id))

    def insert(self, rec: UsageRecord) -> None:
        self._run(lambda s: s.insert(rec))

    def add_conflict(self, request_id: str, reason: str) -> None:
        self._run(lambda s: s.add_conflict(request_id, reason))

    def purge_before(self, cutoff: datetime) -> int:
        return self._run(lambda s: s.purge_before(cutoff))
