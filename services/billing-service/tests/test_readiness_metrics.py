"""Billing Service PostgreSQL readiness probe metrics tests (SF02/T054).

Covers the three contract-mandated instruments:
``tokenmarket_postgres_readiness_probes_total``,
``tokenmarket_postgres_readiness_probe_failures_total``, and
``tokenmarket_postgres_readiness_probe_duration_seconds``. Counters are
process-global, so every assertion uses before/after deltas. Labels must stay
bounded and secret-free; no label may carry configuration or exception data.
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from app.database import ProbeErrorCategory, ProbeOutcome

_PROBES = "tokenmarket_postgres_readiness_probes_total"
_FAILURES = "tokenmarket_postgres_readiness_probe_failures_total"
_DURATION_COUNT = "tokenmarket_postgres_readiness_probe_duration_seconds_count"
_DURATION_SUM = "tokenmarket_postgres_readiness_probe_duration_seconds_sum"
_FAMILIES = frozenset(
    {
        "tokenmarket_postgres_readiness_probes",
        "tokenmarket_postgres_readiness_probe_failures",
        "tokenmarket_postgres_readiness_probe_duration_seconds",
    }
)


def _sample(name: str) -> float:
    value = REGISTRY.get_sample_value(name)
    assert value is not None, f"missing metric {name}"
    return float(value)


def _snapshot() -> tuple[float, float, float, float]:
    return (
        _sample(_PROBES),
        _sample(_FAILURES),
        _sample(_DURATION_COUNT),
        _sample(_DURATION_SUM),
    )


def test_successful_probe_increments_total_and_duration_only(
    readiness_client, make_probe
) -> None:
    probe = make_probe()
    before = _snapshot()
    with readiness_client(probe) as client:
        assert client.get("/health/ready").status_code == 200
    after = _snapshot()
    assert after[0] == before[0] + 1
    assert after[1] == before[1]
    assert after[2] == before[2] + 1
    assert after[3] >= before[3]


def test_failed_probe_increments_total_failures_and_duration(
    readiness_client, make_probe
) -> None:
    probe = make_probe([ProbeOutcome(ok=False, category=ProbeErrorCategory.AUTH)])
    before = _snapshot()
    with readiness_client(probe) as client:
        assert client.get("/health/ready").status_code == 503
    after = _snapshot()
    assert after[0] == before[0] + 1
    assert after[1] == before[1] + 1
    assert after[2] == before[2] + 1
    assert after[3] >= before[3]


def test_invalid_config_probe_counts_as_failure(
    readiness_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    before = _snapshot()
    with readiness_client() as client:
        assert client.get("/health/ready").status_code == 503
    after = _snapshot()
    assert after[0] == before[0] + 1
    assert after[1] == before[1] + 1
    assert after[2] == before[2] + 1


def test_recovery_increments_total_without_new_failure(
    readiness_client, make_probe
) -> None:
    probe = make_probe([ProbeOutcome(ok=False, category=ProbeErrorCategory.TIMEOUT)])
    before = _snapshot()
    with readiness_client(probe) as client:
        assert client.get("/health/ready").status_code == 503
        assert client.get("/health/ready").status_code == 200
    after = _snapshot()
    assert after[0] == before[0] + 2
    assert after[1] == before[1] + 1
    assert after[2] == before[2] + 2


def test_probe_metrics_have_no_labels_and_no_secret_content(
    readiness_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Probe metric families are label-free; config canaries never surface."""
    canary = "tm_local_labelcanary123"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql+psycopg2://user:{canary}@127.0.0.1:5544/db",
    )
    with readiness_client() as client:
        assert client.get("/health/ready").status_code == 503
        body = client.get("/metrics").text
    for family in REGISTRY.collect():
        if family.name not in _FAMILIES:
            continue
        assert family.samples, f"{family.name} has no samples"
        for sample in family.samples:
            # Bounded labels only: counters carry none; the histogram may
            # carry just the standard finite ``le`` bucket bound. No URL,
            # username, database, exception, SQL, password, or workspace
            # value may ever appear as a label name or value.
            assert set(sample.labels.keys()) <= {
                "le"
            }, f"{sample.name} carries unbounded labels {sample.labels}"
            if "le" in sample.labels:
                assert sample.labels["le"] == "+Inf" or float(sample.labels["le"]) > 0
    assert canary not in body
    assert "psycopg2" not in body
    assert "postgresql://" not in body
    assert "127.0.0.1" not in body
