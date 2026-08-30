from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.usage import Observation


def _base(**kwargs):
    data = {
        "observation_id": "obs-1",
        "request_id": "rid-1",
        "project_id": "proj-1",
        "provider": "openai",
        "endpoint_id": "openai.post.v1.chat.completions",
        "cost_status": "rated",
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        "parser_version": "1.0.0",
        "evidence_digest": "abc",
    }
    data.update(kwargs)
    return data


def test_rated_usage_without_cost() -> None:
    obs = Observation.model_validate(_base())
    assert obs.reported_cost_minor_units is None
    assert obs.cost_status == "rated"


def test_reported_requires_amount() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(_base(cost_status="reported"))


def test_unresolved_rejects_zero_cost() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(
            _base(
                cost_status="unresolved",
                reported_cost_minor_units=0,
                usage={},
            )
        )


def test_unresolved_null_cost_ok() -> None:
    obs = Observation.model_validate(
        _base(cost_status="unresolved", unresolved_reason="missing_usage", usage={})
    )
    assert obs.reported_cost_minor_units is None


def test_forbids_raw_body_field() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(_base(raw_body="secret"))
