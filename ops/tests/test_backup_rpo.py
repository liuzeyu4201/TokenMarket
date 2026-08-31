"""SF33 backup RPO/RTO contract checks."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESTORE = REPO / "ops" / "backup" / "postgres-restore.md"


def test_rpo_rto_declared() -> None:
    text = RESTORE.read_text(encoding="utf-8")
    assert "RPO" in text
    assert "5 分钟" in text
    assert "RTO" in text
    assert "30 分钟" in text
    assert "Redis" in text or "SoR" in text
