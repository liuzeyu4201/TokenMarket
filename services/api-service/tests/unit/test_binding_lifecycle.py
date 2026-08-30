"""Provider Binding domain: publish, admit, degrade, protocol enable."""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.domain.bindings.ports import (
    AlwaysPriceLookup,
    ConnectionFact,
    DictConnectionLookup,
)
from app.domain.bindings.service import BindingError, BindingService
from app.domain.bindings.store import MemoryBindingStore
from app.domain.projects.service import ProjectError, ProjectService
from app.domain.projects.store import MemoryProjectStore


def _stack():
    projects = MemoryProjectStore()
    bindings = MemoryBindingStore()
    conns = DictConnectionLookup()
    bind = BindingService(
        store=bindings,
        projects=projects,
        connections=conns,
        prices=AlwaysPriceLookup(),
    )
    proj = ProjectService(store=projects, binding=bind)
    return proj, bind, conns


def _owner_project(proj: ProjectService, mode: str = "shared"):
    owner = uuid.uuid4()
    rec = proj.create(
        owner_id=owner,
        display_name=f"P-{uuid.uuid4().hex[:8]}",
        mode=mode,
        enabled_protocols=["openai"],
        role="buyer",
        workspace="buyer",
        request_id="c1",
    )
    return owner, rec


def _publish(bind: BindingService, owner, project_id, protocol: str, **kwargs):
    draft = bind.create(
        project_id=project_id,
        owner_id=owner,
        protocol=protocol,
        supply_mode=kwargs.get("supply_mode", "shared"),
        role="buyer",
        workspace="buyer",
        request_id="b1",
        allowed_models=kwargs.get("allowed_models", ["gpt-test"]),
        connection_id=kwargs.get("connection_id"),
    )
    return bind.publish(
        binding_id=draft.binding_id,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        request_id="p1",
    )


def test_three_protocols_active_sdk_hint_has_no_secret() -> None:
    proj, bind, _ = _stack()
    owner, rec = _owner_project(proj)
    hints = []
    for protocol in ("openai", "anthropic", "vertex"):
        published = _publish(bind, owner, rec.project_id, protocol)
        assert published.status == "active"
        hint = bind.sdk_hint(
            binding_id=published.binding_id,
            owner_id=owner,
            role="buyer",
            workspace="buyer",
        )
        hints.append(hint)
        blob = str(hint).lower()
        assert "secret" not in blob
        assert "api_key" not in blob
        assert "credential" not in blob
    assert {h["protocol"] for h in hints} == {"openai", "anthropic", "vertex"}
    assert hints[0]["base_url"] != ""  # native path present


def test_concurrent_publish_one_active() -> None:
    proj, bind, _ = _stack()
    owner, rec = _owner_project(proj)
    d1 = bind.create(
        project_id=rec.project_id,
        owner_id=owner,
        protocol="openai",
        supply_mode="shared",
        role="buyer",
        workspace="buyer",
        request_id="d1",
        allowed_models=["m1"],
    )
    d2 = bind.create(
        project_id=rec.project_id,
        owner_id=owner,
        protocol="openai",
        supply_mode="shared",
        role="buyer",
        workspace="buyer",
        request_id="d2",
        allowed_models=["m2"],
    )

    def _go(bid: uuid.UUID) -> str:
        try:
            bind.publish(
                binding_id=bid,
                owner_id=owner,
                role="buyer",
                workspace="buyer",
                request_id=str(bid),
            )
            return "ok"
        except BindingError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(_go, (d1.binding_id, d2.binding_id)))
    actives = [
        r
        for r in bind.list_mine(
            project_id=rec.project_id,
            owner_id=owner,
            role="buyer",
            workspace="buyer",
        )
        if r.status == "active" and r.protocol == "openai"
    ]
    assert len(actives) == 1
    assert "ok" in outcomes


def test_new_version_does_not_rewrite_old_row() -> None:
    proj, bind, _ = _stack()
    owner, rec = _owner_project(proj)
    first = _publish(bind, owner, rec.project_id, "openai", allowed_models=["old"])
    old_id, old_ver = first.binding_id, first.version
    second = _publish(bind, owner, rec.project_id, "openai", allowed_models=["new"])
    frozen = bind.get(
        binding_id=old_id, owner_id=owner, role="buyer", workspace="buyer"
    )
    assert frozen.version == old_ver
    assert frozen.allowed_models == ["old"]
    assert frozen.status == "inactive"
    start = time.monotonic()
    active = bind.active(
        project_id=rec.project_id,
        protocol="openai",
        owner_id=owner,
        role="buyer",
        workspace="buyer",
    )
    assert time.monotonic() - start < 1.0
    assert active.binding_id == second.binding_id
    assert active.version == old_ver + 1


def test_mode_mismatch_rejected() -> None:
    proj, bind, _ = _stack()
    owner, rec = _owner_project(proj, mode="shared")
    with pytest.raises(BindingError) as exc:
        bind.create(
            project_id=rec.project_id,
            owner_id=owner,
            protocol="openai",
            supply_mode="dedicated",
            role="buyer",
            workspace="buyer",
            request_id="x",
            connection_id=uuid.uuid4(),
        )
    assert exc.value.code == "MODE_MISMATCH"


