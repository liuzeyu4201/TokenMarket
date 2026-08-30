"""Provider Binding lookup port. SF11 supplies a real implementation."""

from __future__ import annotations

import uuid
from typing import Protocol


class BindingLookup(Protocol):
    def has_enabled_binding(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        protocol: str,
    ) -> bool: ...


class EmptyBindingLookup:
    """SF10 default: no Binding rows exist yet."""

    def has_enabled_binding(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        protocol: str,
    ) -> bool:
        return False


class DictBindingLookup:
    """Test double used until SF11 persists Binding rows."""

    def __init__(self) -> None:
        self._ok: set[tuple[uuid.UUID, uuid.UUID, str]] = set()

    def grant(self, owner_id: uuid.UUID, project_id: uuid.UUID, protocol: str) -> None:
        self._ok.add((owner_id, project_id, protocol))

    def has_enabled_binding(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        protocol: str,
    ) -> bool:
        return (owner_id, project_id, protocol) in self._ok
