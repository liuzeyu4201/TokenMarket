"""Repository license is Apache-2.0; first-party package metadata must match."""

from __future__ import annotations

import json

from .helpers import load_text


def test_root_license_is_official_apache_2_0() -> None:
    text = load_text("LICENSE")
    assert "Apache License" in text
    assert "Version 2.0, January 2004" in text
    assert "END OF TERMS AND CONDITIONS" in text
    assert "Proprietary" not in text
    assert "All rights reserved" not in text


def test_notice_declares_apache_2_0() -> None:
    text = load_text("NOTICE")
    assert "Apache License, Version 2.0" in text
    assert "TokenMarket" in text


def test_readme_declares_apache_2_0() -> None:
    assert "Apache License 2.0" in load_text("README.md")
    assert "Apache License 2.0" in load_text("README.en.md")
    assert "Proprietary" not in load_text("README.md")
    assert "Proprietary" not in load_text("README.en.md")


def test_first_party_python_packages_declare_apache_2_0() -> None:
    paths = (
        ("services", "api-service", "pyproject.toml"),
        ("services", "admin-service", "pyproject.toml"),
        ("services", "billing-service", "pyproject.toml"),
        ("tools", "workflow", "pyproject.toml"),
    )
    for parts in paths:
        text = load_text(*parts)
        assert "Apache-2.0" in text, parts
        assert "Proprietary" not in text, parts
        assert "LicenseRef-Proprietary" not in text, parts


def test_frontend_package_declares_apache_2_0() -> None:
    pkg = json.loads(load_text("frontend", "package.json"))
    assert pkg.get("license") == "Apache-2.0"
