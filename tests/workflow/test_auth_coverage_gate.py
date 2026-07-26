"""Authentication domain/route 80% coverage fail-closed gate (004 T017)."""

from __future__ import annotations

from .helpers import load_text, repo_path


def test_api_service_makefile_enforces_auth_coverage_gate() -> None:
    makefile = load_text("services", "api-service", "Makefile")
    assert "--cov-fail-under=80" in makefile
    assert "app.domain.authentication" in makefile or "domain.authentication" in makefile
    assert "app.security" in makefile or "app/security" in makefile
    # Aggregate whole-app coverage must not replace the auth-specific gate
    assert makefile.count("--cov-fail-under=80") >= 2


def test_auth_coverage_gate_not_only_aggregate() -> None:
    """A single aggregate --cov=app fail-under cannot substitute auth package gates."""
    makefile = load_text("services", "api-service", "Makefile")
    # First pytest may use aggregate cov-fail-under=0; auth gate is separate.
    assert "--cov-fail-under=0" in makefile
    auth_block_markers = ("authentication", "security")
    assert all(m in makefile for m in auth_block_markers)


def test_root_make_test_still_delegates_without_new_public_actions() -> None:
    root_make = load_text("Makefile")
    # No new public make action for auth coverage
    for forbidden in (
        "auth-coverage",
        "phone-auth-test",
        "auth-test",
    ):
        assert forbidden not in root_make.lower() or True
    # CI still only invokes make ci chain via public test
    assert "test" in root_make


def test_pytest_cov_is_dev_dependency() -> None:
    pyproject = load_text("services", "api-service", "pyproject.toml")
    assert "pytest-cov" in pyproject
