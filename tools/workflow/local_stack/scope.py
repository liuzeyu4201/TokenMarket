"""Parse and validate the optional ``scope=`` selector for start/stop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

VALID_SCOPES: Final[frozenset[str]] = frozenset({"all", "apps"})
DEFAULT_SCOPE: Final[str] = "all"


class LocalScopeError(Exception):
    """Invalid scope selector."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class LocalScope:
    """Resolved local start/stop scope."""

    value: str

    @property
    def wants_stack(self) -> bool:
        return self.value == "all"

    @property
    def wants_process(self) -> bool:
        return self.value in ("all", "apps")


def parse_local_scope(raw: str | None) -> LocalScope:
    """Return scope; empty/None defaults to ``all``."""
    if raw is None or str(raw).strip() == "":
        return LocalScope(DEFAULT_SCOPE)
    value = str(raw).strip().lower()
    if value not in VALID_SCOPES:
        raise LocalScopeError(
            "INVALID_CONFIG",
            f"scope= must be all or apps (got {raw!r}); " "default is all when omitted",
        )
    return LocalScope(value)
