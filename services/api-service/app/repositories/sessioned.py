"""Per-call SQLAlchemy sessions for domain stores (commit on success)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.repositories.sellerkeys import SQLKeyStore

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

    def get_idempotency(self, key: str) -> tuple[str, uuid.UUID | None] | None:
        return self._run(lambda s: s.get_idempotency(key))

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

    def list_routable(self) -> list[dict[str, Any]]:
        return self._run(lambda s: s.list_routable())

    def apply_health(self, key_id: uuid.UUID, health: str) -> None:
        self._run(lambda s: s.apply_health(key_id, health))
