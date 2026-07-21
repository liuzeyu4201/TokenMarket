"""Deterministic performance-harness tests for the SF02 lifecycle (T025).

Executes the shared cross-platform performance harness (T035) against the
real Docker daemon with predeclared trial accounting:

- one predeclared batch of 20 valid cold trials: images are verified present
  before timing, every trial runs in a fresh disposable project with fresh
  isolated test-owned volumes, and at least 19 of 20 must make all three
  dependencies ready within the 60-second readiness window (image timing
  excluded by construction);
- ten healthy repeat-start confirmations on one healthy project: each must
  finish within 15 seconds without registry access, and the exact resource
  identities (containers, network, named volumes) must not change.

Aggregate statistics are printed for the acceptance record and embedded in
assertion messages so a failure carries its own evidence.
"""

from __future__ import annotations

from .conftest import PerformanceHarness, RealComposeProjectFactory


async def test_cold_start_batch_predeclared_twenty_trials(
    performance_harness: PerformanceHarness,
) -> None:
    report = await performance_harness.run_cold_batch()
    print(f"\n{report.summary()}")
    for record in report.records:
        print(
            f"  trial {record.trial:02d}: status={record.status} "
            f"readiness={record.readiness_seconds:.2f}s wall={record.wall_seconds:.2f}s "
            f"correlation_id={record.correlation_id}"
        )
    assert (
        report.valid_trials == report.declared_trials == 20
    ), "every predeclared valid trial must be counted"
    failures = [record for record in report.records if record.status != "PASSED"]
    assert not failures, f"cold trials failed: {failures!r}"
    assert report.within_budget_count >= report.required_within_budget, report.summary()


async def test_ten_healthy_repeats_within_fifteen_seconds(
    real_compose_project_factory: RealComposeProjectFactory,
    performance_harness: PerformanceHarness,
) -> None:
    project = real_compose_project_factory.new()
    cold = await real_compose_project_factory.start(project)
    assert cold.status == "PASSED"

    report = await performance_harness.run_healthy_repeats(project)
    print(f"\n{report.summary()}")
    for record in report.records:
        print(
            f"  repeat {record.repeat:02d}: status={record.status} "
            f"wall={record.wall_seconds:.2f}s pulled={record.pulled}"
        )
    assert report.snapshot_before == report.snapshot_after, (
        f"resource identities must not change across repeats: "
        f"{report.snapshot_before!r} != {report.snapshot_after!r}"
    )
    assert len(report.snapshot_after.containers) == 3
    assert len(report.snapshot_after.networks) == 1
    assert len(report.snapshot_after.volumes) == 2
    pulled = [record for record in report.records if record.pulled]
    assert not pulled, f"healthy repeats must not contact the registry: {pulled!r}"
    assert report.within_budget_count == report.declared_repeats == 10, report.summary()
