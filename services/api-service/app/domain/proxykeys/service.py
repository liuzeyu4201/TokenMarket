"""Proxy key issue/revoke and lookup hash (SF10/SF11)."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

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
    masked_prefix: str = "tmk-"
    name: str | None = None
    replayed: bool = False
    project_id: uuid.UUID | None = None
    protocols: list[str] = field(default_factory=list)
    allowed_models: list[str] = field(default_factory=list)
    allowed_cidrs: list[str] = field(default_factory=list)
    quota_period: str | None = None
    quota_limit: int | None = None
    expires_at: datetime | None = None
    secret_hash: str | None = None


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

    def list_by_project(self, project_id: uuid.UUID) -> list[IssuedProxyKey]: ...

    def replace_hash(self, rec: IssuedProxyKey, secret_hash: str) -> None: ...

    def consume_quota(
        self, key_id: uuid.UUID, period_start: datetime, limit: int
    ) -> bool: ...

    def stored_hash(self, key_id: uuid.UUID) -> str | None: ...


class MemoryProxyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_hash: dict[str, IssuedProxyKey] = {}
        self.by_id: dict[uuid.UUID, IssuedProxyKey] = {}
        self.idem: dict[tuple[uuid.UUID, str], tuple[str, uuid.UUID | None]] = {}
        self.hashes: dict[uuid.UUID, str] = {}
        self.owners: dict[uuid.UUID, OwnerState] = {}
        self.quota: dict[tuple[uuid.UUID, datetime], int] = {}

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
            rec.secret_hash = secret_hash
            stored = deepcopy(rec)
            stored.secret_once = None
            self.by_hash[secret_hash] = stored
            self.by_id[rec.key_id] = stored
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

    def list_by_project(self, project_id: uuid.UUID) -> list[IssuedProxyKey]:
        with self._lock:
            return [r for r in self.by_id.values() if r.project_id == project_id]

    def replace_hash(self, rec: IssuedProxyKey, secret_hash: str) -> None:
        with self._lock:
            old = self.hashes.get(rec.key_id)
            if old:
                self.by_hash.pop(old, None)
            rec.secret_hash = secret_hash
            persisted = deepcopy(rec)
            persisted.secret_once = None
            self.hashes[rec.key_id] = secret_hash
            self.by_id[rec.key_id] = persisted
            self.by_hash[secret_hash] = persisted

    def consume_quota(
        self, key_id: uuid.UUID, period_start: datetime, limit: int
    ) -> bool:
        with self._lock:
            cur = self.quota.get((key_id, period_start), 0)
            if cur >= limit:
                return False
            self.quota[(key_id, period_start)] = cur + 1
            return True

    def stored_hash(self, key_id: uuid.UUID) -> str | None:
        with self._lock:
            return self.hashes.get(key_id)


class ProxyKeyService:
    def __init__(
        self,
        pepper: bytes,
        store: ProxyKeyStore | None = None,
        projects: Any = None,
        bindings: Any = None,
    ) -> None:
        self._pepper = pepper
        self._store: ProxyKeyStore = store if store is not None else MemoryProxyStore()
        self._projects = projects
        self._bindings = bindings

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
        return self.authorize(secret)

    def _digest_ok(self, computed: str, rec: IssuedProxyKey | None) -> bool:
        dummy = "0" * 64
        stored = rec.secret_hash if rec is not None else None
        if stored is None and rec is not None:
            stored = self._store.stored_hash(rec.key_id)
        left = computed if len(computed) == 64 else dummy
        right = stored if stored and len(stored) == 64 else dummy
        matched = hmac.compare_digest(left, right)
        return rec is not None and matched and stored == computed

    def _period_start(self, now: datetime, period: str) -> datetime:
        utc = now.astimezone(timezone.utc)
        if period == "month":
            return utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return utc.replace(hour=0, minute=0, second=0, microsecond=0)

    def _ip_allowed(self, rec: IssuedProxyKey, client_ip: str | None) -> bool:
        if not rec.allowed_cidrs:
            return True
        if not client_ip:
            return False
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        for raw in rec.allowed_cidrs:
            try:
                net = ipaddress.ip_network(raw, strict=False)
            except ValueError:
                continue
            if addr in net:
                return True
        return False

    def authorize(
        self,
        secret: str,
        *,
        protocol: str | None = None,
        model: str | None = None,
        client_ip: str | None = None,
        now: datetime | None = None,
    ) -> IssuedProxyKey | None:
        dummy = "0" * 64
        if not secret.startswith("tmk-") or len(secret) < 4 + 32:
            hmac.compare_digest(dummy, dummy)
            return None
        computed = hash_proxy_secret(secret, self._pepper)
        rec = self._store.get_by_hash(computed)
        if not self._digest_ok(computed, rec):
            return None
        assert rec is not None
        scoped = self._scope_ok(
            rec, protocol=protocol, model=model, client_ip=client_ip, now=now
        )
        if scoped is None:
            return None
        # Re-check owner after scope so suspend cannot succeed post-commit.
        if self._store.get_by_hash(computed) is None:
            return None
        return scoped

    def authorize_hash(
        self,
        secret_hash: str,
        *,
        protocol: str | None = None,
        model: str | None = None,
        client_ip: str | None = None,
        now: datetime | None = None,
    ) -> IssuedProxyKey | None:
        rec = self._store.get_by_hash(secret_hash)
        if not self._digest_ok(secret_hash, rec):
            return None
        assert rec is not None
        scoped = self._scope_ok(
            rec, protocol=protocol, model=model, client_ip=client_ip, now=now
        )
        if scoped is None:
            return None
        if self._store.get_by_hash(secret_hash) is None:
            return None
        return scoped

    def _scope_ok(
        self,
        rec: IssuedProxyKey,
        *,
        protocol: str | None,
        model: str | None,
        client_ip: str | None,
        now: datetime | None,
    ) -> IssuedProxyKey | None:
        if rec.status != "active":
            return None
        stamp = now or datetime.now(timezone.utc)
        if rec.expires_at is not None and stamp >= rec.expires_at:
            return None
        if rec.protocols:
            if protocol is None or protocol not in rec.protocols:
                return None
        if rec.allowed_models:
            if model is None or model not in rec.allowed_models:
                return None
        if not self._ip_allowed(rec, client_ip):
            return None
        if rec.quota_limit is not None and rec.quota_period:
            start = self._period_start(stamp, rec.quota_period)
            if not self._store.consume_quota(rec.key_id, start, rec.quota_limit):
                return None
        return rec

    def lookup_hash(
        self,
        secret_hash: str,
        *,
        protocol: str | None = None,
        model: str | None = None,
        client_ip: str | None = None,
    ) -> IssuedProxyKey | None:
        return self.authorize_hash(
            secret_hash, protocol=protocol, model=model, client_ip=client_ip
        )

    def lookup_runtime(self, secret_hash: str) -> IssuedProxyKey | None:
        """Internal gateway lookup: hash is identity; protocol is applied at admit."""
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

    def issue_for_project(
        self,
        *,
        buyer_id: uuid.UUID,
        project_id: uuid.UUID,
        protocols: Sequence[str],
        role: str = "buyer",
        workspace: str | None = "buyer",
        name: str | None = None,
        allowed_models: Sequence[str] | None = None,
        allowed_cidrs: Sequence[str] | None = None,
        quota_period: str | None = None,
        quota_limit: int | None = None,
        expires_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> IssuedProxyKey:
        if role not in ("buyer", "both") or (
            workspace is not None and workspace != "buyer"
        ):
            raise ProxyKeyError(
                "FORBIDDEN_ROLE", "当前工作区无权执行该操作", http_status=403
            )
        protos = list(protocols)
        if not protos or any(
            p not in ("openai", "anthropic", "vertex") for p in protos
        ):
            raise ProxyKeyError("VALIDATION", "请求参数不合法", http_status=400)
        models = list(allowed_models or [])
        cidrs = list(allowed_cidrs or [])
        for raw in cidrs:
            try:
                ipaddress.ip_network(raw, strict=False)
            except ValueError as exc:
                raise ProxyKeyError(
                    "VALIDATION", "请求参数不合法", http_status=400
                ) from exc
        if (quota_period is None) != (quota_limit is None):
            raise ProxyKeyError("VALIDATION", "请求参数不合法", http_status=400)
        if quota_limit is not None and quota_limit < 1:
            raise ProxyKeyError("VALIDATION", "请求参数不合法", http_status=400)
        if quota_period is not None and quota_period not in ("day", "month"):
            raise ProxyKeyError("VALIDATION", "请求参数不合法", http_status=400)
        project = self._require_project(project_id, buyer_id)
        self._assert_binding_subset(project_id, buyer_id, protos, models)
        digest = hashlib.sha256(
            f"{project_id}|{','.join(protos)}|{name or ''}".encode()
        ).hexdigest()
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
            platform="project",
            secret_once=secret,
            status="active",
            masked_suffix=_mask(secret),
            masked_prefix="tmk-",
            name=name,
            project_id=project.project_id,
            protocols=protos,
            allowed_models=models,
            allowed_cidrs=cidrs,
            quota_period=quota_period,
            quota_limit=quota_limit,
            expires_at=expires_at,
        )
        self._store.insert(rec, hash_proxy_secret(secret, self._pepper))
        if idempotency_key:
            self._store.put_idempotency(idempotency_key, buyer_id, digest, rec.key_id)
        return rec

    def _require_project(self, project_id: uuid.UUID, buyer_id: uuid.UUID) -> Any:
        if self._projects is None:
            raise ProxyKeyError("NOT_FOUND", "资源不存在", http_status=404)
        rec = self._projects.get(project_id)
        if (
            rec is None
            or rec.owner_account_id != buyer_id
            or rec.deleted_at is not None
        ):
            raise ProxyKeyError("NOT_FOUND", "资源不存在", http_status=404)
        if rec.status == "archived":
            raise ProxyKeyError(
                "ILLEGAL_STATE_TRANSITION", "非法状态转换", http_status=409
            )
        return rec

    def _assert_binding_subset(
        self,
        project_id: uuid.UUID,
        buyer_id: uuid.UUID,
        protocols: list[str],
        models: list[str],
    ) -> None:
        if self._bindings is None:
            raise ProxyKeyError(
                "PROVIDER_BINDING_REQUIRED",
                "启用协议前必须存在对应 Provider Binding",
                http_status=409,
            )
        for proto in protocols:
            if not self._bindings.has_enabled_binding(
                owner_id=buyer_id, project_id=project_id, protocol=proto
            ):
                raise ProxyKeyError(
                    "PROVIDER_BINDING_REQUIRED",
                    "启用协议前必须存在对应 Provider Binding",
                    http_status=409,
                )
            snap = None
            active = getattr(self._bindings, "active", None)
            if callable(active):
                try:
                    snap = active(
                        project_id=project_id,
                        protocol=proto,
                        owner_id=buyer_id,
                        role="buyer",
                        workspace="buyer",
                    )
                except Exception:
                    snap = None
            allowed = list(getattr(snap, "allowed_models", []) or [])
            if models and allowed and any(m not in allowed for m in models):
                raise ProxyKeyError(
                    "SCOPE_EXCEEDED", "权限超出 Binding 能力", http_status=409
                )

    def _owned_project_key(
        self, key_id: uuid.UUID, buyer_id: uuid.UUID, project_id: uuid.UUID
    ) -> IssuedProxyKey:
        rec = self._store.get_by_id(key_id)
        if rec is None or rec.buyer_id != buyer_id or rec.project_id != project_id:
            raise ProxyKeyError("NOT_FOUND", "资源不存在", http_status=404)
        return rec

    def rotate(
        self, key_id: uuid.UUID, buyer_id: uuid.UUID, project_id: uuid.UUID, role: str
    ) -> IssuedProxyKey:
        if role not in ("buyer", "both"):
            raise ProxyKeyError(
                "FORBIDDEN_ROLE", "当前工作区无权执行该操作", http_status=403
            )
        rec = self._owned_project_key(key_id, buyer_id, project_id)
        if rec.status == "revoked":
            raise ProxyKeyError("NOT_FOUND", "资源不存在", http_status=404)
        secret = generate_proxy_secret()
        rec.secret_once = secret
        rec.masked_suffix = _mask(secret)
        rec.replayed = False
        rec.status = "active"
        self._store.replace_hash(rec, hash_proxy_secret(secret, self._pepper))
        return rec

    def disable(
        self, key_id: uuid.UUID, buyer_id: uuid.UUID, project_id: uuid.UUID, role: str
    ) -> IssuedProxyKey:
        rec = self._owned_project_key(key_id, buyer_id, project_id)
        if rec.status == "revoked":
            raise ProxyKeyError("NOT_FOUND", "资源不存在", http_status=404)
        rec.status = "disabled"
        rec.secret_once = None
        self._store.save(rec)
        return rec

    def enable(
        self, key_id: uuid.UUID, buyer_id: uuid.UUID, project_id: uuid.UUID, role: str
    ) -> IssuedProxyKey:
        rec = self._owned_project_key(key_id, buyer_id, project_id)
        if rec.status == "revoked":
            raise ProxyKeyError(
                "ILLEGAL_STATE_TRANSITION", "已撤销的 Key 不可恢复", http_status=409
            )
        rec.status = "active"
        rec.secret_once = None
        self._store.save(rec)
        return rec

    def revoke_project_key(
        self, key_id: uuid.UUID, buyer_id: uuid.UUID, project_id: uuid.UUID, role: str
    ) -> IssuedProxyKey:
        rec = self._owned_project_key(key_id, buyer_id, project_id)
        rec.status = "revoked"
        rec.secret_once = None
        self._store.save(rec)
        return rec

    def list_project(
        self, buyer_id: uuid.UUID, project_id: uuid.UUID, role: str
    ) -> list[IssuedProxyKey]:
        if role not in ("buyer", "both"):
            raise ProxyKeyError(
                "FORBIDDEN_ROLE", "当前工作区无权执行该操作", http_status=403
            )
        self._require_project(project_id, buyer_id)
        return [
            r for r in self._store.list_by_project(project_id) if r.buyer_id == buyer_id
        ]
