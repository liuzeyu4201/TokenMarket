"""Project domain: create, immutable mode, state, binding, delete, admission."""

from __future__ import annotations

import time
import uuid

import pytest

from app.domain.projects.admission import allows_new_proxy
from app.domain.projects.binding import DictBindingLookup, EmptyBindingLookup
from app.domain.projects.service import ProjectError, ProjectService
from app.domain.projects.store import MemoryProjectStore


def _svc(binding=None) -> tuple[ProjectService, MemoryProjectStore]:
    store = MemoryProjectStore()
    return ProjectService(store=store, binding=binding or EmptyBindingLookup()), store


def _create(svc: ProjectService, owner: uuid.UUID, **kwargs):
    body = {
        "owner_id": owner,
        "display_name": kwargs.get("name", "Alpha"),
        "mode": kwargs.get("mode", "shared"),
        "enabled_protocols": kwargs.get("protocols", ["openai"]),
        "role": kwargs.get("role", "buyer"),
        "workspace": kwargs.get("workspace", "buyer"),
        "request_id": kwargs.get("request_id", "r1"),
        "idempotency_key": kwargs.get("idempotency_key"),
    }
    return svc.create(**body)


def test_create_shared_and_dedicated() -> None:
    svc, _ = _svc()
    owner = uuid.uuid4()
    shared = _create(svc, owner, name="S1", mode="shared")
    dedicated = _create(svc, owner, name="D1", mode="dedicated")
    assert shared.mode == "shared"
    assert dedicated.mode == "dedicated"
    assert shared.status == "draft"
    assert dedicated.status == "draft"
    assert shared.enabled_protocol_names() == ["openai"]


def test_name_conflict_case_insensitive() -> None:
    svc, _ = _svc()
    owner = uuid.uuid4()
    _create(svc, owner, name="MyProj")
    with pytest.raises(ProjectError) as exc:
        _create(svc, owner, name="myproj")
    assert exc.value.code == "NAME_CONFLICT"


def test_other_owner_can_reuse_name() -> None:
    svc, _ = _svc()
    _create(svc, uuid.uuid4(), name="Same")
    rec = _create(svc, uuid.uuid4(), name="Same")
    assert rec.display_name == "Same"


def test_seller_workspace_forbidden() -> None:
    svc, _ = _svc()
    with pytest.raises(ProjectError) as exc:
        _create(svc, uuid.uuid4(), role="both", workspace="seller")
    assert exc.value.code == "FORBIDDEN_ROLE"
    assert exc.value.http_status == 403


def test_idempotent_create() -> None:
    svc, _ = _svc()
    owner = uuid.uuid4()
    a = _create(svc, owner, name="Idem", idempotency_key="k1")
    b = _create(svc, owner, name="Idem", idempotency_key="k1")
    assert a.project_id == b.project_id


def test_state_machine_and_illegal() -> None:
    svc, _ = _svc()
    owner = uuid.uuid4()
    rec = _create(svc, owner)
    rec = svc.transition(
        project_id=rec.project_id,
        owner_id=owner,
        action="activate",
        role="buyer",
        workspace="buyer",
        request_id="t1",
    )
    assert rec.status == "active"
    rec = svc.transition(
        project_id=rec.project_id,
        owner_id=owner,
        action="suspend",
        role="buyer",
        workspace="buyer",
        request_id="t2",
    )
    assert rec.status == "suspended"
    rec = svc.transition(
        project_id=rec.project_id,
        owner_id=owner,
        action="activate",
        role="buyer",
        workspace="buyer",
        request_id="t3",
    )
    rec = svc.transition(
        project_id=rec.project_id,
        owner_id=owner,
        action="archive",
        role="buyer",
        workspace="buyer",
        request_id="t4",
    )
    assert rec.status == "archived"
    with pytest.raises(ProjectError) as exc:
        svc.transition(
            project_id=rec.project_id,
            owner_id=owner,
            action="activate",
            role="buyer",
            workspace="buyer",
            request_id="t5",
        )
    assert exc.value.code == "ILLEGAL_STATE_TRANSITION"
    assert (
        svc.get(
            project_id=rec.project_id,
            owner_id=owner,
            role="buyer",
            workspace="buyer",
        ).status
        == "archived"
    )


def test_archive_admission_immediate() -> None:
    svc, _ = _svc()
    owner = uuid.uuid4()
    rec = _create(svc, owner)
    rec = svc.transition(
        project_id=rec.project_id,
        owner_id=owner,
        action="activate",
        role="buyer",
        workspace="buyer",
        request_id="a1",
    )
    assert allows_new_proxy(rec) is True
    start = time.monotonic()
    rec = svc.transition(
        project_id=rec.project_id,
        owner_id=owner,
        action="archive",
        role="buyer",
        workspace="buyer",
        request_id="a2",
    )
    adm = svc.admission(
        project_id=rec.project_id,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
    )
    elapsed = time.monotonic() - start
    assert adm["allows_new_proxy"] is False
    assert elapsed < 1.0


