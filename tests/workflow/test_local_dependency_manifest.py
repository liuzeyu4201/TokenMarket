"""Local dependency manifest validation tests (T010).

Every test starts from a deep copy of the reviewed real manifest in
``ops/workflow/local-dependencies.json`` and mutates exactly one fact. The
validator must accept the unmutated copy and fail closed — with
``ManifestValidationError`` — on placeholder/tag-only/leaf-only digest
identities, missing or extra platform children, extra or reordered
dependencies, unsafe runtime facts, invalid UID/GID values, timeout drift,
and storage-class violations defined by
``contracts/local-dependency-manifest.schema.json``.

These tests fail until T014 implements manifest loading and the exact
three-dependency validator in ``tools/workflow/local_env/models.py``.
"""

from __future__ import annotations

import copy
import importlib
from typing import Any

import pytest

from .helpers import load_json


def _models() -> Any:
    try:
        return importlib.import_module("workflow.local_env.models")
    except ImportError as exc:
        pytest.fail(f"workflow.local_env.models is not implemented yet (T014): {exc}")


def _parse(data: Any) -> Any:
    return _models().parse_manifest(data)


def _validation_error() -> Any:
    return _models().ManifestValidationError


@pytest.fixture
def manifest_data() -> dict[str, Any]:
    """A deep copy of the reviewed manifest; each test mutates its own copy."""
    return copy.deepcopy(load_json("ops", "workflow", "local-dependencies.json"))


def _postgres(data: dict[str, Any]) -> dict[str, Any]:
    return data["dependencies"][0]


def _redis(data: dict[str, Any]) -> dict[str, Any]:
    return data["dependencies"][1]


def _grafana(data: dict[str, Any]) -> dict[str, Any]:
    return data["dependencies"][2]


def _valid_digest(seed: str) -> str:
    return "sha256:" + (seed * 64)[:64]


class TestAcceptedManifest:
    def test_real_manifest_is_accepted(self, manifest_data: dict[str, Any]) -> None:
        manifest = _parse(manifest_data)
        assert [d.id.value for d in manifest.dependencies] == [
            "postgres",
            "redis",
            "grafana",
        ]

    def test_deep_copy_is_accepted(self, manifest_data: dict[str, Any]) -> None:
        _parse(copy.deepcopy(manifest_data))


class TestDigestIdentity:
    def test_placeholder_zero_digest_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["index_digest"] = "sha256:" + "0" * 64
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_placeholder_text_digest_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["index_digest"] = "sha256:PLACEHOLDER_INDEX_DIGEST"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_single_nibble_digest_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["index_digest"] = "sha256:" + "f" * 64
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_uppercase_digest_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["index_digest"] = "sha256:" + "A" * 64
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_non_sha256_algorithm_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["index_digest"] = "sha512:" + "ab" * 32
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_tag_only_missing_index_digest_rejected(self, manifest_data: dict[str, Any]) -> None:
        del _postgres(manifest_data)["index_digest"]
        with pytest.raises(_validation_error()) as excinfo:
            _parse(manifest_data)
        assert "index_digest" in excinfo.value.path

    def test_tag_only_empty_index_digest_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["index_digest"] = ""
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_leaf_only_identity_rejected(self, manifest_data: dict[str, Any]) -> None:
        dep = _postgres(manifest_data)
        dep["index_digest"] = dep["platform_digests"]["linux_amd64"]
        with pytest.raises(_validation_error()) as excinfo:
            _parse(manifest_data)
        assert "index_digest" in excinfo.value.path

    def test_platform_child_digest_pattern_enforced(self, manifest_data: dict[str, Any]) -> None:
        _redis(manifest_data)["platform_digests"]["linux_arm64"] = "sha256:not-a-digest"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)


class TestPlatformChildren:
    def test_missing_platform_child_rejected(self, manifest_data: dict[str, Any]) -> None:
        del _postgres(manifest_data)["platform_digests"]["linux_arm64"]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_missing_platform_digest_map_rejected(self, manifest_data: dict[str, Any]) -> None:
        del _redis(manifest_data)["platform_digests"]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_extra_platform_child_rejected(self, manifest_data: dict[str, Any]) -> None:
        _grafana(manifest_data)["platform_digests"]["linux_ppc64le"] = _valid_digest("cd")
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_required_platforms_reordered_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["required_platforms"] = ["linux/arm64", "linux/amd64"]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_required_platforms_reduced_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["required_platforms"] = ["linux/amd64"]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)


class TestDependencySet:
    def test_fourth_dependency_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["dependencies"].append(copy.deepcopy(_redis(manifest_data)))
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_missing_dependency_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["dependencies"] = manifest_data["dependencies"][:2]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_reordered_dependencies_rejected(self, manifest_data: dict[str, Any]) -> None:
        deps = manifest_data["dependencies"]
        manifest_data["dependencies"] = [deps[1], deps[0], deps[2]]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_duplicate_dependency_rejected(self, manifest_data: dict[str, Any]) -> None:
        deps = manifest_data["dependencies"]
        manifest_data["dependencies"] = [deps[0], copy.deepcopy(deps[0]), deps[2]]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_extra_dependency_field_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["extra_field"] = "not-reviewed"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_unknown_dependency_id_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["id"] = "kafka"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)


