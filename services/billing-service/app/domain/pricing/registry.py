from __future__ import annotations

import threading

from app.domain.pricing.errors import PricingError
from app.domain.pricing.models import PriceLock, RateRow, RateVersion, SellerQuote
from app.domain.pricing.quote import row_conflicts


class Registry:
    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._versions: dict[str, RateVersion] = {}
        self._quotes: dict[tuple[str, str], SellerQuote] = {}
        self._published: str | None = None
        self._locks: dict[str, PriceLock] = {}

    def create(self, version: RateVersion) -> None:
        with self._mu:
            if version.version_id in self._versions:
                raise PricingError("conflict")
            version.status = "draft"
            self._versions[version.version_id] = version

    def get(self, version_id: str) -> RateVersion:
        with self._mu:
            v = self._versions.get(version_id)
            if v is None:
                raise PricingError("not_found")
            return v

    def add_row(self, version_id: str, row: RateRow) -> None:
        with self._mu:
            v = self._require_mutable(version_id)
            v.rows.append(row)

    def set_quote(self, quote: SellerQuote) -> None:
        with self._mu:
            v = self._versions.get(quote.rate_version)
            if v is None:
                raise PricingError("not_found")
            if not (
                v.seller_quote_min_bps <= quote.multiplier_bps <= v.seller_quote_max_bps
            ):
                raise PricingError("quote_out_of_bounds")
            self._quotes[(quote.seller_id, quote.rate_version)] = quote

    def preview(self, version_id: str) -> None:
        with self._mu:
            v = self._require_mutable(version_id)
            self._validate(v)
            v.status = "previewed"

    def approve(self, version_id: str) -> None:
        with self._mu:
            v = self._require_mutable(version_id)
            if v.status not in {"previewed", "draft"}:
                raise PricingError("invalid_status")
            self._validate(v)
            v.status = "approved"

    def publish(self, version_id: str) -> None:
        with self._mu:
            v = self._versions.get(version_id)
            if v is None:
                raise PricingError("not_found")
            if v.status == "published":
                return
            self._validate(v)
            if self._published and self._published != version_id:
                old = self._versions[self._published]
                old.status = "superseded"
            v.status = "published"
            self._published = version_id

    def delete_version(self, version_id: str) -> None:
        with self._mu:
            v = self._versions.get(version_id)
            if v is None:
                raise PricingError("not_found")
            if v.status in {"published", "superseded"}:
                raise PricingError("immutable")
            del self._versions[version_id]

    def lock(self, request_id: str, seller_id: str) -> PriceLock:
        with self._mu:
            if request_id in self._locks:
                return self._locks[request_id]
            if not self._published:
                raise PricingError("no_published")
            v = self._versions[self._published]
            q = self._quotes.get((seller_id, v.version_id))
            if q is None:
                raise PricingError("no_quote")
            snap = PriceLock(
                request_id=request_id,
                rate_version=v.version_id,
                buyer_bps=v.buyer_multiplier_bps,
                seller_bps=q.multiplier_bps,
            )
            self._locks[request_id] = snap
            return snap

    def _require_mutable(self, version_id: str) -> RateVersion:
        v = self._versions.get(version_id)
        if v is None:
            raise PricingError("not_found")
        if v.status in {"published", "superseded"}:
            raise PricingError("immutable")
        return v

    def _validate(self, v: RateVersion) -> None:
        if v.seller_quote_min_bps > v.seller_quote_max_bps:
            raise PricingError("invalid_bounds")
        if v.buyer_multiplier_bps < v.seller_quote_max_bps:
            raise PricingError("negative_spread")
        code = row_conflicts(v.rows)
        if code:
            raise PricingError(code)
