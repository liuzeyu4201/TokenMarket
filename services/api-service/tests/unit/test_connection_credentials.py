"""Provider Connection encryption, fingerprint, replace CAS, delete wipe."""

from __future__ import annotations

import json
import threading
import uuid

import pytest

from app.domain.bindings.ports import AlwaysPriceLookup, ConnectionFact
from app.domain.bindings.service import BindingError, BindingService
from app.domain.bindings.store import MemoryBindingStore
from app.domain.connections.service import (
    ConnectionError,
    ConnectionService,
    ServiceConnectionLookup,
)
from app.domain.connections.store import MemoryConnectionStore
from app.domain.projects.service import ProjectService
from app.domain.projects.store import MemoryProjectStore
from app.domain.sellerkeys.crypto import CredentialEncryptor

SECRET = "sk-live-plaintext-never-store"
FP = b"f" * 32


def _enc(
    version: str = "v1", previous: dict[str, bytes] | None = None
) -> CredentialEncryptor:
    material = {"v1": b"a" * 32, "v2": b"b" * 32}
    return CredentialEncryptor(material[version], version, previous=previous)


def _svc(
    store: MemoryConnectionStore | None = None,
    enc: CredentialEncryptor | None = None,
    resolver=None,
    bindings=None,
) -> tuple[ConnectionService, MemoryConnectionStore]:
    store = store if store is not None else MemoryConnectionStore()
    svc = ConnectionService(
        enc or _enc(),
        FP,
        store=store,
        resolver=resolver or (lambda _h, _p: ["1.1.1.1"]),
        bindings=bindings,
    )
    return svc, store


def _create(svc: ConnectionService, seller: uuid.UUID, secret: str = SECRET, **kwargs):
    return svc.create(
        seller_id=seller,
        provider=kwargs.get("provider", "openai"),
        supply_mode=kwargs.get("supply_mode", "shared"),
        secret=secret,
        role=kwargs.get("role", "seller"),
        workspace=kwargs.get("workspace", "seller"),
        request_id=kwargs.get("request_id", "req-1"),
        project_number=kwargs.get("project_number"),
        location=kwargs.get("location"),
        base_url=kwargs.get("base_url"),
    )


def _audits_blob(store: MemoryConnectionStore) -> str:
    return json.dumps(store.audits, default=str)


def test_create_encrypts_and_fingerprints() -> None:
    svc, store = _svc()
    seller = uuid.uuid4()
    rec = _create(svc, seller)
    assert rec.ciphertext is not None
    assert rec.ciphertext != SECRET.encode("utf-8")
    assert rec.nonce is not None and rec.tag is not None
    assert rec.credential_fingerprint
    assert SECRET not in rec.credential_fingerprint
    assert SECRET not in rec.to_public()["credential_fingerprint"]
    assert "ciphertext" not in rec.to_public()
    stored = store.get(rec.connection_id)
    assert stored is not None
    assert stored.ciphertext != SECRET.encode("utf-8")
    assert SECRET not in _audits_blob(store)
    assert stored.usable() is True


def test_buyer_workspace_forbidden() -> None:
    svc, _ = _svc()
    with pytest.raises(ConnectionError) as exc:
        _create(svc, uuid.uuid4(), role="both", workspace="buyer")
    assert exc.value.http_status == 403
    assert exc.value.code == "FORBIDDEN_ROLE"


def test_buyer_role_without_workspace_forbidden() -> None:
    svc, _ = _svc()
    with pytest.raises(ConnectionError) as exc:
        _create(svc, uuid.uuid4(), role="buyer", workspace=None)
    assert exc.value.code == "FORBIDDEN_ROLE"


def test_seller_role_without_workspace_allowed() -> None:
    svc, _ = _svc()
    rec = _create(svc, uuid.uuid4(), role="seller", workspace=None)
    assert rec.status == "active"


def test_invalid_provider_rejected() -> None:
    svc, _ = _svc()
    with pytest.raises(ConnectionError) as exc:
        _create(svc, uuid.uuid4(), provider="volcano")
    assert exc.value.code == "VALIDATION"


