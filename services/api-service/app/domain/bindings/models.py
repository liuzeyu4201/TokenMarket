"""Binding records and ORM."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BindingRecord:
    binding_id: uuid.UUID
    project_id: uuid.UUID
    owner_account_id: uuid.UUID
    protocol: str
    supply_mode: str
    status: str
    version: int
    allowed_providers: list[str] = field(default_factory=list)
    allowed_models: list[str] = field(default_factory=list)
    allowed_regions: list[str] = field(default_factory=list)
    connection_id: uuid.UUID | None = None
    draining_connection_id: uuid.UUID | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProviderBindingRow(Base):
    __tablename__ = "provider_bindings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    protocol: Mapped[str] = mapped_column(String(16), nullable=False)
    supply_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allowed_providers: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    allowed_models: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    allowed_regions: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    draining_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ProviderBindingAuditRow(Base):
    __tablename__ = "provider_binding_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
