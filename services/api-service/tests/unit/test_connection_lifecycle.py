"""Supply-mode lifecycle transitions, pause, blockers, pool isolation."""

from __future__ import annotations

import time
import uuid

import pytest

from app.domain.bindings.ports import AlwaysPriceLookup, ConnectionFact
from app.domain.bindings.service import BindingError, BindingService
from app.domain.bindings.store import MemoryBindingStore
from app.domain.connections.health import HealthService, ProbeOutcome, ScriptedProbe
from app.domain.connections.lifecycle import (
    LifecycleService,
    ScriptedDependencies,
    admits_new,
    transition,
)
from app.domain.connections.service import ConnectionError, ConnectionService
from app.domain.connections.store import MemoryConnectionStore
from app.domain.projects.store import MemoryProjectStore
from app.domain.sellerkeys.crypto import CredentialEncryptor

SECRET = "sk-life-ok-credential"
CATALOG = {
    "catalog_major": 1,
    "records": [
        {
            "provider": "openai",
            "stability": "stable",
            "path_template": "/v1/chat/completions",
            "capability_tags": [],
        }
    ],
}


def _enc() -> CredentialEncryptor:
    return CredentialEncryptor(b"k" * 32, "v1")


def _stack(deps=None):
    store = MemoryConnectionStore()
    conn = ConnectionService(
        _enc(),
        b"f" * 32,
        store=store,
        resolver=lambda _h, _p: ["1.1.1.1"],
    )
    probe = ScriptedProbe()
    probe.by_secret[SECRET] = ProbeOutcome(
        "ok",
        [{"path_template": "/v1/chat/completions", "model": "gpt-test"}],
    )
    health = HealthService(conn, probe, catalog=CATALOG)
    life = LifecycleService(conn, dependencies=deps or ScriptedDependencies())
    return conn, health, life, store


def _verified(conn, health, life, mode="shared"):
    rec = conn.create(
        seller_id=uuid.uuid4(),
        provider="openai",
        supply_mode=mode,
        secret=SECRET,
        role="seller",
        workspace="seller",
        request_id="c",
    )
    health.verify(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="v",
    )
    rec = conn.get(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
    )
    return rec


def test_transition_matrix_legal_and_illegal() -> None:
    assert transition("draft", "verified") == "verified"
    assert transition("verified", "listed") == "listed"
    assert transition("listed", "paused") == "paused"
    with pytest.raises(ConnectionError) as exc:
        transition("listed", "retired")
    assert exc.value.code == "ILLEGAL_STATE_TRANSITION"
    with pytest.raises(ConnectionError):
        transition("draining", "listed")


def test_list_locks_mode() -> None:
    conn, health, life, _ = _stack()
    rec = _verified(conn, health, life)
    listed = life.list_supply(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="l",
    )
    assert listed.lifecycle_state == "listed"
    with pytest.raises(ConnectionError) as exc:
        life.set_mode(
            connection_id=rec.connection_id,
            seller_id=rec.seller_account_id,
            supply_mode="dedicated",
            role="seller",
            workspace="seller",
            request_id="m",
        )
    assert exc.value.code == "MODE_LOCKED"
    draft = conn.create(
        seller_id=uuid.uuid4(),
        provider="openai",
        supply_mode="shared",
        secret=SECRET,
        role="seller",
        workspace="seller",
        request_id="d",
    )
    changed = life.set_mode(
        connection_id=draft.connection_id,
        seller_id=draft.seller_account_id,
        supply_mode="dedicated",
        role="seller",
        workspace="seller",
        request_id="ok",
    )
    assert changed.supply_mode == "dedicated"


def test_pause_blocks_new_routing_within_one_second() -> None:
    conn, health, life, store = _stack()
    rec = _verified(conn, health, life)
    life.list_supply(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="l",
    )
    rec = store.get(rec.connection_id)
    assert rec is not None
    assert admits_new(rec) is True
    start = time.monotonic()
    life.pause(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="p",
    )
    assert time.monotonic() - start < 1.0
    rec = store.get(rec.connection_id)
    assert rec is not None
    assert admits_new(rec) is False
    fact = conn.get_fact(rec.connection_id)
    assert fact is not None
    assert fact.admits_new is False


