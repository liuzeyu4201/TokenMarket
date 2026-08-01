"""Pydantic DTOs for authorization evaluate / fixtures / route exclude."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

ActionLiteral = Literal[
    "proxy_key.create",
    "proxy_key.revoke",
    "proxy_key.use",
    "seller_key.register",
    "seller_key.read",
    "seller_key.update",
    "seller_key.disable",
    "route_candidate_exclude_self",
]

ResourceTypeLiteral = Literal["proxy_key", "seller_key"]
LifecycleLiteral = Literal["active", "disabled", "soft_deleted"]


class EvaluateRequest(BaseModel):
    action: ActionLiteral
    resource_type: ResourceTypeLiteral | None = None
    resource_id: UUID | None = None
    # Accepted only to prove ignore behavior in tests
    user_id: UUID | None = None
    role: str | None = None


class RouteCandidateIn(BaseModel):
    resource_id: UUID
    owner_user_id: UUID
    lifecycle_status: LifecycleLiteral


class RouteExcludeRequest(BaseModel):
    candidates: list[RouteCandidateIn] = Field(default_factory=list)


class FixtureCreateResourceRequest(BaseModel):
    resource_type: ResourceTypeLiteral
    action: Literal["proxy_key.create", "seller_key.register"]
    resource_id: UUID | None = None


class FixturePatchResourceRequest(BaseModel):
    action: Literal[
        "proxy_key.revoke",
        "seller_key.update",
        "seller_key.disable",
    ]
    lifecycle_status: LifecycleLiteral | None = None
