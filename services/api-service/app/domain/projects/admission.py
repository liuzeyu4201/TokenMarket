"""Proxy admission derived from Project facts (no cache)."""

from __future__ import annotations

from app.domain.projects.models import ProjectRecord


def allows_new_proxy(rec: ProjectRecord) -> bool:
    """True only for live active Projects. Archive/suspend/delete fail closed."""
    return rec.deleted_at is None and rec.status == "active"
