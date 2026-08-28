"""Routable seller keys exclude ineligible owners."""

from __future__ import annotations

import os
import uuid

from app.domain.owners import owner_can_route_seller_keys
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.memory_store import MemoryKeyStore


def _insert_routable(store: MemoryKeyStore, seller_id: uuid.UUID) -> uuid.UUID:
    enc = CredentialEncryptor(os.urandom(32), "v1")
    nonce, ct, tag = enc.encrypt(b"sk-ok")
    kid = uuid.uuid4()
    store.insert(
        {
            "id": kid,
            "seller_id": seller_id,
            "platform": "volcano",
            "fingerprint": f"fp-{kid}",
            "ciphertext": ct,
            "nonce": nonce,
            "tag": tag,
            "administrative_state": "active",
            "health_state": "healthy",
            "remaining_quota": "9",
            "soft_deleted": False,
        }
    )
    return kid


def test_seller_owner_eligibility_matrix() -> None:
    assert owner_can_route_seller_keys("active", "seller") is True
    assert owner_can_route_seller_keys("active", "both") is True
    assert owner_can_route_seller_keys("suspended", "seller") is False
    assert owner_can_route_seller_keys("active", "buyer") is False
    assert owner_can_route_seller_keys("active", "seller", is_deleted=True) is False


def test_suspended_deleted_buyer_only_and_role_changed_never_routable() -> None:
    store = MemoryKeyStore()
    suspended = uuid.uuid4()
    deleted = uuid.uuid4()
    buyer_only = uuid.uuid4()
    role_changed = uuid.uuid4()
    healthy = uuid.uuid4()
    for sid in (suspended, deleted, buyer_only, role_changed, healthy):
        _insert_routable(store, sid)
    store.set_owner(suspended, status="suspended", role="seller")
    store.set_owner(deleted, status="active", role="seller", is_deleted=True)
    store.set_owner(buyer_only, status="active", role="buyer")
    store.set_owner(role_changed, status="active", role="buyer")
    store.set_owner(healthy, status="active", role="seller")
    got = {row["seller_id"] for row in store.list_routable()}
    assert got == {healthy}
    assert suspended not in got
    assert deleted not in got
    assert buyer_only not in got
    assert role_changed not in got
