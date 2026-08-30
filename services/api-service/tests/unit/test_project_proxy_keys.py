"""Project-scoped proxy keys: scope, quota, rotate, revoke."""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.bindings.ports import AlwaysPriceLookup
from app.domain.bindings.service import BindingService
from app.domain.bindings.store import MemoryBindingStore
from app.domain.projects.service import ProjectService
from app.domain.projects.store import MemoryProjectStore
from app.domain.proxykeys.service import ProxyKeyService, hash_proxy_secret


def _stack():
    projects = MemoryProjectStore()
    bindings = MemoryBindingStore()
    bind = BindingService(store=bindings, projects=projects, prices=AlwaysPriceLookup())
    proj = ProjectService(store=projects, binding=bind)
    keys = ProxyKeyService(b"p" * 32, projects=projects, bindings=bind)
    return proj, bind, keys


def _ready_project(proj, bind, mode="shared"):
    owner = uuid.uuid4()
    rec = proj.create(
        owner_id=owner,
        display_name=f"K-{uuid.uuid4().hex[:8]}",
        mode=mode,
        enabled_protocols=["openai"],
        role="buyer",
        workspace="buyer",
        request_id="c",
    )
    draft = bind.create(
        project_id=rec.project_id,
        owner_id=owner,
        protocol="openai",
        supply_mode=mode,
        role="buyer",
        workspace="buyer",
        request_id="b",
        allowed_models=["gpt-test"],
        connection_id=None,
    )
    if mode == "dedicated":
        # dedicated needs connection — use shared for most tests
        pass
    bind.publish(
        binding_id=draft.binding_id,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        request_id="p",
    )
    return owner, rec


def test_issue_secret_once_and_not_in_store() -> None:
    proj, bind, keys = _stack()
    owner, rec = _ready_project(proj, bind)
    issued = keys.issue_for_project(
        buyer_id=owner,
        project_id=rec.project_id,
        protocols=["openai"],
        allowed_models=["gpt-test"],
        name="dev",
    )
    assert issued.secret_once is not None
    assert issued.secret_once.startswith("tmk-")
    secret = issued.secret_once
    listed = keys.list_project(owner, rec.project_id, "buyer")
    assert listed[0].secret_once is None or listed[0].secret_once != secret
    # HMAC store has no plaintext
    store = keys._store  # noqa: SLF001
    blob = str(store.by_id) + str(store.by_hash)
    assert secret not in blob
    assert keys.authorize(secret, protocol="openai", model="gpt-test") is not None


def test_scope_matrix() -> None:
    proj, bind, keys = _stack()
    owner, rec = _ready_project(proj, bind)
    issued = keys.issue_for_project(
        buyer_id=owner,
        project_id=rec.project_id,
        protocols=["openai"],
        allowed_models=["gpt-test"],
        allowed_cidrs=["127.0.0.1/32"],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    secret = issued.secret_once
    assert (
        keys.authorize(
            secret, protocol="openai", model="gpt-test", client_ip="127.0.0.1"
        )
        is not None
    )
    assert (
        keys.authorize(
            secret, protocol="anthropic", model="gpt-test", client_ip="127.0.0.1"
        )
        is None
    )
    assert (
        keys.authorize(secret, protocol="openai", model="other", client_ip="127.0.0.1")
        is None
    )
    assert (
        keys.authorize(
            secret, protocol="openai", model="gpt-test", client_ip="10.0.0.1"
        )
        is None
    )
    expired = keys.issue_for_project(
        buyer_id=owner,
        project_id=rec.project_id,
        protocols=["openai"],
        allowed_models=["gpt-test"],
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        name="old",
    )
    assert (
        keys.authorize(
            expired.secret_once or "",
            protocol="openai",
            model="gpt-test",
        )
        is None
    )


def test_concurrent_quota_not_over_accepted() -> None:
    proj, bind, keys = _stack()
    owner, rec = _ready_project(proj, bind)
    issued = keys.issue_for_project(
        buyer_id=owner,
        project_id=rec.project_id,
        protocols=["openai"],
        allowed_models=["gpt-test"],
        quota_period="day",
        quota_limit=5,
    )
    secret = issued.secret_once or ""

    def _one(_: int) -> bool:
        return keys.authorize(secret, protocol="openai", model="gpt-test") is not None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_one, range(20)))
    assert sum(1 for ok in results if ok) == 5


