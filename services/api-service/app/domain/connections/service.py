"""Provider Connection lifecycle: encrypt, never read back on public paths."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from app.domain.authorization.workspace import effective_role
from app.domain.bindings.ports import ConnectionFact
from app.domain.connections.models import ConnectionRecord, utcnow
from app.domain.connections.ssrf import (
    OFFICIAL_BASE,
    SsrfError,
    default_resolver,
    validate_base_url,
)
from app.domain.connections.store import (
    ConnectionStore,
    MemoryConnectionStore,
    VersionConflict,
)
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.fingerprint import fingerprint_key

logger = logging.getLogger("api-service")

PROVIDERS = frozenset({"openai", "anthropic", "vertex"})
MODES = frozenset({"shared", "dedicated"})


class ConnectionError(Exception):
    def __init__(
        self, code: str, message: str, *, http_status: int, data: object | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data
        super().__init__(message)


class ServiceConnectionLookup:
    """Adapts ConnectionService.get_fact to Binding ConnectionLookup."""

    def __init__(self, service: ConnectionService) -> None:
        self._service = service

    def get(self, connection_id: uuid.UUID) -> ConnectionFact | None:
        return self._service.get_fact(connection_id)


class ConnectionService:
    def __init__(
        self,
        encryptor: CredentialEncryptor,
        fingerprint_secret: bytes,
        store: ConnectionStore | None = None,
        *,
        bindings: Any = None,
        resolver: Callable[..., list[str]] | None = None,
    ) -> None:
        self._enc = encryptor
        self._fp = fingerprint_secret
        self._store: ConnectionStore = (
            store if store is not None else MemoryConnectionStore()
        )
        self._bindings = bindings
        self._resolver = resolver

    def bind_bindings(self, bindings: Any) -> None:
        self._bindings = bindings

    def _require_seller(self, role: str, workspace: str | None) -> None:
        if workspace is None:
            if role not in ("seller", "both"):
                raise ConnectionError(
                    "FORBIDDEN_ROLE", "当前工作区无权执行该操作", http_status=403
                )
            return
        if effective_role(role, workspace) != "seller":
            raise ConnectionError(
                "FORBIDDEN_ROLE", "当前工作区无权执行该操作", http_status=403
            )

    def _owned(
        self, connection_id: uuid.UUID, seller_id: uuid.UUID
    ) -> ConnectionRecord:
        rec = self._store.get(connection_id)
        if rec is None or rec.seller_account_id != seller_id or rec.status == "deleted":
            raise ConnectionError("NOT_FOUND", "资源不存在", http_status=404)
        return rec

    def get_fact(self, connection_id: uuid.UUID) -> ConnectionFact | None:
        rec = self._store.get(connection_id)
        if rec is None or not rec.usable():
            return None
        return ConnectionFact(
            connection_id=rec.connection_id,
            provider=rec.provider,
            supply_mode=rec.supply_mode,
            usable=True,
        )

    def create(
        self,
        *,
        seller_id: uuid.UUID,
        provider: str,
        supply_mode: str,
        secret: str,
        role: str,
        workspace: str | None,
        request_id: str,
        region: str | None = None,
        purpose: str | None = None,
        base_url: str | None = None,
        project_number: str | None = None,
        location: str | None = None,
    ) -> ConnectionRecord:
        self._require_seller(role, workspace)
        if provider not in PROVIDERS or supply_mode not in MODES:
            raise ConnectionError("VALIDATION", "请求参数不合法", http_status=400)
        secret = (secret or "").strip()
        if not secret:
            raise ConnectionError("VALIDATION", "请求参数不合法", http_status=400)
        auth_type = "service_account" if provider == "vertex" else "api_key"
        if provider == "vertex" and (not project_number or not location):
            raise ConnectionError(
                "VALIDATION", "Vertex 需要 project_number 与 location", http_status=400
            )
        url = (base_url or OFFICIAL_BASE[provider]).strip()
        try:
            validate_base_url(
                url,
                resolver=self._resolver or default_resolver,
                skip_resolve=base_url is None,
            )
        except SsrfError as exc:
            raise ConnectionError(
                "SSRF_REJECTED", exc.message, http_status=400
            ) from exc
        nonce, ct, tag = self._enc.encrypt(secret.encode("utf-8"))
        now = utcnow()
        rec = ConnectionRecord(
            connection_id=uuid.uuid4(),
            seller_account_id=seller_id,
            provider=provider,
            supply_mode=supply_mode,
            auth_type=auth_type,
            base_url=url,
            region=region or location,
            purpose=purpose,
            project_number=project_number,
            location=location,
            nonce=nonce,
            ciphertext=ct,
            tag=tag,
            key_version=self._enc.key_version,
            credential_fingerprint=fingerprint_key(secret, self._fp, platform=provider),
            credential_version=1,
            status="active",
            created_at=now,
            updated_at=now,
        )
        self._store.create(rec)
        self._store.audit(
            seller_id=seller_id,
            connection_id=rec.connection_id,
            event_type="connection.created",
            request_id=request_id,
            payload={"provider": provider, "fingerprint": rec.credential_fingerprint},
        )
        return rec

    def list_mine(
        self, *, seller_id: uuid.UUID, role: str, workspace: str | None
    ) -> list[ConnectionRecord]:
        self._require_seller(role, workspace)
        return self._store.list_by_seller(seller_id)

    def get(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> ConnectionRecord:
        self._require_seller(role, workspace)
        return self._owned(connection_id, seller_id)

    def replace_credential(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        secret: str,
        expected_version: int,
        role: str,
        workspace: str | None,
        request_id: str,
        project_number: str | None = None,
        location: str | None = None,
    ) -> ConnectionRecord:
        self._require_seller(role, workspace)
        rec = self._owned(connection_id, seller_id)
        secret = (secret or "").strip()
        if not secret:
            raise ConnectionError("VALIDATION", "请求参数不合法", http_status=400)
        if rec.provider == "vertex":
            rec.project_number = project_number or rec.project_number
            rec.location = location or rec.location
            if not rec.project_number or not rec.location:
                raise ConnectionError(
                    "VALIDATION",
                    "Vertex 需要 project_number 与 location",
                    http_status=400,
                )
        nonce, ct, tag = self._enc.encrypt(secret.encode("utf-8"))
        rec.nonce, rec.ciphertext, rec.tag = nonce, ct, tag
        rec.key_version = self._enc.key_version
        rec.credential_fingerprint = fingerprint_key(
            secret, self._fp, platform=rec.provider
        )
        rec.credential_version = expected_version + 1
        rec.updated_at = utcnow()
        try:
            self._store.save_replace(rec, expected_version)
        except VersionConflict as exc:
            raise ConnectionError(
                "VERSION_CONFLICT", "凭据版本冲突，请重试", http_status=409
            ) from exc
        except KeyError as exc:
            raise ConnectionError("NOT_FOUND", "资源不存在", http_status=404) from exc
        self._store.audit(
            seller_id=seller_id,
            connection_id=connection_id,
            event_type="connection.credential_replaced",
            request_id=request_id,
            payload={"version": rec.credential_version},
        )
        return rec

    def delete(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> None:
        self._require_seller(role, workspace)
        rec = self._owned(connection_id, seller_id)
        rec.status = "deleted"
        rec.deleted_at = utcnow()
        rec.updated_at = rec.deleted_at
        rec.nonce = None
        rec.ciphertext = None
        rec.tag = None
        rec.key_version = None
        try:
            self._store.save_replace(rec, rec.credential_version)
        except KeyError as exc:
            raise ConnectionError("NOT_FOUND", "资源不存在", http_status=404) from exc
        self._store.audit(
            seller_id=seller_id,
            connection_id=connection_id,
            event_type="connection.deleted",
            request_id=request_id,
            payload={"fingerprint": rec.credential_fingerprint},
        )
        if self._bindings is not None:
            self._bindings.degrade_for_connection(connection_id, request_id)

    def unwrap(
        self,
        *,
        connection_id: uuid.UUID,
        purpose: str,
        request_id: str,
        actor_seller_id: uuid.UUID | None = None,
    ) -> str:
        if purpose not in ("proxy", "verify"):
            raise ConnectionError("VALIDATION", "请求参数不合法", http_status=400)
        rec = self._store.get(connection_id)
        if rec is None or not rec.usable():
            raise ConnectionError("NOT_FOUND", "资源不存在", http_status=404)
        if actor_seller_id is not None and rec.seller_account_id != actor_seller_id:
            raise ConnectionError("NOT_FOUND", "资源不存在", http_status=404)
        try:
            plain = self._enc.decrypt(
                rec.nonce or b"",
                rec.ciphertext or b"",
                rec.tag or b"",
                rec.key_version,
            )
        except ValueError as exc:
            raise ConnectionError("NOT_FOUND", "资源不存在", http_status=404) from exc
        self._store.audit(
            seller_id=rec.seller_account_id,
            connection_id=connection_id,
            event_type="connection.unwrapped",
            request_id=request_id,
            payload={"purpose": purpose},
        )
        logger.info(
            "connection_unwrapped",
            extra={
                "connection_id": str(connection_id),
                "request_id": request_id,
                "purpose": purpose,
            },
        )
        return plain.decode("utf-8")
