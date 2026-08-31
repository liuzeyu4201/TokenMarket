"""Typed entity, state-machine, and serialization-exclusion tests (T011).

Covers the normative entities of
``specs/002-local-dependency-lifecycle/data-model.md``: the manifest and its
three dependency definitions, lifecycle operations and their state machine,
dependency instances, health results, Compose secret material, and the
API/Billing service readiness projection. Entities must be immutable and
typed, transitions must follow the contracted state machines, and secret
values must be excluded from repr, equality, and serialization.

These tests fail until T014 implements the entities in
``tools/workflow/local_env/models.py``.
"""

from __future__ import annotations

import dataclasses
import importlib
from datetime import datetime, timezone
from typing import Any

import pytest

from .helpers import repo_path


def _models() -> Any:
    try:
        return importlib.import_module("workflow.local_env.models")
    except ImportError as exc:
        pytest.fail(f"workflow.local_env.models is not implemented yet (T014): {exc}")


@pytest.fixture
def manifest() -> Any:
    models = _models()
    return models.load_manifest(repo_path("ops", "workflow", "local-dependencies.json"))


def _operation(models: Any, **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "correlation_id": "11111111-2222-3333-4444-555555555555",
        "action": models.LifecycleAction.DEV,
        "project_id": "tokenmarket-abcdef012345",
        "started_at": 100.0,
    }
    kwargs.update(overrides)
    return models.LifecycleOperation(**kwargs)


class TestManifestEntities:
    def test_dependencies_are_typed_and_ordered(self, manifest: Any) -> None:
        models = _models()
        ids = [d.id for d in manifest.dependencies]
        assert ids == [
            models.DependencyId.POSTGRES,
            models.DependencyId.REDIS,
            models.DependencyId.GRAFANA,
        ]

    def test_manifest_constants(self, manifest: Any) -> None:
        assert manifest.schema_version == "1.0.0"
        assert manifest.diagnostic_contract_version == "2.0.0"
        assert manifest.timeouts.readiness_budget_seconds == 60
        assert manifest.timeouts.repeat_confirmation_seconds == 15
        assert manifest.timeouts.stop_operation_seconds == 75
        assert manifest.project.prefix == "tokenmarket"

    def test_image_ref_composition(self, manifest: Any) -> None:
        models = _models()
        postgres = manifest.dependency(models.DependencyId.POSTGRES)
        assert postgres.image_ref == (
            "docker.io/library/postgres:15.18-bookworm@"
            "sha256:b0c5bab0fbba8e0c221f73b1dc6359ec35f8650074377e727299df248fc8ad51"
        )

    def test_dependency_facts(self, manifest: Any) -> None:
        models = _models()
        grafana = manifest.dependency(models.DependencyId.GRAFANA)
        assert grafana.container_port == 3000
        assert grafana.volume is None
        assert grafana.ephemeral_storage is not None
        assert grafana.ephemeral_storage.mode == "0700"
        redis = manifest.dependency(models.DependencyId.REDIS)
        assert redis.volume is not None
        assert redis.volume.delete_on_down is False
        assert redis.ephemeral_storage is None

    def test_manifest_is_immutable(self, manifest: Any) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            manifest.timeouts.readiness_budget_seconds = 61  # type: ignore[misc]

    def test_manifest_equality(self, manifest: Any) -> None:
        models = _models()
        again = models.load_manifest(repo_path("ops", "workflow", "local-dependencies.json"))
        assert manifest == again
        other = models.load_manifest(repo_path("ops", "workflow", "local-dependencies.json"))
        changed = dataclasses.replace(other.timeouts, readiness_budget_seconds=61)
        assert manifest != dataclasses.replace(other, timeouts=changed)


