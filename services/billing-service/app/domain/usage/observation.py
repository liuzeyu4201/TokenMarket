"""Usage observation envelope (usage/v1.1). Unknown cost must not be stored as 0."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CostStatus = Literal["reported", "rated", "unresolved"]
Settlement = Literal["reported", "usage", "unresolved", "none"]


class UsageDims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    image_units: int | None = None
    audio_ms: int | None = None
    duration_ms: int | None = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    provider: Literal["openai", "anthropic", "vertex"]
    endpoint_id: str = Field(min_length=1)
    cost_status: CostStatus
    usage: UsageDims
    settlement_basis: Settlement | None = None
    reported_cost_minor_units: int | None = Field(default=None, ge=0)
    currency: str | None = None
    cost_scale: int | None = Field(default=6, ge=0, le=9)
    parser_version: str | None = None
    evidence_digest: str | None = None
    unresolved_reason: str | None = None
    integrity: Literal["complete", "partial", "failed"] | None = None
    dual_present: bool | None = None
    metering_source: (
        Literal["usage", "mixed", "reported_cost", "none", "unresolved"] | None
    ) = None

    @model_validator(mode="after")
    def unknown_cost_is_not_zero(self) -> Observation:
        if (
            self.cost_status == "unresolved"
            and self.reported_cost_minor_units is not None
        ):
            raise ValueError("unresolved must not carry a reported cost")
        if self.cost_status == "reported" and self.reported_cost_minor_units is None:
            raise ValueError("reported requires reported_cost_minor_units")
        return self
