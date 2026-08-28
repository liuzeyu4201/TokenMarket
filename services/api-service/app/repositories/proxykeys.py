"""Sync SQLAlchemy adapter for proxy keys."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.owners import owner_can_use_proxy_keys
from app.domain.proxykeys.models import ProxyKey, ProxyKeyIdempotency
from app.domain.proxykeys.service import IssuedProxyKey
from app.domain.users.models import User, UserRole, UserStatus


def _to_issued(row: ProxyKey) -> IssuedProxyKey:
    return IssuedProxyKey(
        key_id=row.id,
        buyer_id=row.buyer_id,
        platform=row.platform,
        secret_once=None,
        status=row.status,
        masked_suffix=row.masked_suffix,
        name=row.name,
    )


class SQLProxyStore:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_hash(self, secret_hash: str) -> IssuedProxyKey | None:
        row = self._s.execute(
            select(ProxyKey)
            .join(User, User.id == ProxyKey.buyer_id)
            .where(
                ProxyKey.secret_hash == secret_hash,
                ProxyKey.soft_deleted.is_(False),
                User.is_deleted.is_(False),
                User.status == UserStatus.active,
                User.role.in_((UserRole.buyer, UserRole.both)),
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        owner = self._s.get(User, row.buyer_id)
        if owner is None or not owner_can_use_proxy_keys(
            owner.status.value, owner.role.value, owner.is_deleted
        ):
            return None
        return _to_issued(row)

    def get_by_id(self, key_id: uuid.UUID) -> IssuedProxyKey | None:
        row = self._s.get(ProxyKey, key_id)
        if row is None or row.soft_deleted:
            return None
        return _to_issued(row)

    def insert(self, rec: IssuedProxyKey, secret_hash: str) -> None:
        self._s.add(
            ProxyKey(
                id=rec.key_id,
                buyer_id=rec.buyer_id,
                platform=rec.platform,
                secret_hash=secret_hash,
                masked_suffix=rec.masked_suffix,
                name=rec.name,
                status=rec.status,
                secret_delivered=rec.secret_once is not None,
                created_request_id="issue",
                version=1,
                soft_deleted=False,
                created_at=datetime.now(timezone.utc),
            )
        )
        self._s.flush()

    def save(self, rec: IssuedProxyKey) -> None:
        row = self._s.get(ProxyKey, rec.key_id)
        if row is None:
            return
        row.status = rec.status
        if rec.status == "revoked":
            row.revoked_at = datetime.now(timezone.utc)

    def list_by_buyer(self, buyer_id: uuid.UUID) -> list[IssuedProxyKey]:
        rows = self._s.execute(
            select(ProxyKey).where(
                ProxyKey.buyer_id == buyer_id, ProxyKey.soft_deleted.is_(False)
            )
        ).scalars()
        return [_to_issued(r) for r in rows]

    def get_idempotency(
        self, actor_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None:
        row = self._s.get(ProxyKeyIdempotency, (actor_id, key))
        if row is None:
            return None
        return row.request_hash, row.result_key_id

    def put_idempotency(
        self,
        key: str,
        buyer_id: uuid.UUID,
        digest: str,
        key_id: uuid.UUID | None,
    ) -> None:
        existing = self._s.get(ProxyKeyIdempotency, (buyer_id, key))
        if existing is not None:
            existing.request_hash = digest
            existing.result_key_id = key_id
            return
        self._s.add(
            ProxyKeyIdempotency(
                idempotency_key=key,
                buyer_id=buyer_id,
                request_hash=digest,
                result_key_id=key_id,
                created_at=datetime.now(timezone.utc),
            )
        )