def test_delete_blockers() -> None:
    deps = ScriptedDependencies()
    conn, health, life, _ = _stack(deps)
    rec = _verified(conn, health, life)
    listed = life.list_supply(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="l",
    )
    with pytest.raises(ConnectionError) as listed_del:
        life.ensure_deletable(listed.connection_id)
    assert listed_del.value.code == "ILLEGAL_STATE"
    deps.by_id[rec.connection_id] = [{"code": "IN_FLIGHT", "detail": "req"}]
    with pytest.raises(ConnectionError) as inflight:
        life.retire(
            connection_id=rec.connection_id,
            seller_id=rec.seller_account_id,
            role="seller",
            workspace="seller",
            request_id="r",
        )
    assert inflight.value.code == "IN_FLIGHT"
    assert inflight.value.data["blockers"][0]["code"] == "IN_FLIGHT"


def test_shared_pool_excludes_dedicated() -> None:
    conn, health, life, _ = _stack()
    shared = _verified(conn, health, life, mode="shared")
    dedicated = _verified(conn, health, life, mode="dedicated")
    for rec in (shared, dedicated):
        life.list_supply(
            connection_id=rec.connection_id,
            seller_id=rec.seller_account_id,
            role="seller",
            workspace="seller",
            request_id="l",
        )
    pool = life.list_routable("shared")
    ids = {r.connection_id for r in pool}
    assert shared.connection_id in ids
    assert dedicated.connection_id not in ids
    ded = life.list_routable("dedicated")
    dids = {r.connection_id for r in ded}
    assert dedicated.connection_id in dids
    assert shared.connection_id not in dids


def test_dedicated_dual_bind_rejected() -> None:
    store = MemoryBindingStore()
    cid = uuid.uuid4()
    proj = MemoryProjectStore()
    bind = BindingService(
        store=store,
        projects=proj,
        prices=AlwaysPriceLookup(),
    )
    from app.domain.projects.service import ProjectService as ProjectSvc

    projects = ProjectSvc(store=proj, binding=bind)
    o1 = uuid.uuid4()
    a = projects.create(
        owner_id=o1,
        display_name="A",
        mode="dedicated",
        enabled_protocols=["openai"],
        role="buyer",
        workspace="buyer",
        request_id="p1",
    )
    o2 = uuid.uuid4()
    b = projects.create(
        owner_id=o2,
        display_name="B",
        mode="dedicated",
        enabled_protocols=["openai"],
        role="buyer",
        workspace="buyer",
        request_id="p2",
    )

    class L:
        def get(self, connection_id):
            return ConnectionFact(
                connection_id=cid,
                provider="openai",
                supply_mode="dedicated",
                usable=True,
            )

    bind._connections = L()
    d1 = bind.create(
        project_id=a.project_id,
        owner_id=o1,
        protocol="openai",
        supply_mode="dedicated",
        role="buyer",
        workspace="buyer",
        request_id="b1",
        connection_id=cid,
    )
    bind.publish(
        binding_id=d1.binding_id,
        owner_id=o1,
        role="buyer",
        workspace="buyer",
        request_id="pub1",
    )
    d2 = bind.create(
        project_id=b.project_id,
        owner_id=o2,
        protocol="openai",
        supply_mode="dedicated",
        role="buyer",
        workspace="buyer",
        request_id="b2",
        connection_id=cid,
    )
    with pytest.raises(BindingError) as exc:
        bind.publish(
            binding_id=d2.binding_id,
            owner_id=o2,
            role="buyer",
            workspace="buyer",
            request_id="pub2",
        )
    assert exc.value.code == "PUBLISH_CONFLICT"


def test_retired_metadata_without_secret() -> None:
    conn, health, life, _ = _stack()
    rec = _verified(conn, health, life)
    life.retire(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="ret",
    )
    got = conn.get(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
    )
    assert got.lifecycle_state == "retired"
    public = got.to_public()
    assert public["seller_account_id"] == str(rec.seller_account_id)
    assert "ciphertext" not in public
    assert SECRET not in str(public)


def test_resume_drain_and_binding_blockers() -> None:
    conn, health, life, _ = _stack()
    rec = _verified(conn, health, life)
    life.list_supply(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="l",
    )
    life.pause(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="p",
    )
    resumed = life.resume(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="r",
    )
    assert resumed.lifecycle_state == "listed"
    drained = life.drain(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="d",
    )
    assert drained.lifecycle_state == "draining"
    retired = life.retire(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="t",
    )
    assert retired.lifecycle_state == "retired"


def test_buyer_forbidden() -> None:
    conn, health, life, _ = _stack()
    rec = _verified(conn, health, life)
    with pytest.raises(ConnectionError) as exc:
        life.list_supply(
            connection_id=rec.connection_id,
            seller_id=rec.seller_account_id,
            role="both",
            workspace="buyer",
            request_id="x",
        )
    assert exc.value.code == "FORBIDDEN_ROLE"
