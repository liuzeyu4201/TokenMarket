"""Proxy key issue/revoke and lookup hash (SF10/SF11)."""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.domain.owners import OwnerState, owner_state_allows_proxy


class ProxyKeyError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def hash_proxy_secret(secret: str, pepper: bytes) -> str:
    return hmac.new(pepper, secret.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_proxy_secret() -> str:
    return "tmk-" + os.urandom(24).hex()


def _mask(secret: str) -> str:
    if len(secret) < 8:
        return "****"
    return secret[-4:]


@dataclass
class IssuedProxyKey:
    key_id: uuid.UUID
    buyer_id: uuid.UUID
    platform: str
    secret_once: str | None
    status: str
    masked_suffix: str = ""
    name: str | None = None
    replayed: bool = False


class ProxyKeyStore(Protocol):
    def get_by_hash(self, secret_hash: str) -> IssuedProxyKey | None: ...

    def get_by_id(self, key_id: uuid.UUID) -> IssuedProxyKey | None: ...

    def insert(self, rec: IssuedProxyKey, secret_hash: str) -> None: ...

    def save(self, rec: IssuedProxyKey) -> None: ...

    def list_by_buyer(self, buyer_id: uuid.UUID) -> list[IssuedProxyKey]: ...

    def get_idempotency(
        self, actor_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None: ...

    def put_idempotency(
        self,
        key: str,
        buyer_id: uuid.UUID,
        digest: str,
        key_id: uuid.UUID | None,
    ) -> None: ...


class MemoryProxyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_hash: dict[str, IssuedProxyKey] = {}
        self.by_id: dict[uuid.UUID, IssuedProxyKey] = {}
        self.idem: dict[tuple[uuid.UUID, str], tuple[str, uuid.UUID | None]] = {}
        self.hashes: dict[uuid.UUID, str] = {}
        self.owners: dict[uuid.UUID, OwnerState] = {}

    def set_owner(
        self,
        user_id: uuid.UUID,
        *,
        status: str,
        role: str,
        is_deleted: bool = False,
    ) -> None:
        with self._lock:
            self.owners[user_id] = OwnerState(
                status=status, role=role, is_deleted=is_deleted
            )

    def get_by_hash(self, secret_hash: str) -> IssuedProxyKey | None:
        with self._lock:
            rec = self.by_hash.get(secret_hash)
            if rec is None:
                return rec
            owner = self.owners.get(rec.buyer_id)
            if not owner_state_allows_proxy(owner):
                return None
            return rec

    def get_by_id(self, key_id: uuid.UUID) -> IssuedProxyKey | None:
        with self._lock:
            return self.by_id.get(key_id)

    def insert(self, rec: IssuedProxyKey, secret_hash: str) -> None:
        with self._lock:
            self.by_hash[secret_hash] = rec
            self.by_id[rec.key_id] = rec
            self.hashes[rec.key_id] = secret_hash
            if rec.buyer_id not in self.owners:
                self.owners[rec.buyer_id] = OwnerState(
                    status="active", role="buyer", is_deleted=False
                )

    def save(self, rec: IssuedProxyKey) -> None:
        with self._lock:
            self.by_id[rec.key_id] = rec
            h = self.hashes.get(rec.key_id)
            if h:
                self.by_hash[h] = rec

    def list_by_buyer(self, buyer_id: uuid.UUID) -> list[IssuedProxyKey]:
        with self._lock:
            return [r for r in self.by_id.values() if r.buyer_id == buyer_id]

    def get_idempotency(
        self, actor_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None:
        with self._lock:
            return self.idem.get((actor_id, key))

    def put_idempotency(
        self,
        key: str,
        buyer_id: uuid.UUID,
        digest: str,
        key_id: uuid.UUID | None,
    ) -> None:
        with self._lock:
            self.idem[(buyer_id, key)] = (digest, key_id)


class ProxyKeyService:
    def __init__(self, pepper: bytes, store: ProxyKeyStore | None = None) -> None:
        self._pepper = pepper
        self._store: ProxyKeyStore = store if store is not None else MemoryProxyStore()

    def issue(
        self,
        *,
        buyer_id: uuid.UUID,
        platform: str = "volcano",
        name: str | None = None,
        role: str = "buyer",
        idempotency_key: str | None = None,
    ) -> IssuedProxyKey:
        if role not in ("buyer", "both"):
            raise ProxyKeyError("UNAUTHORIZED", "需要买家身份", http_status=403)
        if platform != "volcano":
            raise ProxyKeyError("UNSUPPORTED_PLATFORM", "平台不受支持", http_status=400)
        digest = hashlib.sha256(f"{platform}|{name or ''}".encode()).hexdigest()
        if idempotency_key:
            existing = self._store.get_idempotency(buyer_id, idempotency_key)
            if existing:
                prev_digest, prev_id = existing
                if prev_digest != digest:
                    raise ProxyKeyError(
                        "IDEMPOTENCY_CONFLICT",
                        "幂等键与请求内容不一致",
                        http_status=409,
                    )
                if prev_id is None:
                    raise ProxyKeyError(
                        "TEMPORARY_UNAVAILABLE", "请稍后重试", http_status=503
                    )
                rec = self._store.get_by_id(prev_id)
                if rec is None:
                    raise ProxyKeyError(
                        "TEMPORARY_UNAVAILABLE", "请稍后重试", http_status=503
                    )
                rec.secret_once = None
                rec.replayed = True
                return rec
        secret = generate_proxy_secret()
        rec = IssuedProxyKey(
            key_id=uuid.uuid4(),
            buyer_id=buyer_id,
            platform=platform,
            secret_once=secret,
            status="active",
            masked_suffix=_mask(secret),
            name=name,
        )
        self._store.insert(rec, hash_proxy_secret(secret, self._pepper))
        if idempotency_key:
            self._store.put_idempotency(idempotency_key, buyer_id, digest, rec.key_id)
        return rec

    def authenticate(self, secret: str) -> IssuedProxyKey | None:
        if not secret.startswith("tmk-") or len(secret) < 4 + 32:
            return None
        rec = self._store.get_by_hash(hash_proxy_secret(secret, self._pepper))
        if rec is None or rec.status != "active":
            return None
        return rec

    def lookup_hash(self, secret_hash: str) -> IssuedProxyKey | None:
        rec = self._store.get_by_hash(secret_hash)
        if rec is None or rec.status != "active":
            return None
        return rec

    def revoke(
        self, key_id: uuid.UUID, buyer_id: uuid.UUID, role: str = "buyer"
    ) -> IssuedProxyKey:
        if role not in ("buyer", "both"):
            raise ProxyKeyError("UNAUTHORIZED", "需要买家身份", http_status=403)
        rec = self._store.get_by_id(key_id)
        if rec is None or rec.buyer_id != buyer_id:
            raise ProxyKeyError("NOT_FOUND", "资源不存在", http_status=404)
        rec.status = "revoked"
        rec.secret_once = None
        self._store.save(rec)
        return rec

    def list_mine(
        self, buyer_id: uuid.UUID, role: str = "buyer"
    ) -> list[IssuedProxyKey]:
        if role not in ("buyer", "both"):
            raise ProxyKeyError("UNAUTHORIZED", "需要买家身份", http_status=403)
        return self._store.list_by_buyer(buyer_id)

    def now(self) -> datetime:
        return datetime.now(timezone.utc)
