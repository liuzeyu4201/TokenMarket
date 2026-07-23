"""Unified business response envelope (user-registration contract)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseResponse(BaseModel, Generic[T]):
    """Versioned business envelope: code/message/data/request_id/timestamp."""

    code: str = Field(default="0", description="Business status code; 0 means success")
    message: str = Field(default="success")
    data: Optional[T] = None
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=utc_now)


class ErrorData(BaseModel):
    """Optional error payload (field errors or safe diagnostics)."""

    errors: Optional[dict[str, list[str]]] = None


def success_envelope(
    data: Any,
    *,
    request_id: str,
    message: str = "success",
) -> dict[str, Any]:
    return {
        "code": "0",
        "message": message,
        "data": data,
        "request_id": request_id,
        "timestamp": utc_now().isoformat(),
    }


def error_envelope(
    code: str,
    message: str,
    *,
    request_id: str,
    data: Any = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id,
        "timestamp": utc_now().isoformat(),
    }
