"""T058 configuration preflight contract tests.

Verify that missing, empty, wrongly-typed or dangerous production-default
configuration values fail before any persistent side effect and that error
messages only expose variable names, never values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root


@pytest.fixture
def security() -> Any:
    """Import the security module that T063 will implement."""
    try:
        import workflow.security as sec  # type: ignore[import]
    except ImportError as exc:
        pytest.fail(f"workflow.security has not been implemented yet (T063): {exc}")
    return sec


def test_missing_required_variable_fails(security: Any) -> None:
    schema = {"DATABASE_URL": {"type": "string", "required": True}}
    with pytest.raises(ValueError) as exc_info:
        security.validate_config(schema, {})
    assert "DATABASE_URL" in str(exc_info.value)
    assert "value" not in str(exc_info.value).lower()


def test_empty_required_variable_fails(security: Any) -> None:
    schema = {"DATABASE_URL": {"type": "string", "required": True}}
    with pytest.raises(ValueError) as exc_info:
        security.validate_config(schema, {"DATABASE_URL": ""})
    assert "DATABASE_URL" in str(exc_info.value)


def test_wrong_type_variable_fails(security: Any) -> None:
    schema = {"PORT": {"type": "integer", "required": True}}
    with pytest.raises(ValueError) as exc_info:
        security.validate_config(schema, {"PORT": "not-a-number"})
    assert "PORT" in str(exc_info.value)


def test_dangerous_production_default_fails(security: Any) -> None:
    schema = {
        "MODE": {
            "type": "string",
            "required": True,
            "allowed": ["local", "test", "prod"],
            "dangerous_defaults": ["prod"],
        }
    }
    with pytest.raises(ValueError) as exc_info:
        security.validate_config(schema, {"MODE": "prod"})
    assert "MODE" in str(exc_info.value)


def test_valid_local_config_passes(security: Any) -> None:
    schema = {
        "MODE": {
            "type": "string",
            "required": True,
            "allowed": ["local", "test", "prod"],
        },
        "DATABASE_URL": {"type": "string", "required": True},
    }
    security.validate_config(
        schema,
        {
            "MODE": "local",
            "DATABASE_URL": "postgresql://app:replace-me@localhost:5432/app",
        },
    )
