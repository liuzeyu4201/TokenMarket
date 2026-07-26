"""Shared SQLAlchemy declarative base for API Service domain models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root metadata for all API Service ORM models."""

    pass
