"""Register request/response DTOs aligned with OpenAPI user-registration v1."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """Client registration body. Client must not send user id or status."""

    model_config = {"extra": "forbid"}

    phone: str = Field(min_length=1, max_length=32)
    nickname: str = Field(min_length=1, max_length=50)
    role: Literal["buyer", "seller", "both"]


class RegisterSuccessData(BaseModel):
    user_id: str
    role: Literal["buyer", "seller", "both"]
    status: Literal["active"] = "active"
    created_at: datetime
    phone_masked: str | None = None