class TestUnsafeRuntimes:
    def test_remote_endpoint_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["runtime"]["endpoint"] = "tcp-remote-socket"
        with pytest.raises(_validation_error()) as excinfo:
            _parse(manifest_data)
        assert "endpoint" in excinfo.value.path

    def test_docker_version_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["runtime"]["docker_version"] = "28.0.0"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_compose_version_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["runtime"]["compose_version"] = "4.0.0"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_hosts_reordered_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["runtime"]["hosts"] = ["linux/amd64", "darwin/arm64"]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_hosts_extended_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["runtime"]["hosts"] = [
            "darwin/arm64",
            "linux/amd64",
            "windows/amd64",
        ]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_secret_transport_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["runtime"]["secret_transport"] = "service-environment-variables"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_wildcard_bind_address_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["host_bind_address"] = "0.0.0.0"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_hostname_bind_address_rejected(self, manifest_data: dict[str, Any]) -> None:
        _redis(manifest_data)["host_bind_address"] = "localhost"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)


class TestRuntimeUidGid:
    def test_zero_uid_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["runtime_uid"] = 0
        with pytest.raises(_validation_error()) as excinfo:
            _parse(manifest_data)
        assert "runtime_uid" in excinfo.value.path

    def test_negative_gid_rejected(self, manifest_data: dict[str, Any]) -> None:
        _redis(manifest_data)["runtime_gid"] = -1
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_string_uid_rejected(self, manifest_data: dict[str, Any]) -> None:
        _grafana(manifest_data)["runtime_uid"] = "472"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_bool_uid_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["runtime_uid"] = True
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_uid_policy_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _grafana(manifest_data)["runtime_uid_policy"] = "runs-as-root"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)


class TestTimeoutDrift:
    def test_readiness_budget_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["timeouts"]["readiness_budget_seconds"] = 61
        with pytest.raises(_validation_error()) as excinfo:
            _parse(manifest_data)
        assert "readiness_budget_seconds" in excinfo.value.path

    def test_repeat_confirmation_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["timeouts"]["repeat_confirmation_seconds"] = 14
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_stop_operation_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["timeouts"]["stop_operation_seconds"] = 76
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_postgres_grace_period_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["stop_grace_period_seconds"] = 59
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_grafana_grace_period_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _grafana(manifest_data)["stop_grace_period_seconds"] = 45
        with pytest.raises(_validation_error()):
            _parse(manifest_data)


class TestStorageClasses:
    def test_postgres_ephemeral_storage_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["ephemeral_storage"] = copy.deepcopy(
            _grafana(manifest_data)["ephemeral_storage"]
        )
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_postgres_missing_volume_rejected(self, manifest_data: dict[str, Any]) -> None:
        del _postgres(manifest_data)["volume"]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_grafana_volume_rejected(self, manifest_data: dict[str, Any]) -> None:
        _grafana(manifest_data)["volume"] = copy.deepcopy(_redis(manifest_data)["volume"])
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_grafana_missing_tmpfs_rejected(self, manifest_data: dict[str, Any]) -> None:
        del _grafana(manifest_data)["ephemeral_storage"]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_volume_delete_on_down_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["volume"]["delete_on_down"] = True
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_volume_logical_name_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _redis(manifest_data)["volume"]["logical_name"] = "shared-data"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_volume_mount_path_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["volume"]["mount_path"] = "var/lib/postgresql/data"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_tmpfs_mode_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _grafana(manifest_data)["ephemeral_storage"]["mode"] = "0777"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)


class TestDependencyConstDrift:
    def test_postgres_port_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["container_port"] = 5433
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_redis_version_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _redis(manifest_data)["version_tag"] = "7.4.0-bookworm"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_grafana_repository_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _grafana(manifest_data)["repository"] = "docker.io/grafana/grafana-oss"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_host_url_field_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["host_url_field"] = "POSTGRES_URL"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_readiness_probe_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["readiness_probe"] = "tcp-connect-only"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_durability_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        _postgres(manifest_data)["durability"] = "ephemeral"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)


class TestTopLevelStructure:
    def test_extra_top_level_key_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["extra"] = {}
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_missing_timeouts_rejected(self, manifest_data: dict[str, Any]) -> None:
        del manifest_data["timeouts"]
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_schema_version_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["schema_version"] = "1.0.1"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_diagnostic_contract_version_drift_rejected(
        self, manifest_data: dict[str, Any]
    ) -> None:
        manifest_data["diagnostic_contract_version"] = "1.0.0"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_project_prefix_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["project"]["prefix"] = "other"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_workspace_hash_length_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["project"]["workspace_hash_length"] = 16
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_lock_mechanism_drift_rejected(self, manifest_data: dict[str, Any]) -> None:
        manifest_data["project"]["lock_mechanism"] = "none"
        with pytest.raises(_validation_error()):
            _parse(manifest_data)

    def test_non_object_manifest_rejected(self) -> None:
        with pytest.raises(_validation_error()):
            _parse(["not", "an", "object"])
