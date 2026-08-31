from __future__ import annotations

import uuid

import pytest

from app.domain.projects.codes import MODE_IMMUTABLE
from app.domain.projects.service import ProjectError, ProjectService


def test_buyer_create_then_mode_change_rejected() -> None:
    svc = ProjectService()
    owner = uuid.uuid4()
    rec = svc.create(
        owner_id=owner,
        display_name="Release Journey",
        mode="dedicated",
        enabled_protocols=["openai"],
        role="buyer",
        workspace="buyer",
        request_id="rel-1",
        idempotency_key="rel-1",
    )
    assert rec.mode == "dedicated"
    renamed = svc.rename(
        project_id=rec.project_id,
        owner_id=owner,
        display_name="Release Journey 2",
        role="buyer",
        workspace="buyer",
        request_id="rel-2",
    )
    assert renamed.mode == "dedicated"
    with pytest.raises(ProjectError) as exc:
        svc.reject_mode_change()
    assert exc.value.code == MODE_IMMUTABLE
    seller = ProjectService()
    with pytest.raises(ProjectError):
        seller.create(
            owner_id=uuid.uuid4(),
            display_name="Seller Project",
            mode="shared",
            enabled_protocols=["openai"],
            role="seller",
            workspace="seller",
            request_id="rel-3",
        )