def test_cross_protocol_and_model_admit_rejected() -> None:
    proj, bind, _ = _stack()
    owner, rec = _owner_project(proj)
    _publish(bind, owner, rec.project_id, "openai", allowed_models=["gpt-test"])
    with pytest.raises(BindingError) as cross:
        bind.admit(
            project_id=rec.project_id,
            owner_id=owner,
            protocol="openai",
            provider="anthropic",
            model="gpt-test",
            role="buyer",
            workspace="buyer",
        )
    assert cross.value.code == "PROTOCOL_MISMATCH"
    with pytest.raises(BindingError) as model:
        bind.admit(
            project_id=rec.project_id,
            owner_id=owner,
            protocol="openai",
            provider="openai",
            model="other-model",
            role="buyer",
            workspace="buyer",
        )
    assert model.value.code == "MODEL_NOT_ALLOWED"


def test_dedicated_degrade_no_shared_fallback() -> None:
    proj, bind, conns = _stack()
    owner, rec = _owner_project(proj, mode="dedicated")
    cid = uuid.uuid4()
    conns.put(
        ConnectionFact(
            connection_id=cid,
            provider="openai",
            supply_mode="dedicated",
            usable=True,
        )
    )
    published = _publish(
        bind,
        owner,
        rec.project_id,
        "openai",
        supply_mode="dedicated",
        connection_id=cid,
        allowed_models=[],
    )
    ok = bind.admit(
        project_id=rec.project_id,
        owner_id=owner,
        protocol="openai",
        provider="openai",
        model=None,
        role="buyer",
        workspace="buyer",
    )
    assert ok["version"] == published.version
    n = bind.degrade_for_connection(cid, "deg-1")
    assert n == 1
    with pytest.raises(BindingError) as exc:
        bind.admit(
            project_id=rec.project_id,
            owner_id=owner,
            protocol="openai",
            provider="openai",
            model=None,
            role="buyer",
            workspace="buyer",
        )
    assert exc.value.code == "BINDING_DEGRADED"
    assert exc.value.data["shared_pool"] is False
    assert exc.value.data["fallback"] is None


def test_enable_protocol_after_publish() -> None:
    proj, bind, _ = _stack()
    owner, rec = _owner_project(proj)
    with pytest.raises(ProjectError) as before:
        proj.enable_protocol(
            project_id=rec.project_id,
            owner_id=owner,
            protocol="anthropic",
            role="buyer",
            workspace="buyer",
            request_id="e0",
        )
    assert before.value.code == "PROVIDER_BINDING_REQUIRED"
    _publish(bind, owner, rec.project_id, "anthropic")
    enabled = proj.enable_protocol(
        project_id=rec.project_id,
        owner_id=owner,
        protocol="anthropic",
        role="buyer",
        workspace="buyer",
        request_id="e1",
    )
    assert "anthropic" in enabled.enabled_protocol_names()


def test_validate_deactivate_and_empty_connection() -> None:
    proj, bind, _ = _stack()
    owner, rec = _owner_project(proj)
    draft = bind.create(
        project_id=rec.project_id,
        owner_id=owner,
        protocol="openai",
        supply_mode="shared",
        role="buyer",
        workspace="buyer",
        request_id="v0",
        allowed_models=["m"],
    )
    validated = bind.validate(
        binding_id=draft.binding_id,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        request_id="v1",
    )
    assert validated.status == "validated"
    published = bind.publish(
        binding_id=draft.binding_id,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        request_id="v2",
    )
    stopped = bind.deactivate(
        binding_id=published.binding_id,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        request_id="v3",
    )
    assert stopped.status == "inactive"
    owner2, rec2 = _owner_project(proj, mode="dedicated")
    with pytest.raises(BindingError) as exc:
        bind.create(
            project_id=rec2.project_id,
            owner_id=owner2,
            protocol="openai",
            supply_mode="dedicated",
            role="buyer",
            workspace="buyer",
            request_id="no-conn",
            connection_id=uuid.uuid4(),
        )
    assert exc.value.code == "CONNECTION_REQUIRED"


def test_catalog_price_lookup_openai_stable() -> None:
    from app.domain.bindings.ports import CatalogPriceLookup, EmptyConnectionLookup

    lookup = CatalogPriceLookup()
    assert lookup.available("openai") is True
    assert EmptyConnectionLookup().get(uuid.uuid4()) is None


def test_seller_workspace_forbidden() -> None:
    proj, bind, _ = _stack()
    owner, rec = _owner_project(proj)
    with pytest.raises(BindingError) as exc:
        bind.create(
            project_id=rec.project_id,
            owner_id=owner,
            protocol="openai",
            supply_mode="shared",
            role="both",
            workspace="seller",
            request_id="s",
            allowed_models=["m"],
        )
    assert exc.value.code == "FORBIDDEN_ROLE"
