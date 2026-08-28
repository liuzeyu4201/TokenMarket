"""Proxy-key authenticate/lookup deny ineligible owners (finding: owner-state)."""

from __future__ import annotations

import threading
import uuid

from app.domain.owners import owner_can_use_proxy_keys
from app.domain.proxykeys.service import MemoryProxyStore, ProxyKeyService


def _issued(role: str = "buyer"):
    store = MemoryProxyStore()
    buyer = uuid.uuid4()
    store.set_owner(buyer, status="active", role=role)
    svc = ProxyKeyService(b"p" * 32, store=store)
    rec = svc.issue(buyer_id=buyer, role="buyer" if role == "seller" else role)
    return svc, store, rec


def test_owner_eligibility_matrix() -> None:
    assert owner_can_use_proxy_keys("active", "buyer") is True
    assert owner_can_use_proxy_keys("active", "both") is True
    assert owner_can_use_proxy_keys("suspended", "buyer") is False
    assert owner_can_use_proxy_keys("active", "seller") is False
    assert owner_can_use_proxy_keys("active", "buyer", is_deleted=True) is False
    assert owner_can_use_proxy_keys("active", "buyer", is_deleted=False) is True


def test_suspended_owner_denied_on_authenticate_and_lookup() -> None:
    svc, store, rec = _issued()
    secret = rec.secret_once
    assert secret is not None
    assert svc.authenticate(secret) is not None
    store.set_owner(rec.buyer_id, status="suspended", role="buyer")
    assert svc.authenticate(secret) is None
    assert svc.lookup_hash(store.hashes[rec.key_id]) is None


def test_deleted_owner_denied() -> None:
    svc, store, rec = _issued()
    secret = rec.secret_once
    assert secret is not None
    store.set_owner(rec.buyer_id, status="active", role="buyer", is_deleted=True)
    assert svc.authenticate(secret) is None
    assert svc.lookup_hash(store.hashes[rec.key_id]) is None


def test_seller_only_owner_denied() -> None:
    store = MemoryProxyStore()
    buyer = uuid.uuid4()
    store.set_owner(buyer, status="active", role="seller")
    svc = ProxyKeyService(b"p" * 32, store=store)
    rec = svc.issue(buyer_id=buyer, role="buyer")
    store.set_owner(buyer, status="active", role="seller")
    assert rec.secret_once is not None
    assert svc.authenticate(rec.secret_once) is None
    assert svc.lookup_hash(store.hashes[rec.key_id]) is None


def test_role_changed_to_seller_denied() -> None:
    svc, store, rec = _issued(role="buyer")
    secret = rec.secret_once
    assert secret is not None
    store.set_owner(rec.buyer_id, status="active", role="seller")
    assert svc.authenticate(secret) is None
    assert svc.lookup_hash(store.hashes[rec.key_id]) is None


def test_race_suspension_vs_auth_no_post_commit_success() -> None:
    svc, store, rec = _issued()
    secret = rec.secret_once
    assert secret is not None
    post_commit_success = []
    suspended = threading.Event()
    started = threading.Event()

    def authenticate_loop() -> None:
        started.set()
        for _ in range(2000):
            got = svc.authenticate(secret)
            if suspended.is_set() and got is not None:
                post_commit_success.append(got)

    def suspend() -> None:
        started.wait(timeout=1)
        store.set_owner(rec.buyer_id, status="suspended", role="buyer")
        suspended.set()

    t_auth = threading.Thread(target=authenticate_loop)
    t_susp = threading.Thread(target=suspend)
    t_auth.start()
    t_susp.start()
    t_auth.join()
    t_susp.join()
    assert svc.authenticate(secret) is None
    assert post_commit_success == []