def test_empty_secret_and_vertex_fields() -> None:
    svc, _ = _svc()
    seller = uuid.uuid4()
    with pytest.raises(ConnectionError) as empty:
        _create(svc, seller, secret="  ")
    assert empty.value.code == "VALIDATION"
    with pytest.raises(ConnectionError) as vertex:
        _create(svc, seller, provider="vertex", secret="sa-json")
    assert vertex.value.code == "VALIDATION"
    rec = _create(
        svc,
        seller,
        secret="sa-json",
        provider="vertex",
        project_number="123",
        location="us-central1",
    )
    assert rec.auth_type == "service_account"


def test_ssrf_on_custom_url() -> None:
    svc, _ = _svc()
    with pytest.raises(ConnectionError) as exc:
        _create(svc, uuid.uuid4(), base_url="https://127.0.0.1/v1")
    assert exc.value.code == "SSRF_REJECTED"


def test_official_default_skips_resolver() -> None:
    def boom(_h: str, _p: int) -> list[str]:
        raise AssertionError("dns")

    svc, _ = _svc(resolver=boom)
    rec = _create(svc, uuid.uuid4())
    assert rec.base_url == "https://api.openai.com"


def test_unwrap_proxy_and_audit_has_no_plaintext(
    caplog: pytest.LogCaptureFixture,
) -> None:
    svc, store = _svc()
    seller = uuid.uuid4()
    rec = _create(svc, seller)
    with caplog.at_level("INFO"):
        plain = svc.unwrap(
            connection_id=rec.connection_id, purpose="proxy", request_id="u1"
        )
    assert plain == SECRET
    assert SECRET not in _audits_blob(store)
    assert SECRET not in caplog.text
    events = [a["event_type"] for a in store.audits]
    assert "connection.unwrapped" in events
    with pytest.raises(ConnectionError):
        svc.unwrap(connection_id=rec.connection_id, purpose="admin", request_id="u2")


def test_previous_key_version_still_decrypts() -> None:
    store = MemoryConnectionStore()
    old = ConnectionService(
        _enc("v1"), FP, store=store, resolver=lambda _h, _p: ["1.1.1.1"]
    )
    seller = uuid.uuid4()
    rec = _create(old, seller)
    ring = ConnectionService(
        _enc("v2", previous={"v1": b"a" * 32}),
        FP,
        store=store,
        resolver=lambda _h, _p: ["1.1.1.1"],
    )
    assert (
        ring.unwrap(connection_id=rec.connection_id, purpose="verify", request_id="rot")
        == SECRET
    )


