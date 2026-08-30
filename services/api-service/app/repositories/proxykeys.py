"""Sync SQLAlchemy adapter for proxy keys."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.owners import owner_can_use_proxy_keys
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.domain.proxykeys.models import ProxyKey, ProxyKeyIdempotency, ProxyKeyQuota
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
        masked_prefix=getattr(row, "masked_prefix", None) or "tmk-",
        name=row.name,
        project_id=getattr(row, "project_id", None),
        protocols=list(getattr(row, "protocols", None) or []),
        allowed_models=list(getattr(row, "allowed_models", None) or []),
        allowed_cidrs=list(getattr(row, "allowed_cidrs", None) or []),
        quota_period=getattr(row, "quota_period", None),
        quota_limit=getattr(row, "quota_limit", None),
        expires_at=getattr(row, "expires_at", None),
        secret_hash=row.secret_hash,
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
                project_id=rec.project_id,
                masked_prefix=rec.masked_prefix or "tmk-",
                protocols=list(rec.protocols or []),
                allowed_models=list(rec.allowed_models or []),
                allowed_cidrs=list(rec.allowed_cidrs or []),
                quota_period=rec.quota_period,
                quota_limit=rec.quota_limit,
                expires_at=rec.expires_at,
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
        if rec.status == "disabled":
            row.disabled_at = datetime.now(timezone.utc)
        row.masked_suffix = rec.masked_suffix
        row.masked_prefix = rec.masked_prefix or row.masked_prefix

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

    def list_by_project(self, project_id: uuid.UUID) -> list[IssuedProxyKey]:
        rows = self._s.execute(
            select(ProxyKey).where(
                ProxyKey.project_id == project_id, ProxyKey.soft_deleted.is_(False)
            )
        ).scalars()
        return [_to_issued(r) for r in rows]

    def replace_hash(self, rec: IssuedProxyKey, secret_hash: str) -> None:
        row = self._s.get(ProxyKey, rec.key_id)
        if row is None:
            return
        row.secret_hash = secret_hash
        row.masked_suffix = rec.masked_suffix
        row.masked_prefix = rec.masked_prefix or "tmk-"
        row.status = rec.status
        row.rotated_at = datetime.now(timezone.utc)
        rec.secret_hash = secret_hash
        self._s.flush()

    def stored_hash(self, key_id: uuid.UUID) -> str | None:
        row = self._s.get(ProxyKey, key_id)
        return None if row is None else row.secret_hash

    def consume_quota(
        self, key_id: uuid.UUID, period_start: datetime, limit: int
    ) -> bool:
        stmt = (
            pg_insert(ProxyKeyQuota)
            .values(key_id=key_id, period_start=period_start, accepted=1)
            .on_conflict_do_update(
                index_elements=["key_id", "period_start"],
                set_={"accepted": ProxyKeyQuota.accepted + 1},
                where=ProxyKeyQuota.accepted < limit,
            )
            .returning(ProxyKeyQuota.accepted)
        )
        row = self._s.execute(stmt).first()
        return row is not None
