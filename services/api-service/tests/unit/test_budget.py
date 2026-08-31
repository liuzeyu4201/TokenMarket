from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.domain.budget import (
    BudgetError,
    BudgetService,
    MemoryLedgerView,
    QuotaView,
    UsageRow,
)
from app.domain.budget.samples import SAMPLES


def test_hard_limit_concurrent_does_not_exceed() -> None:
    pid = uuid.uuid4()
    owner = uuid.uuid4()
    ledger = MemoryLedgerView()
    ledger.put(
        str(pid),
        QuotaView(available=500, reserved=0, settled=0, unresolved=0),
    )
    svc = BudgetService(ledger=ledger)
    svc.put_policy(
        project_id=pid,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        hard_minor=500,
        soft_minor=100,
    )
    accepted: list[int] = []

    def one(_i: int) -> None:
        try:
            rec = svc.admit(
                project_id=pid,
                owner_id=owner,
                role="buyer",
                workspace="buyer",
                amount_minor=50,
            )
            accepted.append(int(rec["amount_minor"]))
        except BudgetError as exc:
            if exc.code != "HARD_LIMIT":
                raise

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(one, range(100)))
    assert sum(accepted) == 500
    assert sum(accepted) <= 500


def test_soft_limit_warns_but_admits() -> None:
    pid = uuid.uuid4()
    owner = uuid.uuid4()
    ledger = MemoryLedgerView()
    ledger.put(str(pid), QuotaView(available=40, reserved=0, settled=20, unresolved=0))
    svc = BudgetService(ledger=ledger)
    svc.put_policy(
        project_id=pid,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        hard_minor=200,
        soft_minor=50,
    )
    ov = svc.overview(project_id=pid, owner_id=owner, role="buyer", workspace="buyer")
    assert ov["warning"] == "SOFT_LIMIT"
    rec = svc.admit(
        project_id=pid,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        amount_minor=10,
    )
    assert rec["admitted"] is True


def test_overview_unresolved_not_zero_and_matches_view() -> None:
    pid = uuid.uuid4()
    owner = uuid.uuid4()
    ledger = MemoryLedgerView()
    ledger.put(
        str(pid),
        QuotaView(
            available=890,
            reserved=0,
            settled=80,
            unresolved=30,
            requests=[
                UsageRow("ok", "k1", "consumed", 80),
                UsageRow("un", "k1", "unresolved", 30, reason="PARSE_FAILED"),
            ],
        ),
    )
    svc = BudgetService(ledger=ledger)
    ov = svc.overview(project_id=pid, owner_id=owner, role="buyer", workspace="buyer")
    assert ov["available"] == 890
    assert ov["settled"] == 80
    assert ov["unresolved"] == 30
    rows = svc.usage(
        project_id=pid,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        status="unresolved",
    )
    assert rows[0].request_id == "un"
    assert rows[0].amount_minor != 0
    assert rows[0].reason == "PARSE_FAILED"


def test_native_samples_are_protocol_specific() -> None:
    assert "Authorization: Bearer" in SAMPLES["openai"]["curl"]
    assert "/openai/v1/chat/completions" in SAMPLES["openai"]["path"]
    assert "x-api-key" in SAMPLES["anthropic"]["curl"]
    assert "anthropic-version" in SAMPLES["anthropic"]["curl"]
    assert "/anthropic/v1/messages" in SAMPLES["anthropic"]["path"]
    assert ":generateContent" in SAMPLES["vertex"]["path"]
    assert "chat.completions" not in SAMPLES["anthropic"]["curl"]
    assert "chat.completions" not in SAMPLES["vertex"]["curl"]


def test_guide_checklist_and_no_purchase_copy() -> None:
    pid = uuid.uuid4()
    owner = uuid.uuid4()
    svc = BudgetService(ledger=MemoryLedgerView())
    guide = svc.guide(project_id=pid, owner_id=owner, role="buyer", workspace="buyer")
    ids = [s["id"] for s in guide["checklist"]]  # type: ignore[index]
    assert ids == ["binding", "key", "sample", "result"]
    blob = str(guide).lower()
    assert "充值" not in str(guide)
    assert "提现" not in str(guide) or "不可" in guide["disclaimer"]  # type: ignore[index]
    assert "支付" not in blob
    assert "1:1" not in blob


def test_seller_forbidden() -> None:
    svc = BudgetService()
    with pytest.raises(BudgetError) as exc:
        svc.overview(
            project_id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            role="both",
            workspace="seller",
        )
    assert exc.value.code == "FORBIDDEN_ROLE"
