"""Port for SF06 credential validation (no HTTP in domain)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ValidationSnapshot:
    error_category: str
    remaining_quota: str | None = None
    quota_unit: str | None = None
    validity: str = "unknown"


class CredentialValidator(Protocol):
    def validate(
        self, *, platform: str, api_key: str, request_id: str
    ) -> ValidationSnapshot: ...
