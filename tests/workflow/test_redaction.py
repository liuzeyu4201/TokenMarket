"""T058 redaction contract tests.

Verify that secrets and personally identifiable values are removed from
terminal output, JSONL events, exceptions, service logs, test fixtures and
build arguments before they are persisted or displayed.
"""

from __future__ import annotations

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


@pytest.mark.parametrize(
    "raw,expected_substring",
    [
        ("key=sk-abcdefghijklmnopqrstuvwxyz1234", "[REDACTED]"),
        ("Authorization: bearer abcdef1234567890", "[REDACTED]"),
        ("api_key=super_secret_value_12345", "[REDACTED]"),
        ("password=MyP@ssw0rd!", "[REDACTED]"),
    ],
)
def test_redact_removes_secret_values(security: Any, raw: str, expected_substring: str) -> None:
    result = security.redact(raw)
    assert expected_substring in result
    assert "super_secret_value_12345" not in result
    assert "MyP@ssw0rd!" not in result
    assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in result


def test_redact_preserves_variable_names(security: Any) -> None:
    result = security.redact("api_key=secret-value")
    assert "api_key" in result
    assert "secret-value" not in result


def test_redact_handles_empty_string(security: Any) -> None:
    assert security.redact("") == ""


def test_validate_no_secret_raises_on_credential(security: Any) -> None:
    with pytest.raises(ValueError) as exc_info:
        security.validate_no_secret_in_text("api_key=real-secret-value", context="fixture")
    assert "fixture" in str(exc_info.value)


def test_validate_no_secret_passes_for_safe_placeholder(security: Any) -> None:
    security.validate_no_secret_in_text("api_key=replace-me", context="fixture")


def test_is_safe_placeholder_recognizes_examples(security: Any) -> None:
    assert security.is_safe_placeholder("replace-me")
    assert security.is_safe_placeholder("<SECRET>")
    assert security.is_safe_placeholder("changeme")
    assert security.is_safe_placeholder("example.local")
    assert not security.is_safe_placeholder("real-secret-123")
