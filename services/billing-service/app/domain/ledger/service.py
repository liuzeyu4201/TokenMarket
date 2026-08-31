"""Test-quota reserve, sync settle, release, unresolved, and reverse."""

from __future__ import annotations

import uuid

from app.domain.ledger.errors import (
    ALREADY_TERMINAL,
    IDEMPOTENCY_CONFLICT,
    INSUFFICIENT_QUOTA,
    MSG,
    NOT_FOUND,
    UNBALANCED,
    VALIDATION,
    LedgerError,
)
from app.domain.ledger.models import (
    UNIT,
    AccountKind,
    Balance,
    Direction,
    Entry,
    EntryStatus,
    Journal,
    Reservation,
    account_id_for,
    utcnow,
)
from app.domain.ledger.store import LedgerStore, MemoryLedgerStore


def _new_id() -> str:
    return str(uuid.uuid4())


class LedgerService:
    def __init__(self, store: LedgerStore | None = None) -> None:
        self._store: LedgerStore = store if store is not None else MemoryLedgerStore()

    def seed_quota(
        self,
        *,
        account_id: str,
        project_id: str,
        key_id: str,
        account_grant: int,
        project_grant: int,
        key_grant: int,
        request_id: str = "seed",
        rate_version: str = "seed",
    ) -> None:
        if min(account_grant, project_grant, key_grant) < 0:
            raise LedgerError(VALIDATION, MSG[VALIDATION], http_status=400)
        journal = _new_id()
        self._credit(
            journal_id=journal,
            request_id=request_id,
            account_id=account_id_for("buyer_quota", account_id),
            kind="buyer_quota",
            amount=account_grant,
            status="settled",
            rate_version=rate_version,
            project_id=project_id,
            key_id=key_id,
        )
        self._credit(
            journal_id=journal,
            request_id=request_id,
            account_id=account_id_for("project_quota", project_id),
            kind="project_quota",
            amount=project_grant,
            status="settled",
            rate_version=rate_version,
            project_id=project_id,
            key_id=key_id,
        )
        self._credit(
            journal_id=journal,
            request_id=request_id,
            account_id=account_id_for("key_quota", key_id),
            kind="key_quota",
            amount=key_grant,
            status="settled",
            rate_version=rate_version,
            project_id=project_id,
            key_id=key_id,
        )

    def reserve(
        self,
        *,
        request_id: str,
        idempotency_key: str,
        account_id: str,
        project_id: str,
        key_id: str,
        amount_minor: int,
        rate_version: str,
    ) -> Reservation:
        if amount_minor <= 0 or not request_id or not idempotency_key:
            raise LedgerError(VALIDATION, MSG[VALIDATION], http_status=400)
        existing = self._store.get_reservation(request_id)
        by_key = self._store.get_by_idempotency(idempotency_key)
        if existing is not None:
            if existing.idempotency_key != idempotency_key:
                raise LedgerError(IDEMPOTENCY_CONFLICT, MSG[IDEMPOTENCY_CONFLICT])
            if existing.amount_minor != amount_minor:
                raise LedgerError(IDEMPOTENCY_CONFLICT, MSG[IDEMPOTENCY_CONFLICT])
            return existing
        if by_key is not None:
            if by_key.request_id != request_id or by_key.amount_minor != amount_minor:
                raise LedgerError(IDEMPOTENCY_CONFLICT, MSG[IDEMPOTENCY_CONFLICT])
            return by_key
        buckets = self._buyer_buckets(account_id, project_id, key_id)
        lock = getattr(self._store, "locked", None)
        ctx = lock() if callable(lock) else None
        if ctx is not None:
            ctx.acquire()
        try:
            # Re-check under lock
            existing = self._store.get_reservation(request_id)
            if existing is not None:
                return existing
            for acc, _kind in buckets:
                if self.rebuild(acc).available < amount_minor:
                    raise LedgerError(INSUFFICIENT_QUOTA, MSG[INSUFFICIENT_QUOTA])
            journal = _new_id()
            for acc, kind in buckets:
                self._debit(
                    journal_id=journal,
                    request_id=request_id,
                    account_id=acc,
                    kind=kind,
                    amount=amount_minor,
                    status="reserved",
                    rate_version=rate_version,
                    project_id=project_id,
                    key_id=key_id,
                    idempotency_key=idempotency_key,
                )
            rec = Reservation(
                reservation_id=_new_id(),
                request_id=request_id,
                idempotency_key=idempotency_key,
                account_id=account_id,
                project_id=project_id,
                key_id=key_id,
                amount_minor=amount_minor,
                remaining_minor=amount_minor,
                status="held",
                rate_version=rate_version,
                journal_id=journal,
                created_at=utcnow(),
            )
            self._store.put_reservation(rec)
            return rec
        finally:
            if ctx is not None:
                ctx.release()

    def settle(
        self,
        *,
        request_id: str,
        buyer_debit: int,
        seller_earning: int,
        spread: int,
        seller_id: str,
        rate_version: str,
        evidence_digest: str = "",
    ) -> Journal:
        if buyer_debit != seller_earning + spread:
            raise LedgerError(UNBALANCED, MSG[UNBALANCED])
        if min(buyer_debit, seller_earning, spread) < 0:
            raise LedgerError(VALIDATION, MSG[VALIDATION], http_status=400)
        rec = self._require_res(request_id)
        if rec.status == "consumed":
            return Journal(journal_id=rec.journal_id, request_id=request_id)
        if rec.status in ("released", "unresolved"):
            raise LedgerError(ALREADY_TERMINAL, MSG[ALREADY_TERMINAL])
        lock = getattr(self._store, "locked", None)
        ctx = lock() if callable(lock) else None
        if ctx is not None:
            ctx.acquire()
        try:
            rec = self._require_res(request_id)
            if rec.status == "consumed":
                return Journal(journal_id=rec.journal_id, request_id=request_id)
            journal = _new_id()
            buckets = self._buyer_buckets(rec.account_id, rec.project_id, rec.key_id)
            # Release the full hold, then post settled buyer debit.
            for acc, kind in buckets:
                self._credit(
                    journal_id=journal,
                    request_id=request_id,
                    account_id=acc,
                    kind=kind,
                    amount=rec.amount_minor,
                    status="released",
                    rate_version=rate_version,
                    project_id=rec.project_id,
                    key_id=rec.key_id,
                    evidence_digest=evidence_digest,
                )
                self._debit(
                    journal_id=journal,
                    request_id=request_id,
                    account_id=acc,
                    kind=kind,
                    amount=buyer_debit,
                    status="settled",
                    rate_version=rate_version,
                    project_id=rec.project_id,
                    key_id=rec.key_id,
                    evidence_digest=evidence_digest,
                )
            self._credit(
                journal_id=journal,
                request_id=request_id,
                account_id=account_id_for("seller_earning", seller_id),
                kind="seller_earning",
                amount=seller_earning,
                status="settled",
                rate_version=rate_version,
                evidence_digest=evidence_digest,
            )
            self._credit(
                journal_id=journal,
                request_id=request_id,
                account_id=account_id_for("platform_spread", "platform"),
                kind="platform_spread",
                amount=spread,
                status="settled",
                rate_version=rate_version,
                evidence_digest=evidence_digest,
            )
            rec.status = "consumed"
            rec.remaining_minor = max(0, rec.amount_minor - buyer_debit)
            rec.journal_id = journal
            rec.rate_version = rate_version
            self._store.save_reservation(rec)
            ids = [
                e.entry_id
                for e in self._store.list_entries()
                if e.journal_id == journal
            ]
            return Journal(journal_id=journal, request_id=request_id, entry_ids=ids)
        finally:
            if ctx is not None:
                ctx.release()

    def release(self, *, request_id: str) -> Reservation:
        rec = self._require_res(request_id)
        if rec.status == "released":
            return rec
        if rec.status != "held":
            raise LedgerError(ALREADY_TERMINAL, MSG[ALREADY_TERMINAL])
        journal = _new_id()
        for acc, kind in self._buyer_buckets(
            rec.account_id, rec.project_id, rec.key_id
        ):
            self._credit(
                journal_id=journal,
                request_id=request_id,
                account_id=acc,
                kind=kind,
                amount=rec.amount_minor,
                status="released",
                rate_version=rec.rate_version,
                project_id=rec.project_id,
                key_id=rec.key_id,
            )
        rec.status = "released"
        rec.remaining_minor = 0
        rec.journal_id = journal
        self._store.save_reservation(rec)
        return rec

    def mark_unresolved(self, *, request_id: str, reason: str) -> Reservation:
        rec = self._require_res(request_id)
        if rec.status == "unresolved":
            return rec
        if rec.status != "held":
            raise LedgerError(ALREADY_TERMINAL, MSG[ALREADY_TERMINAL])
        rec.status = "unresolved"
        rec.unresolved_reason = reason or "unknown_cost"
        self._store.save_reservation(rec)
        return rec

    def reverse(self, *, request_id: str, reason: str = "reverse") -> Journal:
        _ = reason
        rec = self._require_res(request_id)
        if rec.status != "consumed":
            raise LedgerError(ALREADY_TERMINAL, MSG[ALREADY_TERMINAL])
        settled = [
            e
            for e in self._store.list_entries()
            if e.request_id == request_id and e.status == "settled"
        ]
        if not settled:
            raise LedgerError(NOT_FOUND, MSG[NOT_FOUND])
        journal = _new_id()
        for e in settled:
            opp: Direction = "credit" if e.direction == "debit" else "debit"
            self._post(
                journal_id=journal,
                request_id=request_id,
                account_id=e.account_id,
                kind=e.account_kind,
                amount=e.amount_minor_units,
                direction=opp,
                status="reversed",
                rate_version=e.rate_version,
                project_id=e.project_id,
                key_id=e.key_id,
                evidence_digest=e.evidence_digest,
                reverses_entry_id=e.entry_id,
            )
        rec.status = "released"
        rec.remaining_minor = 0
        rec.journal_id = journal
        self._store.save_reservation(rec)
        return Journal(journal_id=journal, request_id=request_id)

    def projection(self, account_id: str) -> Balance:
        return self.rebuild(account_id)

    def rebuild(self, account_id: str) -> Balance:
        reserved = 0
        released = 0
        settled_debit = 0
        settled_credit = 0
        reversed_debit = 0
        reversed_credit = 0
        for e in self._store.entries_for(account_id):
            if e.status == "reserved" and e.direction == "debit":
                reserved += e.amount_minor_units
            elif e.status == "released" and e.direction == "credit":
                released += e.amount_minor_units
            elif e.status == "settled" and e.direction == "debit":
                settled_debit += e.amount_minor_units
            elif e.status == "settled" and e.direction == "credit":
                settled_credit += e.amount_minor_units
            elif e.status == "reversed" and e.direction == "debit":
                reversed_debit += e.amount_minor_units
            elif e.status == "reversed" and e.direction == "credit":
                reversed_credit += e.amount_minor_units
        outstanding = reserved - released
        available = (
            settled_credit
            - settled_debit
            - outstanding
            + reversed_credit
            - reversed_debit
        )
        return Balance(
            account_id=account_id,
            available=available,
            reserved=max(0, outstanding),
            settled_debit=settled_debit,
            settled_credit=settled_credit,
        )

    def entries(self) -> list[Entry]:
        return self._store.list_entries()

    def mutate_entry(self, entry_id: str) -> None:
        self._store.mutate_entry(entry_id)

    def delete_entry(self, entry_id: str) -> None:
        self._store.delete_entry(entry_id)

    def _require_res(self, request_id: str) -> Reservation:
        rec = self._store.get_reservation(request_id)
        if rec is None:
            raise LedgerError(NOT_FOUND, MSG[NOT_FOUND], http_status=404)
        return rec

    def _buyer_buckets(
        self, account_id: str, project_id: str, key_id: str
    ) -> list[tuple[str, AccountKind]]:
        return [
            (account_id_for("buyer_quota", account_id), "buyer_quota"),
            (account_id_for("project_quota", project_id), "project_quota"),
            (account_id_for("key_quota", key_id), "key_quota"),
        ]

    def _credit(self, **kwargs: object) -> None:
        self._post(direction="credit", **kwargs)  # type: ignore[arg-type]

    def _debit(self, **kwargs: object) -> None:
        self._post(direction="debit", **kwargs)  # type: ignore[arg-type]

    def _post(
        self,
        *,
        journal_id: str,
        request_id: str,
        account_id: str,
        kind: AccountKind,
        amount: int,
        direction: Direction,
        status: EntryStatus,
        rate_version: str,
        project_id: str | None = None,
        key_id: str | None = None,
        evidence_digest: str | None = None,
        idempotency_key: str | None = None,
        reverses_entry_id: str | None = None,
    ) -> None:
        if amount < 0:
            raise LedgerError(VALIDATION, MSG[VALIDATION], http_status=400)
        entry = Entry(
            entry_id=_new_id(),
            journal_id=journal_id,
            account_id=account_id,
            account_kind=kind,
            request_id=request_id,
            amount_minor_units=amount,
            direction=direction,
            status=status,
            rate_version=rate_version,
            created_at=utcnow(),
            project_id=project_id,
            key_id=key_id,
            evidence_digest=evidence_digest,
            idempotency_key=idempotency_key,
            reverses_entry_id=reverses_entry_id,
            unit=UNIT,
        )
        self._store.append(entry)
