from __future__ import annotations

from app.domain.pricing.models import (
    PriceLock,
    QuoteResult,
    RateRow,
    RateVersion,
    UsageInput,
)

BPS = 10_000


def mul_bps(amount: int, bps: int) -> int:
    if amount < 0 or bps < 0:
        raise ValueError("negative")
    return (amount * bps + BPS // 2) // BPS


def _windows_overlap(a: RateRow, b: RateRow) -> bool:
    start_a = a.valid_from or ""
    start_b = b.valid_from or ""
    end_a = a.valid_to or "\uffff"
    end_b = b.valid_to or "\uffff"
    return start_a < end_b and start_b < end_a


def row_conflicts(rows: list[RateRow]) -> str | None:
    n = len(rows)
    for i in range(n):
        for j in range(i + 1, n):
            if rows[i].key() != rows[j].key():
                continue
            if not _windows_overlap(rows[i], rows[j]):
                continue
            if rows[i].unit != rows[j].unit or rows[i].currency != rows[j].currency:
                return "unit_conflict"
            return "overlap"
    return None


def _usage_base(usage: UsageInput, version: RateVersion) -> int | None:
    dims = usage.as_map()
    if not dims:
        return None
    total = 0
    matched_any = False
    for dim, count in dims.items():
        if dim == "total_tokens":
            continue
        row = _best_row(version, dim)
        if row is None:
            if count:
                return None
            continue
        matched_any = True
        total += count * row.rate_minor_units
    if not matched_any:
        return None
    return total


def _best_row(version: RateVersion, dimension: str) -> RateRow | None:
    candidates = [r for r in version.rows if r.dimension == dimension]
    if not candidates:
        return None

    def score(r: RateRow) -> tuple[int, int]:
        spec_ep = 0 if r.endpoint_id in {"", "*"} else 1
        spec_model = 0 if r.model in {"", "*"} else 1
        return (spec_ep, spec_model)

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def quote(
    usage: UsageInput,
    version: RateVersion,
    lock: PriceLock,
    reported_minor: int | None,
) -> QuoteResult:
    usage_base = _usage_base(usage, version)
    if reported_minor is not None:
        base = reported_minor
        status = "reported"
    elif usage_base is not None:
        base = usage_base
        status = "rated"
    else:
        return QuoteResult(
            status="unresolved",
            base_minor=None,
            buyer_debit=None,
            seller_earning=None,
            spread=None,
            usage_base_minor=usage_base,
            unresolved_reason="missing_rate",
        )
    try:
        debit = mul_bps(base, lock.buyer_bps)
        earn = mul_bps(base, lock.seller_bps)
    except (ValueError, OverflowError):
        return QuoteResult(
            status="unresolved",
            base_minor=None,
            buyer_debit=None,
            seller_earning=None,
            spread=None,
            unresolved_reason="overflow",
        )
    spread = debit - earn
    variance = None
    if reported_minor is not None and usage_base is not None:
        variance = usage_base - reported_minor
    return QuoteResult(
        status=status,
        base_minor=base,
        buyer_debit=debit,
        seller_earning=earn,
        spread=spread,
        usage_base_minor=usage_base,
        variance_minor=variance,
    )
