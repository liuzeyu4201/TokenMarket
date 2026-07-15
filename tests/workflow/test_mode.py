"""T085 mode selection contract tests.

Verify that mode defaults to local, test/prod require explicit selection,
illegal values are rejected, and prod requires approval before any resource
access.
"""

from __future__ import annotations

from typing import Any

import pytest

from .helpers import find_repo_root


@pytest.fixture
def mode_module() -> Any:
    try:
        import workflow.mode as mod  # type: ignore[import]
    except ImportError as exc:
        pytest.fail(f"workflow.mode has not been implemented yet (T090): {exc}")
    return mod


def test_mode_defaults_to_local(mode_module: Any) -> None:
    selection = mode_module.validate_mode(None, "omitted")
    assert selection.mode == "local"


def test_explicit_local_is_allowed(mode_module: Any) -> None:
    selection = mode_module.validate_mode("local", "command")
    assert selection.mode == "local"


def test_test_requires_command_origin(mode_module: Any) -> None:
    selection = mode_module.validate_mode("test", "command")
    assert selection.mode == "test"


def test_prod_requires_command_origin(mode_module: Any) -> None:
    selection = mode_module.validate_mode("prod", "command")
    assert selection.mode == "prod"


def test_test_from_environment_is_rejected(mode_module: Any) -> None:
    with pytest.raises(mode_module.ModeError):
        mode_module.validate_mode("test", "environment")


def test_prod_from_file_is_rejected(mode_module: Any) -> None:
    with pytest.raises(mode_module.ModeError):
        mode_module.validate_mode("prod", "file")


def test_invalid_mode_value_is_rejected(mode_module: Any) -> None:
    with pytest.raises(mode_module.ModeError):
        mode_module.validate_mode("staging", "command")


def test_prod_requires_approval(mode_module: Any) -> None:
    selection = mode_module.validate_mode("prod", "command")
    with pytest.raises(mode_module.ModeError):
        mode_module.require_production_approval(selection)
