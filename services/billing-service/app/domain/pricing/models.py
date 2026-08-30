from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

Status = Literal["draft", "previewed", "approved", "published", "superseded"]


@dataclass(frozen=True)
class RateRow:
    provider: str
    dimension: str
    rate_minor_units: int
    unit: str = "token"
    currency: str = "USD"
    protocol: str = ""
    model: str = "*"
    endpoint_id: str = "*"
    region: str = "*"
    valid_from: str | None = None
    valid_to: str | None = None

    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.provider,
            self.model,
            self.endpoint_id,
            self.dimension,
            self.region,
        )


@dataclass
class RateVersion:
    version_id: str
    buyer_multiplier_bps: int
    seller_quote_min_bps: int
    seller_quote_max_bps: int
    rows: list[RateRow] = field(default_factory=list)
    status: Status = "draft"
    scale: int = 6
    currency: str = "USD"

    def seller_view(self, seller_bps: int) -> dict[str, Any]:
        return {
            "rate_version": self.version_id,
            "status": self.status,
            "seller_quote_min_bps": self.seller_quote_min_bps,
            "seller_quote_max_bps": self.seller_quote_max_bps,
            "own_multiplier_bps": seller_bps,
            "currency": self.currency,
            "scale": self.scale,
        }

    def buyer_view(self) -> dict[str, Any]:
        return {
            "rate_version": self.version_id,
            "status": self.status,
            "buyer_multiplier_bps": self.buyer_multiplier_bps,
            "currency": self.currency,
            "scale": self.scale,
        }

    def admin_view(self) -> dict[str, Any]:
        return {
            "rate_version": self.version_id,
            "status": self.status,
            "buyer_multiplier_bps": self.buyer_multiplier_bps,
            "seller_quote_min_bps": self.seller_quote_min_bps,
            "seller_quote_max_bps": self.seller_quote_max_bps,
            "rows": [r.__dict__ for r in self.rows],
            "currency": self.currency,
            "scale": self.scale,
        }


@dataclass(frozen=True)
class SellerQuote:
    seller_id: str
    rate_version: str
    multiplier_bps: int


@dataclass(frozen=True)
class PriceLock:
    request_id: str
    rate_version: str
    buyer_bps: int
    seller_bps: int


@dataclass(frozen=True)
class UsageInput:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    image_units: int | None = None
    audio_ms: int | None = None
    duration_ms: int | None = None

    def as_map(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "image_units",
            "audio_ms",
            "duration_ms",
        ):
            val = getattr(self, name)
            if val is not None:
                out[name] = int(val)
        return out


@dataclass(frozen=True)
class QuoteResult:
    status: str
    base_minor: int | None
    buyer_debit: int | None
    seller_earning: int | None
    spread: int | None
    usage_base_minor: int | None = None
    variance_minor: int | None = None
    unresolved_reason: str | None = None


def copy_version(v: RateVersion, **changes: Any) -> RateVersion:
    return replace(v, **changes)
