"""Landing docs must describe shipped V0.2, not a V0.1-only scaffold.

Reads the real repository files. Does not freeze whole README bodies.
Desensitization findings are formatted as path:line:kind — never secret values.
"""

from __future__ import annotations

from workflow.security import (format_desense_findings,
                               load_gitleaks_allowlist_patterns,
                               scan_text_for_desensitization)

from .helpers import find_repo_root, load_text

LANDING_FILES: tuple[tuple[str, ...], ...] = (
    ("README.md",),
    ("README.en.md",),
    ("QUICKSTART.md",),
    ("QUICKSTART.en.md",),
    ("docs", "README.md"),
    ("docs", "README.en.md"),
    ("docs", "architecture", "README.md"),
    ("docs", "architecture", "README.en.md"),
    ("docs", "architecture", "overview.md"),
    ("docs", "architecture", "overview.en.md"),
    ("docs", "api", "README.md"),
    ("docs", "api", "README.en.md"),
    ("docs", "product", "README.md"),
    ("docs", "product", "README.en.md"),
    ("services", "proxy-gateway", "README.md"),
    ("services", "api-service", "README.md"),
    ("services", "billing-service", "README.md"),
    ("services", "admin-service", "README.md"),
    ("frontend", "README.md"),
    (".env.example",),
)

_STALE_CURRENT = (
    "V0.1 技术验证",
    "V0.1 technical validation",
    "工作台占位",
    "dashboard placeholder",
    "计费服务仍为骨架",
    "billing service remains a scaffold",
    "billing service scaffold (SF01)",
    "TokenMarket admin service scaffold (SF01)",
)


def _joined(*parts: str) -> str:
    return "/".join(parts)


def test_root_readme_describes_v02_sandbox_not_v01_validation() -> None:
    zh = load_text("README.md")
    en = load_text("README.en.md")
    assert "V0.1 技术验证" not in zh
    assert "V0.1 technical validation" not in en
    assert "V0.2 交易沙盒" in zh
    assert "V0.2 trading sandbox" in en
    for path in ("/openai/*", "/anthropic/*", "/vertex/*"):
        assert path in zh
        assert path in en
    assert "无充值/支付/Escrow/提现" in zh
    assert "no recharge/payment/Escrow/withdraw" in en
    assert "Apache License 2.0" in zh
    assert "公开上线仍须" in zh


def test_related_landing_pages_are_not_scaffold_baseline() -> None:
    blobs = []
    for parts in LANDING_FILES:
        blobs.append((parts, load_text(*parts)))
    joined = "\n".join(text for _parts, text in blobs)
    for stale in _STALE_CURRENT:
        assert stale not in joined, stale
    assert "/openai/*" in joined
    billing = load_text("services", "billing-service", "README.md").lower()
    assert "test-quota ledger" in billing or "测试额度账本" in billing
    assert "scaffold (sf01)" not in billing
    frontend = load_text("frontend", "README.md")
    assert "/projects" in frontend
    assert "/admin/login" in frontend
    gateway = load_text("services", "proxy-gateway", "README.md")
    assert "/openai/*" in gateway
    assert "volcano" in gateway.lower()


def test_landing_files_are_desensitized() -> None:
    repo = find_repo_root()
    allowlist = load_gitleaks_allowlist_patterns(repo / ".gitleaks.toml")
    findings = []
    for parts in LANDING_FILES:
        rel = _joined(*parts)
        text = load_text(*parts)
        findings.extend(scan_text_for_desensitization(rel, text, allowlist=allowlist))
    rendered = format_desense_findings(findings)
    assert "sk-" not in rendered
    assert "tm_local_" not in rendered
    assert findings == [], rendered


def test_env_example_stays_unusable_placeholder() -> None:
    text = load_text(".env.example")
    assert "replace-me" in text
    assert ".env.local" in text
    assert "sk-live-" not in text
