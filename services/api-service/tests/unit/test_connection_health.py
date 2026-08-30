"""Connection verify, catalog intersection, health hysteresis, probe budget."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.domain.connections.health import (
    FAIL_THRESHOLD,
    HealthService,
    ProbeOutcome,
    ScriptedProbe,
    apply_health,
    intersect_catalog,
    redact_detail,
)
from app.domain.connections.models import ConnectionRecord
from app.domain.connections.service import ConnectionError, ConnectionService
from app.domain.connections.store import MemoryConnectionStore
from app.domain.sellerkeys.crypto import CredentialEncryptor

SECRET_OK = "sk-ok-legal-credential"
SECRET_BAD = "sk-invalid-credential"
SECRET_FORB = "sk-forbidden-credential"
SECRET_REGION = "sk-region-mismatch"
SECRET_RL = "sk-rate-limited"
SECRET_FAULT = "sk-upstream-fault"

CATALOG = {
    "catalog_major": 1,
    "records": [
        {
            "provider": "openai",
            "stability": "stable",
            "path_template": "/v1/chat/completions",
            "capability_tags": [],
        },
        {
            "provider": "openai",
            "stability": "stable",
            "path_template": "/v1/assistants",
            "capability_tags": ["control_plane"],
        },
        {
            "provider": "openai",
            "stability": "beta",
            "path_template": "/v1/responses",
            "capability_tags": [],
        },
    ],
}

DISCOVERED = [
    {
        "path_template": "/v1/chat/completions",
        "model": "gpt-test",
        "protocol": "openai",
    },
    {"path_template": "/v1/assistants", "model": "asst", "protocol": "openai"},
    {"path_template": "/v1/responses", "model": "o", "protocol": "openai"},
    {"path_template": "/v1/not-in-catalog", "model": "x", "protocol": "openai"},
]


def _enc() -> CredentialEncryptor:
    return CredentialEncryptor(b"k" * 32, "v1")


def _probe() -> ScriptedProbe:
    p = ScriptedProbe()
    p.by_secret[SECRET_OK] = ProbeOutcome("ok", DISCOVERED, redacted_detail="ok")
    p.by_secret[SECRET_BAD] = ProbeOutcome("invalid_credential", [])
    p.by_secret[SECRET_FORB] = ProbeOutcome("forbidden", [])
    p.by_secret[SECRET_REGION] = ProbeOutcome("region_mismatch", [])
    p.by_secret[SECRET_RL] = ProbeOutcome("rate_limited", [])
    p.by_secret[SECRET_FAULT] = ProbeOutcome("upstream_fault", [])
    return p


def _stack(probe: ScriptedProbe | None = None):
    store = MemoryConnectionStore()
    conn = ConnectionService(
        _enc(),
        b"f" * 32,
        store=store,
        resolver=lambda _h, _p: ["1.1.1.1"],
    )
    health = HealthService(conn, probe or _probe(), catalog=CATALOG, budget=8)
    return conn, health, store


def _create(conn: ConnectionService, secret: str = SECRET_OK) -> ConnectionRecord:
    return conn.create(
        seller_id=uuid.uuid4(),
        provider="openai",
        supply_mode="shared",
        secret=secret,
        role="seller",
        workspace="seller",
        request_id="c1",
    )


def test_six_categories_distinct() -> None:
    conn, health, _ = _stack()
    mapping = {
        SECRET_OK: ("ok", "healthy"),
        SECRET_BAD: ("invalid_credential", "unhealthy"),
        SECRET_FORB: ("forbidden", "unhealthy"),
        SECRET_REGION: ("region_mismatch", "unhealthy"),
        SECRET_RL: ("rate_limited", "degraded"),
        SECRET_FAULT: ("upstream_fault", "unhealthy"),
    }
    for secret, (cat, state) in mapping.items():
        rec = _create(conn, secret)
        out = health.verify(
            connection_id=rec.connection_id,
            seller_id=rec.seller_account_id,
            role="seller",
            workspace="seller",
            request_id="v1",
            immediate=True,
        )
        assert out["category"] == cat
        assert out["health_state"] == state
        assert SECRET_OK not in str(out)
        assert secret not in str(out["detail"])


def test_buyer_cannot_verify() -> None:
    conn, health, _ = _stack()
    rec = _create(conn)
    with pytest.raises(ConnectionError) as exc:
        health.verify(
            connection_id=rec.connection_id,
            seller_id=rec.seller_account_id,
            role="both",
            workspace="buyer",
            request_id="v",
        )
    assert exc.value.code == "FORBIDDEN_ROLE"


def test_snapshot_intersects_catalog_and_versions() -> None:
    conn, health, store = _stack()
    rec = _create(conn, SECRET_OK)
    health.verify(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="s1",
    )
    snaps = store.list_snapshots(rec.connection_id)
    assert len(snaps) == 1
    paths = {c["path_template"] for c in snaps[0].capabilities}
    assert paths == {"/v1/chat/completions"}
    assert "/v1/assistants" not in paths
    assert "/v1/responses" not in paths
    assert "/v1/not-in-catalog" not in paths
    health.verify(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="s2",
    )
    snaps = store.list_snapshots(rec.connection_id)
    assert [s.version for s in snaps] == [1, 2]
    fact = health.health_fact(rec.connection_id)
    assert fact is not None
    assert fact.routable is True


def test_empty_snapshot_not_routable() -> None:
    assert intersect_catalog("openai", DISCOVERED, CATALOG)
    empty = intersect_catalog("openai", [{"path_template": "/nope"}], CATALOG)
    assert empty == []
    conn, health, _ = _stack()
    rec = _create(conn, SECRET_BAD)
    health.verify(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="x",
    )
    fact = health.health_fact(rec.connection_id)
    assert fact is not None
    assert fact.routable is False


def test_single_fault_does_not_unhealthy_from_healthy() -> None:
    rec = ConnectionRecord(
        connection_id=uuid.uuid4(),
        seller_account_id=uuid.uuid4(),
        provider="openai",
        supply_mode="shared",
        auth_type="api_key",
        base_url="https://api.openai.com",
        region=None,
        purpose=None,
        project_number=None,
        location=None,
        nonce=b"n",
        ciphertext=b"c",
        tag=b"t",
        key_version="v1",
        credential_fingerprint="ab" * 16,
        credential_version=1,
        status="active",
        health_state="healthy",
        consecutive_successes=2,
        consecutive_failures=0,
    )
    apply_health(rec, "upstream_fault", immediate=False)
    assert rec.health_state == "degraded"
    apply_health(rec, "upstream_fault", immediate=False)
    assert rec.health_state == "degraded"
    apply_health(rec, "upstream_fault", immediate=False)
    assert rec.consecutive_failures >= FAIL_THRESHOLD
    assert rec.health_state == "unhealthy"


def test_probe_budget_1000() -> None:
    conn, health, store = _stack()
    now = datetime.now(timezone.utc)
    for _ in range(1000):
        rec = ConnectionRecord(
            connection_id=uuid.uuid4(),
            seller_account_id=uuid.uuid4(),
            provider="openai",
            supply_mode="shared",
            auth_type="api_key",
            base_url="https://api.openai.com",
            region=None,
            purpose=None,
            project_number=None,
            location=None,
            nonce=b"n",
            ciphertext=b"c",
            tag=b"t",
            key_version="v1",
            credential_fingerprint="ab" * 16,
            credential_version=1,
            status="active",
            next_probe_at=now,
        )
        store.create(rec)
    due = store.list_probe_due(now, limit=8)
    assert len(due) == 8
    n = health.tick(now)
    assert n <= 8


def test_manual_reverify_recovers_immediately() -> None:
    probe = _probe()
    conn, health, _ = _stack(probe)
    rec = _create(conn, SECRET_BAD)
    out = health.verify(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="bad",
        immediate=True,
    )
    assert out["health_state"] == "unhealthy"
    rec2 = conn.replace_credential(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        secret=SECRET_OK,
        expected_version=1,
        role="seller",
        workspace="seller",
        request_id="rep",
    )
    probe.by_secret[SECRET_OK] = ProbeOutcome("ok", DISCOVERED)
    recovered = health.verify(
        connection_id=rec2.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="ok",
        immediate=True,
    )
    assert recovered["health_state"] == "healthy"


def test_redact_secret_and_audit(caplog: pytest.LogCaptureFixture) -> None:
    assert "[redacted]" in redact_detail("Authorization: Bearer sk-live-abc")
    conn, health, store = _stack()
    rec = _create(conn, SECRET_OK)
    with caplog.at_level("INFO"):
        health.verify(
            connection_id=rec.connection_id,
            seller_id=rec.seller_account_id,
            role="seller",
            workspace="seller",
            request_id="r",
        )
    blob = str(store.audits)
    assert SECRET_OK not in blob
    assert SECRET_OK not in caplog.text


def test_deleted_not_verifiable() -> None:
    conn, health, _ = _stack()
    rec = _create(conn)
    conn.delete(
        connection_id=rec.connection_id,
        seller_id=rec.seller_account_id,
        role="seller",
        workspace="seller",
        request_id="d",
    )
    with pytest.raises(ConnectionError):
        health.verify(
            connection_id=rec.connection_id,
            seller_id=rec.seller_account_id,
            role="seller",
            workspace="seller",
            request_id="v",
        )
