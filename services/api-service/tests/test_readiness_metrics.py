"""Readiness probe observability tests for api-service (SF02).

The service exposes exactly three PostgreSQL readiness probe metric families
on ``/metrics``: a total counter, a failure counter, and a duration histogram.
Samples never carry URL, username, database, exception, SQL, password, or any
other unbounded label; the families are intentionally label-free.
"""

from __future__ import annotations

from collections.abc import Iterator

from conftest import MakeClient
from prometheus_client.parser import text_string_to_metric_families

from app.database import ProbeErrorCategory, ProbeResult

PROBES_TOTAL = "tokenmarket_postgres_readiness_probes_total"
PROBE_FAILURES_TOTAL = "tokenmarket_postgres_readiness_probe_failures_total"
PROBE_DURATION = "tokenmarket_postgres_readiness_probe_duration_seconds"
PROBE_FAMILIES = (PROBES_TOTAL, PROBE_FAILURES_TOTAL, PROBE_DURATION)

EXPECTED_BUCKETS = (
    "0.005",
    "0.01",
    "0.025",
    "0.05",
    "0.1",
    "0.25",
    "0.5",
    "1.0",
    "2.0",
    "5.0",
)


def _samples(body: str) -> Iterator[tuple[str, str, dict[str, str], float]]:
    for family in text_string_to_metric_families(body):
        for sample in family.samples:
            yield family.name, sample.name, sample.labels, sample.value


def _value(body: str, sample_name: str) -> float:
    for _family, name, labels, value in _samples(body):
        if name == sample_name and not labels:
            return value
    raise AssertionError(f"missing unlabelled sample for {sample_name}")


def _histogram_count(body: str) -> float:
    count_name = f"{PROBE_DURATION}_count"
    for _family, name, labels, value in _samples(body):
        if name == count_name and not labels:
            return value
    raise AssertionError("missing _count sample for probe duration histogram")


def _histogram_sum(body: str) -> float:
    sum_name = f"{PROBE_DURATION}_sum"
    for _family, name, labels, value in _samples(body):
        if name == sum_name and not labels:
            return value
    raise AssertionError("missing _sum sample for probe duration histogram")


def test_successful_probe_increments_total_and_duration_only(
    make_client: MakeClient,
) -> None:
    with make_client() as handle:
        before = handle.client.get("/metrics").text
        response = handle.client.get("/health/ready")
        after = handle.client.get("/metrics").text
    assert response.status_code == 200
    assert _value(after, PROBES_TOTAL) - _value(before, PROBES_TOTAL) == 1
    assert (
        _value(after, PROBE_FAILURES_TOTAL) - _value(before, PROBE_FAILURES_TOTAL) == 0
    )
    assert _histogram_count(after) - _histogram_count(before) == 1
    assert _histogram_sum(after) - _histogram_sum(before) >= 0


def test_failed_probe_increments_total_failures_and_duration(
    make_client: MakeClient,
) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.QUERY))
        before = handle.client.get("/metrics").text
        response = handle.client.get("/health/ready")
        after = handle.client.get("/metrics").text
    assert response.status_code == 503
    assert _value(after, PROBES_TOTAL) - _value(before, PROBES_TOTAL) == 1
    assert (
        _value(after, PROBE_FAILURES_TOTAL) - _value(before, PROBE_FAILURES_TOTAL) == 1
    )
    assert _histogram_count(after) - _histogram_count(before) == 1


def test_recovery_increments_total_without_failure(make_client: MakeClient) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.TIMEOUT))
        failing = handle.client.get("/health/ready")
        assert failing.status_code == 503
        before = handle.client.get("/metrics").text
        recovered = handle.client.get("/health/ready")
        after = handle.client.get("/metrics").text
    assert recovered.status_code == 200
    assert _value(after, PROBES_TOTAL) - _value(before, PROBES_TOTAL) == 1
    assert (
        _value(after, PROBE_FAILURES_TOTAL) - _value(before, PROBE_FAILURES_TOTAL) == 0
    )
    assert _histogram_count(after) - _histogram_count(before) == 1


def test_probe_metrics_have_no_labels(make_client: MakeClient) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.AUTH))
        handle.client.get("/health/ready")
        handle.client.get("/health/ready")
        body = handle.client.get("/metrics").text
    inspected = 0
    for family_name, _name, labels, _value_ignored in _samples(body):
        if family_name not in PROBE_FAMILIES:
            continue
        inspected += 1
        allowed = {"le"} if family_name == PROBE_DURATION else set()
        assert set(labels) <= allowed, (family_name, labels)
    assert inspected > 0


def test_probe_duration_histogram_buckets_are_bounded(
    make_client: MakeClient,
) -> None:
    with make_client() as handle:
        handle.client.get("/health/ready")
        body = handle.client.get("/metrics").text
    bucket_labels = [
        labels["le"]
        for family_name, _name, labels, _v in _samples(body)
        if family_name == PROBE_DURATION and "le" in labels
    ]
    assert bucket_labels
    finite = [le for le in bucket_labels if le != "+Inf"]
    assert tuple(finite) == EXPECTED_BUCKETS
    assert "+Inf" in bucket_labels


def test_probe_metrics_contain_no_configuration_or_exception_data(
    make_client: MakeClient,
) -> None:
    # The env URL carries a distinctive synthetic username; the fake probe
    # then fails. Neither configuration nor failure detail may appear
    # anywhere in the exposition.
    marker_url = "postgresql://markeruser:markerscret@127.0.0.1:65432/markerdatabase"
    with make_client(database_url=marker_url) as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.AUTH))
        handle.client.get("/health/ready")
        body = handle.client.get("/metrics").text
    assert PROBES_TOTAL in body
    assert PROBE_FAILURES_TOTAL in body
    assert PROBE_DURATION in body
    lowered = body.lower()
    for forbidden in (
        "markeruser",
        "markerscret",
        "markerdatabase",
        "postgresql",
        "asyncpg",
        "127.0.0.1",
        "65432",
        "select 1",
        "password",
        "tm_local_",
        "traceback",
    ):
        assert forbidden not in lowered
