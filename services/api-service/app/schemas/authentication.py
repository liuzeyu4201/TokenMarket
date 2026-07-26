"""Phone authentication request/response DTOs (phone-auth-session v1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RequestChallengeRequest(BaseModel):
    """POST /verification-challenges body."""

    model_config = {"extra": "forbid"}

    phone: str = Field(min_length=1, max_length=32)


class CreateSessionRequest(BaseModel):
    """POST /sessions body.

    Format validation for the 6-digit ASCII OTP is performed by SessionService so
    malformed codes map to the contracted ``VALIDATION_ERROR`` envelope (not 422)
    and do not consume challenge attempts (FR-006a).
    """

    model_config = {"extra": "forbid"}

    challenge_id: UUID
    code: str = Field(min_length=1, max_length=32)


class ChallengeAcceptedData(BaseModel):
    model_config = {"extra": "forbid"}

    challenge_id: str
    phone_masked: str
    expires_at: datetime
    resend_available_at: datetime


class SessionData(BaseModel):
    model_config = {"extra": "forbid"}

    user_id: str
    nickname: str = Field(min_length=1, max_length=50)
    phone_masked: str
    role: Literal["buyer", "seller", "both"]
    expires_at: datetime
    csrf_token: str = Field(min_length=32, max_length=256)


class VerificationFailureData(BaseModel):
    model_config = {"extra": "forbid"}

    action: Literal["retry_code", "request_new_code"]
    attempts_remaining: int | None = Field(default=None, ge=0, le=4)


class RateLimitData(BaseModel):
    model_config = {"extra": "forbid"}

    retry_after_seconds: int = Field(ge=1)