def test_enable_protocol_fail_closed_without_binding() -> None:
    svc, store = _svc()
    owner = uuid.uuid4()
    rec = _create(svc, owner, protocols=["openai"])
    with pytest.raises(ProjectError) as exc:
        svc.enable_protocol(
            project_id=rec.project_id,
            owner_id=owner,
            protocol="anthropic",
            role="buyer",
            workspace="buyer",
            request_id="e1",
        )
    assert exc.value.code == "PROVIDER_BINDING_REQUIRED"
    again = svc.get(
        project_id=rec.project_id,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
    )
    assert again.enabled_protocol_names() == ["openai"]
    assert any(
        a["event_type"] == "project.protocol_enable_denied" for a in store.audits
    )


def test_enable_protocol_with_binding() -> None:
    binding = DictBindingLookup()
    svc, _ = _svc(binding=binding)
    owner = uuid.uuid4()
    rec = _create(svc, owner, protocols=["openai"])
    binding.grant(owner, rec.project_id, "anthropic")
    rec = svc.enable_protocol(
        project_id=rec.project_id,
        owner_id=owner,
        protocol="anthropic",
        role="buyer",
        workspace="buyer",
        request_id="e2",
    )
    assert "anthropic" in rec.enabled_protocol_names()


def test_disable_keeps_history_row() -> None:
    svc, _ = _svc()
    owner = uuid.uuid4()
    rec = _create(svc, owner, protocols=["openai"])
    rec = svc.disable_protocol(
        project_id=rec.project_id,
        owner_id=owner,
        protocol="openai",
        role="buyer",
        workspace="buyer",
        request_id="d1",
    )
    assert rec.enabled_protocol_names() == []
    assert len(rec.protocols) == 1
    assert rec.protocols[0].enabled is False
    assert rec.protocols[0].disabled_at is not None


def test_delete_blocked_and_then_succeeds() -> None:
    svc, store = _svc()
    owner = uuid.uuid4()
    rec = _create(svc, owner)
    store.add_blocker(rec.project_id, "key", "key-1")
    with pytest.raises(ProjectError) as exc:
        svc.delete(
            project_id=rec.project_id,
            owner_id=owner,
            role="buyer",
            workspace="buyer",
            request_id="del1",
        )
    assert exc.value.code == "DELETE_BLOCKED"
    assert exc.value.data["blockers"][0]["kind"] == "key"
    store._blockers[rec.project_id][0].resolved_at = rec.created_at  # noqa: SLF001
    svc.delete(
        project_id=rec.project_id,
        owner_id=owner,
        role="buyer",
        workspace="buyer",
        request_id="del2",
    )
    with pytest.raises(ProjectError) as gone:
        svc.get(
            project_id=rec.project_id,
            owner_id=owner,
            role="buyer",
            workspace="buyer",
        )
    assert gone.value.code == "NOT_FOUND"


def test_idor_same_not_found() -> None:
    svc, _ = _svc()
    a = uuid.uuid4()
    b = uuid.uuid4()
    rec = _create(svc, a)
    with pytest.raises(ProjectError) as other:
        svc.get(
            project_id=rec.project_id,
            owner_id=b,
            role="buyer",
            workspace="buyer",
        )
    with pytest.raises(ProjectError) as missing:
        svc.get(
            project_id=uuid.uuid4(),
            owner_id=a,
            role="buyer",
            workspace="buyer",
        )
    assert other.value.code == missing.value.code == "NOT_FOUND"
    assert other.value.message == missing.value.message
    assert other.value.http_status == missing.value.http_status == 404


def test_idempotency_conflict() -> None:
    svc, _ = _svc()
    owner = uuid.uuid4()
    _create(svc, owner, name="A", idempotency_key="same")
    with pytest.raises(ProjectError) as exc:
        _create(svc, owner, name="B", idempotency_key="same")
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_validation_empty_and_bad_protocol() -> None:
    svc, _ = _svc()
    owner = uuid.uuid4()
    with pytest.raises(ProjectError) as exc:
        _create(svc, owner, name="   ")
    assert exc.value.code == "VALIDATION"
    with pytest.raises(ProjectError) as exc2:
        _create(svc, owner, protocols=["ftp"])
    assert exc2.value.code == "VALIDATION"


def test_reject_mode_change_helper() -> None:
    svc, _ = _svc()
    with pytest.raises(ProjectError) as exc:
        svc.reject_mode_change()
    assert exc.value.code == "MODE_IMMUTABLE"


def test_memory_save_rejects_mode_mutation() -> None:
    svc, store = _svc()
    owner = uuid.uuid4()
    rec = _create(svc, owner, mode="shared")
    rec.mode = "dedicated"
    with pytest.raises(RuntimeError, match="immutable"):
        store.save(rec)