class TestLifecycleOperationStateMachine:
    def test_initial_state(self) -> None:
        models = _models()
        op = _operation(models)
        assert op.status == models.OperationStatus.REQUESTED
        assert op.phase == models.LifecyclePhase.IDENTITY
        assert not op.is_terminal
        assert op.readiness_deadline is None

    def test_legal_start_transitions(self) -> None:
        models = _models()
        op = _operation(models)
        running = op.transition(
            models.OperationStatus.RUNNING, phase=models.LifecyclePhase.PREFLIGHT
        )
        assert running.status == models.OperationStatus.RUNNING
        assert running.phase == models.LifecyclePhase.PREFLIGHT
        succeeded = running.transition(
            models.OperationStatus.SUCCEEDED, phase=models.LifecyclePhase.FINAL
        )
        assert succeeded.is_terminal
        # Frozen entities: the original operation is unchanged.
        assert op.status == models.OperationStatus.REQUESTED

    def test_requested_cannot_jump_to_succeeded(self) -> None:
        models = _models()
        with pytest.raises(models.InvalidStateTransitionError):
            _operation(models).transition(models.OperationStatus.SUCCEEDED)

    def test_requested_rejected_on_lock_contention(self) -> None:
        models = _models()
        rejected = _operation(models).transition(
            models.OperationStatus.REJECTED, diagnostic_code="OPERATION_IN_PROGRESS"
        )
        assert rejected.status == models.OperationStatus.REJECTED
        assert rejected.is_terminal

    def test_running_interrupted_is_retriable_terminal(self) -> None:
        models = _models()
        running = _operation(models).transition(models.OperationStatus.RUNNING)
        interrupted = running.transition(models.OperationStatus.INTERRUPTED)
        assert interrupted.is_terminal

    def test_terminal_states_cannot_transition(self) -> None:
        models = _models()
        running = _operation(models).transition(models.OperationStatus.RUNNING)
        for terminal in (
            models.OperationStatus.SUCCEEDED,
            models.OperationStatus.FAILED,
            models.OperationStatus.INTERRUPTED,
        ):
            op = running.transition(terminal)
            with pytest.raises(models.InvalidStateTransitionError):
                op.transition(models.OperationStatus.RUNNING)

    def test_rejected_is_terminal(self) -> None:
        models = _models()
        rejected = _operation(models).transition(models.OperationStatus.REJECTED)
        with pytest.raises(models.InvalidStateTransitionError):
            rejected.transition(models.OperationStatus.RUNNING)

    def test_readiness_deadline_is_exact(self, monotonic_clock: Any) -> None:
        models = _models()
        op = _operation(models).transition(models.OperationStatus.RUNNING)
        at = monotonic_clock()
        op = op.begin_readiness(at=at, budget_seconds=60)
        assert op.readiness_started_at == at
        assert op.readiness_deadline == at + 60

    def test_readiness_deadline_cannot_be_extended(self, monotonic_clock: Any) -> None:
        models = _models()
        op = _operation(models).transition(models.OperationStatus.RUNNING)
        op = op.begin_readiness(at=monotonic_clock(), budget_seconds=60)
        monotonic_clock.advance(30)
        with pytest.raises(models.InvalidStateTransitionError):
            op.begin_readiness(at=monotonic_clock(), budget_seconds=60)

    def test_remaining_readiness_seconds(self, monotonic_clock: Any) -> None:
        models = _models()
        op = _operation(models).transition(models.OperationStatus.RUNNING)
        op = op.begin_readiness(at=monotonic_clock(), budget_seconds=60)
        monotonic_clock.advance(45)
        assert op.remaining_readiness_seconds(monotonic_clock()) == pytest.approx(15.0)
        monotonic_clock.advance(30)
        assert op.remaining_readiness_seconds(monotonic_clock()) < 0

    def test_negative_duration_rejected(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            _operation(models, duration_ms=-1)


class TestDependencyInstance:
    def test_mutation_requires_valid_owner_labels(self) -> None:
        models = _models()
        foreign = models.DependencyInstance(
            dependency_id=models.DependencyId.POSTGRES,
            state=models.InstanceState.RUNNING,
            owner_labels_valid=False,
        )
        with pytest.raises(models.OwnershipConflictError) as excinfo:
            foreign.authorize_mutation()
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"

    def test_mutation_allowed_for_owned_instance(self) -> None:
        models = _models()
        owned = models.DependencyInstance(
            dependency_id=models.DependencyId.REDIS,
            state=models.InstanceState.RUNNING,
            health=models.InstanceHealth.HEALTHY,
            owner_labels_valid=True,
            image_matches_desired=True,
            volume_attached=True,
        )
        owned.authorize_mutation()

    def test_defaults_are_absent_and_unknown(self) -> None:
        models = _models()
        instance = models.DependencyInstance(dependency_id=models.DependencyId.GRAFANA)
        assert instance.state == models.InstanceState.ABSENT
        assert instance.health == models.InstanceHealth.UNKNOWN
        assert instance.container_id is None

    def test_published_port_bounds(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            models.DependencyInstance(dependency_id=models.DependencyId.POSTGRES, published_port=0)
        with pytest.raises(ValueError):
            models.DependencyInstance(
                dependency_id=models.DependencyId.POSTGRES, published_port=65536
            )
        ok = models.DependencyInstance(
            dependency_id=models.DependencyId.POSTGRES, published_port=5432
        )
        assert ok.published_port == 5432


class TestDependencyHealthResult:
    def _result(self, models: Any, **overrides: Any) -> Any:
        kwargs: dict[str, Any] = {
            "dependency": models.DependencyId.POSTGRES,
            "liveness": models.LivenessState.ALIVE,
            "readiness": models.ReadinessState.READY,
            "probe": models.ProbeKind.POSTGRES_QUERY,
            "checked_at": datetime.now(timezone.utc),
            "duration_ms": 12,
            "code": "OK",
            "safe_reason": "authenticated SELECT 1 returned 1",
        }
        kwargs.update(overrides)
        return models.DependencyHealthResult(**kwargs)

    def test_valid_result(self) -> None:
        models = _models()
        result = self._result(models)
        assert result.readiness == models.ReadinessState.READY

    def test_waiting_state_is_representable(self) -> None:
        models = _models()
        result = self._result(models, readiness=models.ReadinessState.WAITING)
        assert result.readiness == models.ReadinessState.WAITING

    def test_negative_duration_rejected(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._result(models, duration_ms=-1)

    def test_naive_timestamp_rejected(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._result(models, checked_at=datetime(2026, 7, 16, 12, 0, 0))

    def test_non_utc_timestamp_rejected(self) -> None:
        models = _models()
        from datetime import timedelta

        with pytest.raises(ValueError):
            self._result(
                models,
                checked_at=datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone(timedelta(hours=8))),
            )

    def test_safe_reason_is_bounded(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._result(models, safe_reason="x" * 201)
        ok = self._result(models, safe_reason="x" * 200)
        assert len(ok.safe_reason) == 200


class TestComposeSecretMaterial:
    def _material(self, models: Any, secret: str, **overrides: Any) -> Any:
        kwargs: dict[str, Any] = {
            "project_id": "tokenmarket-abcdef012345",
            "purpose": models.SecretPurpose.POSTGRES_PASSWORD,
            "source_field": "DATABASE_URL",
            "container_owner_uid": 999,
            "container_owner_gid": 999,
            "secret": secret,
        }
        kwargs.update(overrides)
        return models.ComposeSecretMaterial(**kwargs)

    def test_secret_never_rendered(self, synthetic_secret: str) -> None:
        models = _models()
        material = self._material(models, synthetic_secret)
        assert synthetic_secret not in repr(material)
        assert synthetic_secret not in str(material)
        assert synthetic_secret not in f"{material!r}"

    def test_secret_excluded_from_equality_and_hash(self, synthetic_secret_factory: Any) -> None:
        models = _models()
        first = self._material(models, synthetic_secret_factory.new())
        second = self._material(models, synthetic_secret_factory.new())
        assert first == second
        assert hash(first) == hash(second)

    def test_metadata_difference_still_unequal(self, synthetic_secret_factory: Any) -> None:
        models = _models()
        first = self._material(models, synthetic_secret_factory.new())
        second = self._material(
            models,
            synthetic_secret_factory.new(),
            purpose=models.SecretPurpose.REDIS_CONFIG,
            source_field="REDIS_URL",
        )
        assert first != second

    def test_release_drops_secret_value(self, synthetic_secret: str) -> None:
        models = _models()
        material = self._material(models, synthetic_secret)
        released = material.release()
        assert released.cleanup_state == models.SecretCleanupState.RELEASED
        assert released.secret == ""
        assert synthetic_secret not in repr(released)
        # Frozen entities: the original mapping is unchanged.
        assert material.cleanup_state == models.SecretCleanupState.IN_MEMORY

    def test_source_field_must_be_a_name_not_a_value(self, synthetic_secret: str) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._material(
                models,
                synthetic_secret,
                source_field=f"DATABASE_URL={synthetic_secret}",
            )
        with pytest.raises(ValueError):
            self._material(models, synthetic_secret, source_field=synthetic_secret)

    def test_in_memory_material_requires_secret(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._material(models, "")

    def test_container_owner_must_be_non_root(self, synthetic_secret: str) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._material(models, synthetic_secret, container_owner_uid=0)

    def test_teardown_placeholder_purpose(self, synthetic_secret: str) -> None:
        models = _models()
        material = self._material(
            models, synthetic_secret, purpose=models.SecretPurpose.TEARDOWN_PLACEHOLDER
        )
        assert material.purpose == models.SecretPurpose.TEARDOWN_PLACEHOLDER


class TestServiceReadinessResult:
    def _dependency(self, models: Any, **overrides: Any) -> Any:
        kwargs: dict[str, Any] = {
            "name": models.DependencyId.POSTGRES,
            "status": models.ServiceReadinessStatus.NOT_READY,
            "code": "DEPENDENCY_NOT_READY",
        }
        kwargs.update(overrides)
        return models.ServiceDependencyResult(**kwargs)

    def _result(self, models: Any, **overrides: Any) -> Any:
        kwargs: dict[str, Any] = {
            "service": models.ReadinessService.API_SERVICE,
            "status": models.ServiceReadinessStatus.READY,
            "version": "0.1.0",
            "request_id": "req-123",
            "http_status": 200,
        }
        kwargs.update(overrides)
        return models.ServiceReadinessResult(**kwargs)

    def test_ready_shape(self) -> None:
        models = _models()
        result = self._result(models)
        assert result.http_status == 200
        assert result.dependencies == ()

    def test_ready_with_dependencies_rejected(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._result(models, dependencies=(self._dependency(models),))

    def test_ready_with_503_rejected(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._result(models, http_status=503)

    def test_not_ready_requires_exactly_one_postgres_result(self) -> None:
        models = _models()
        not_ready = models.ServiceReadinessStatus.NOT_READY
        with pytest.raises(ValueError):
            self._result(models, status=not_ready, http_status=503, dependencies=())
        with pytest.raises(ValueError):
            self._result(
                models,
                status=not_ready,
                http_status=503,
                dependencies=(
                    self._dependency(models),
                    self._dependency(models),
                ),
            )
        with pytest.raises(ValueError):
            self._result(
                models,
                status=not_ready,
                http_status=503,
                dependencies=(self._dependency(models, name=models.DependencyId.REDIS),),
            )
        ok = self._result(
            models,
            status=not_ready,
            http_status=503,
            dependencies=(self._dependency(models),),
        )
        assert ok.http_status == 503

    def test_not_ready_with_200_rejected(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._result(
                models,
                status=models.ServiceReadinessStatus.NOT_READY,
                http_status=200,
                dependencies=(self._dependency(models),),
            )

    def test_dependency_serialization_is_minimal_and_safe(self) -> None:
        models = _models()
        payload = self._dependency(models).to_dict()
        assert payload == {
            "name": "postgres",
            "status": "not_ready",
            "code": "DEPENDENCY_NOT_READY",
        }

    def test_dependency_code_required(self) -> None:
        models = _models()
        with pytest.raises(ValueError):
            self._dependency(models, code="")

    def test_billing_service_representable(self) -> None:
        models = _models()
        result = self._result(models, service=models.ReadinessService.BILLING_SERVICE)
        assert result.service == models.ReadinessService.BILLING_SERVICE