def test_concurrent_replace_no_mix() -> None:
    svc, store = _svc()
    seller = uuid.uuid4()
    rec = _create(svc, seller, secret="old-secret-aaaaaaaa")
    errors: list[str] = []
    results: list[str] = []

    def worker(secret: str) -> None:
        try:
            out = svc.replace_credential(
                connection_id=rec.connection_id,
                seller_id=seller,
                secret=secret,
                expected_version=1,
                role="seller",
                workspace="seller",
                request_id="c-" + secret,
            )
            results.append(out.credential_fingerprint)
        except ConnectionError as exc:
            errors.append(exc.code)

    t1 = threading.Thread(target=worker, args=("new-secret-bbbbbbbb",))
    t2 = threading.Thread(target=worker, args=("new-secret-cccccccc",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert len(results) == 1
    assert errors == ["VERSION_CONFLICT"]
    stored = store.get(rec.connection_id)
    assert stored is not None
    plain = svc.unwrap(
        connection_id=rec.connection_id, purpose="proxy", request_id="after"
    )
    assert plain in {"new-secret-bbbbbbbb", "new-secret-cccccccc"}
    assert "old-secret-aaaaaaaa" != plain
    assert stored.credential_version == 2


def test_delete_wipes_ciphertext_and_unwrap_fails() -> None:
    svc, store = _svc()
    seller = uuid.uuid4()
    rec = _create(svc, seller)
    fp = rec.credential_fingerprint
    svc.delete(
        connection_id=rec.connection_id,
        seller_id=seller,
        role="seller",
        workspace="seller",
        request_id="del",
    )
    stored = store.get(rec.connection_id)
    assert stored is not None
    assert stored.ciphertext is None
    assert stored.nonce is None
    assert stored.tag is None
    assert stored.status == "deleted"
    assert stored.usable() is False
    assert svc.get_fact(rec.connection_id) is None
    with pytest.raises(ConnectionError) as exc:
        svc.unwrap(connection_id=rec.connection_id, purpose="proxy", request_id="x")
    assert exc.value.http_status == 404
    deleted_events = [
        a for a in store.audits if a["event_type"] == "connection.deleted"
    ]
    assert any(a["payload"].get("fingerprint") == fp for a in deleted_events)
    listed = svc.list_mine(seller_id=seller, role="seller", workspace="seller")
    assert listed == []
    with pytest.raises(ConnectionError) as missing:
        svc.get(
            connection_id=rec.connection_id,
            seller_id=seller,
            role="seller",
            workspace="seller",
        )
    assert missing.value.code == "NOT_FOUND"


def test_delete_degrades_dedicated_binding() -> None:
    projects = MemoryProjectStore()
    bindings = MemoryBindingStore()
    conns = MemoryConnectionStore()
    conn_svc, _ = _svc(store=conns)
    bind = BindingService(
        store=bindings,
        projects=projects,
        connections=ServiceConnectionLookup(conn_svc),
        prices=AlwaysPriceLookup(),
    )
    conn_svc.bind_bindings(bind)
    proj = ProjectService(store=projects, binding=bind)
    owner = uuid.uuid4()
    project = proj.create(
        owner_id=owner,
        display_name="Ded",
        mode="dedicated",
        enabled_protocols=["openai"],
        role="buyer",
        workspace="buyer",
        request_id="p1",
    )
    rec = _create(conn_svc, owner, supply_mode="dedicated")
    draft = bind.create(
        project_id=project.project_id,
        owner_id=owner,
        protocol="openai",
        supply_mode="dedicated",
        role="buyer",
        workspace="buyer",
        request_id="b1",
        connection_id=rec.connection_id,
    )
    published = bind.publish(
        binding_id=draft.binding_id,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        request_id="b2",
    )
    assert published.status == "active"
    conn_svc.delete(
        connection_id=rec.connection_id,
        seller_id=owner,
        role="seller",
        workspace="seller",
        request_id="del",
    )
    with pytest.raises(BindingError) as exc:
        bind.admit(
            project_id=project.project_id,
            owner_id=owner,
            protocol="openai",
            provider="openai",
            model=None,
            role="buyer",
            workspace="buyer",
        )
    assert exc.value.code == "BINDING_DEGRADED"
    assert exc.value.data["shared_pool"] is False


def test_idor_other_seller() -> None:
    svc, _ = _svc()
    rec = _create(svc, uuid.uuid4())
    with pytest.raises(ConnectionError) as exc:
        svc.get(
            connection_id=rec.connection_id,
            seller_id=uuid.uuid4(),
            role="seller",
            workspace="seller",
        )
    assert exc.value.code == "NOT_FOUND"


def test_unwrap_wrong_actor_and_corrupt() -> None:
    svc, store = _svc()
    seller = uuid.uuid4()
    rec = _create(svc, seller)
    with pytest.raises(ConnectionError):
        svc.unwrap(
            connection_id=rec.connection_id,
            purpose="proxy",
            request_id="x",
            actor_seller_id=uuid.uuid4(),
        )
    stored = store.by_id[rec.connection_id]
    stored.tag = b"\x00" * 32
    with pytest.raises(ConnectionError):
        svc.unwrap(connection_id=rec.connection_id, purpose="proxy", request_id="bad")


def test_get_fact_matches_port() -> None:
    svc, _ = _svc()
    rec = _create(svc, uuid.uuid4(), supply_mode="dedicated")
    fact = svc.get_fact(rec.connection_id)
    assert isinstance(fact, ConnectionFact)
    assert fact.usable is True
    assert fact.provider == "openai"
    assert fact.supply_mode == "dedicated"
    assert svc.get_fact(uuid.uuid4()) is None


def test_replace_version_conflict() -> None:
    svc, _ = _svc()
    seller = uuid.uuid4()
    rec = _create(svc, seller)
    with pytest.raises(ConnectionError) as exc:
        svc.replace_credential(
            connection_id=rec.connection_id,
            seller_id=seller,
            secret="next-secret-dddddddd",
            expected_version=99,
            role="seller",
            workspace="seller",
            request_id="bad-ver",
        )
    assert exc.value.code == "VERSION_CONFLICT"
    assert exc.value.http_status == 409
