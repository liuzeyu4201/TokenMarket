from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.ledger.errors import IMMUTABLE_ENTRY, LedgerError
from app.domain.ledger.models import Entry
from app.domain.ledger.store import MemoryLedgerStore


def test_ledger_mutate_and_delete_rejected() -> None:
    store = MemoryLedgerStore()
    entry = Entry(
        entry_id="e1",
        journal_id="j1",
        account_id="buyer_quota:a",
        account_kind="buyer_quota",
        request_id="r1",
        amount_minor_units=10,
        direction="debit",
        status="unresolved",
        rate_version="1",
        created_at=datetime.now(timezone.utc),
    )
    store.append(entry)
    rows = store.list_entries()
    assert rows[0].status == "unresolved"
    assert rows[0].amount_minor_units != 0
    with pytest.raises(LedgerError) as mut:
        store.mutate_entry("e1")
    assert mut.value.code == IMMUTABLE_ENTRY
    with pytest.raises(LedgerError) as deleted:
        store.delete_entry("e1")
    assert deleted.value.code == IMMUTABLE_ENTRY
    assert len(store.list_entries()) == 1