def test_rotate_and_revoke_within_one_second() -> None:
    proj, bind, keys = _stack()
    owner, rec = _ready_project(proj, bind)
    issued = keys.issue_for_project(
        buyer_id=owner,
        project_id=rec.project_id,
        protocols=["openai"],
        allowed_models=["gpt-test"],
    )
    old = issued.secret_once or ""
    rotated = keys.rotate(issued.key_id, owner, rec.project_id, "buyer")
    new = rotated.secret_once or ""
    assert new != old
    assert keys.authorize(old, protocol="openai", model="gpt-test") is None
    assert keys.authorize(new, protocol="openai", model="gpt-test") is not None
    start = time.monotonic()
    keys.revoke_project_key(issued.key_id, owner, rec.project_id, "buyer")
    assert keys.authorize(new, protocol="openai", model="gpt-test") is None
    assert time.monotonic() - start < 1.0
    with pytest.raises(Exception) as exc:
        keys.enable(issued.key_id, owner, rec.project_id, "buyer")
    assert exc.value.code == "ILLEGAL_STATE_TRANSITION"


def test_cross_project_hidden() -> None:
    proj, bind, keys = _stack()
    a, pa = _ready_project(proj, bind)
    b, pb = _ready_project(proj, bind)
    issued = keys.issue_for_project(
        buyer_id=a,
        project_id=pa.project_id,
        protocols=["openai"],
        allowed_models=["gpt-test"],
    )
    with pytest.raises(Exception) as exc:
        keys.revoke_project_key(issued.key_id, b, pb.project_id, "buyer")
    assert exc.value.code == "NOT_FOUND"
    with pytest.raises(Exception) as missing:
        keys.revoke_project_key(uuid.uuid4(), a, pa.project_id, "buyer")
    assert missing.value.code == "NOT_FOUND"


def test_binding_subset_required() -> None:
    proj, bind, keys = _stack()
    owner, rec = _ready_project(proj, bind)
    with pytest.raises(Exception) as exc:
        keys.issue_for_project(
            buyer_id=owner,
            project_id=rec.project_id,
            protocols=["anthropic"],
        )
    assert exc.value.code == "PROVIDER_BINDING_REQUIRED"
    with pytest.raises(Exception) as scope:
        keys.issue_for_project(
            buyer_id=owner,
            project_id=rec.project_id,
            protocols=["openai"],
            allowed_models=["not-in-binding"],
        )
    assert scope.value.code == "SCOPE_EXCEEDED"


def test_invalid_cidr_and_seller_workspace() -> None:
    proj, bind, keys = _stack()
    owner, rec = _ready_project(proj, bind)
    with pytest.raises(Exception) as bad:
        keys.issue_for_project(
            buyer_id=owner,
            project_id=rec.project_id,
            protocols=["openai"],
            allowed_cidrs=["not-a-cidr"],
        )
    assert bad.value.code == "VALIDATION"
    with pytest.raises(Exception) as ws:
        keys.issue_for_project(
            buyer_id=owner,
            project_id=rec.project_id,
            protocols=["openai"],
            role="both",
            workspace="seller",
        )
    assert ws.value.code == "FORBIDDEN_ROLE"


def test_disable_enable_and_month_quota() -> None:
    proj, bind, keys = _stack()
    owner, rec = _ready_project(proj, bind)
    issued = keys.issue_for_project(
        buyer_id=owner,
        project_id=rec.project_id,
        protocols=["openai"],
        allowed_models=["gpt-test"],
        quota_period="month",
        quota_limit=1,
    )
    secret = issued.secret_once or ""
    keys.disable(issued.key_id, owner, rec.project_id, "buyer")
    assert keys.authorize(secret, protocol="openai", model="gpt-test") is None
    keys.enable(issued.key_id, owner, rec.project_id, "buyer")
    assert keys.authorize(secret, protocol="openai", model="gpt-test") is not None
    assert keys.authorize(secret, protocol="openai", model="gpt-test") is None


def test_hash_not_invertible_and_volcano_still_works() -> None:
    keys = ProxyKeyService(b"p" * 32)
    buyer = uuid.uuid4()
    issued = keys.issue(buyer_id=buyer)
    secret = issued.secret_once or ""
    digest = hash_proxy_secret(secret, b"p" * 32)
    assert secret not in digest
    assert keys.authenticate(secret) is not None
    keys.revoke(issued.key_id, buyer)
    assert keys.authenticate(secret) is None
