"""Unit tests for make start/stop scope, ports, and process plan."""

from __future__ import annotations

import pytest

from workflow.local_stack.lifecycle import start_local
from workflow.local_stack.logging_util import StartLog
from workflow.local_stack.ports import resolve_ports
from workflow.local_stack.processes import ServiceSpec, _service_fingerprint, build_service_specs
from workflow.local_stack.scope import DEFAULT_SCOPE, LocalScopeError, parse_local_scope


class TestLocalScope:
    def test_default_is_all(self) -> None:
        assert parse_local_scope(None).value == DEFAULT_SCOPE == "all"
        assert parse_local_scope("").value == "all"
        assert parse_local_scope("  ").value == "all"

    def test_valid_scopes(self) -> None:
        for value in ("all", "apps", "ALL"):
            scope = parse_local_scope(value)
            assert scope.value == value.lower()

    def test_all_wants_both(self) -> None:
        scope = parse_local_scope("all")
        assert scope.wants_stack and scope.wants_process

    def test_apps_only(self) -> None:
        scope = parse_local_scope("apps")
        assert scope.wants_process and not scope.wants_stack

    def test_invalid_scope(self) -> None:
        with pytest.raises(LocalScopeError) as exc:
            parse_local_scope("deploy")
        assert exc.value.code == "INVALID_CONFIG"

    def test_apps_start_fails_when_env_local_is_missing(self, tmp_path, capsys) -> None:
        result = start_local(tmp_path, scope="apps", plain=True)
        assert result == 1
        output = capsys.readouterr().out
        assert "INVALID_CONFIG" in output
        assert ".env.local is required" in output


class TestPorts:
    def test_defaults(self) -> None:
        ports = resolve_ports()
        assert ports.api == 8000
        assert ports.frontend == 5173
        assert ports.gateway == 8080

    def test_override(self) -> None:
        ports = resolve_ports({"API_HOST_PORT": "18000", "FRONTEND_HOST_PORT": "15173"})
        assert ports.api == 18000
        assert ports.frontend == 15173

    def test_middleware_ports_come_from_validated_local_config(self) -> None:
        ports = resolve_ports(
            {"POSTGRES_HOST_PORT": "25432", "API_HOST_PORT": "18000"},
            middleware_ports={
                "postgres": 15432,
                "redis": 16379,
                "grafana": 13000,
            },
        )
        assert ports.postgres == 15432
        assert ports.redis == 16379
        assert ports.grafana == 13000
        assert ports.api == 18000

    def test_collision_rejected(self) -> None:
        with pytest.raises(ValueError, match="port collision"):
            resolve_ports({"API_HOST_PORT": "8080", "GATEWAY_HOST_PORT": "8080"})


class TestServiceSpecs:
    def test_five_services(self, tmp_path) -> None:
        ports = resolve_ports()
        specs = build_service_specs(tmp_path, ports, env_local={})
        ids = [s.id for s in specs]
        assert ids == [
            "proxy-gateway",
            "api-service",
            "billing-service",
            "admin-service",
            "frontend",
        ]
        api = next(s for s in specs if s.id == "api-service")
        assert "--port" in api.argv
        assert str(ports.api) in api.argv

    def test_config_fingerprint_changes_without_storing_secret(self, tmp_path) -> None:
        ports = resolve_ports()
        first_secret = "tm_local_" + ("a" * 32)
        second_secret = "tm_local_" + ("b" * 32)
        first = build_service_specs(
            tmp_path,
            ports,
            env_local={
                "DATABASE_URL": (f"postgresql://app:{first_secret}@127.0.0.1:5432/tokenmarket"),
                "REDIS_URL": (f"redis://default:{first_secret}@127.0.0.1:6379/0"),
            },
        )
        second = build_service_specs(
            tmp_path,
            ports,
            env_local={
                "DATABASE_URL": (f"postgresql://app:{second_secret}@127.0.0.1:5432/tokenmarket"),
                "REDIS_URL": (f"redis://default:{second_secret}@127.0.0.1:6379/0"),
            },
        )

        first_api = next(spec for spec in first if spec.id == "api-service")
        second_api = next(spec for spec in second if spec.id == "api-service")
        first_fingerprint = _service_fingerprint(first_api)
        second_fingerprint = _service_fingerprint(second_api)

        assert first_fingerprint != second_fingerprint
        assert len(first_fingerprint) == 64
        assert first_secret not in first_fingerprint
        assert second_secret not in second_fingerprint

    def test_changed_fingerprint_restarts_managed_process(
        self,
        tmp_path,
        monkeypatch,
    ) -> None:
        from workflow.local_stack import processes

        repo_root = tmp_path / "repo"
        service_dir = repo_root / "service"
        service_dir.mkdir(parents=True)
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()
        spec = ServiceSpec(
            id="example",
            cwd_relative="service",
            port=19000,
            health_path=None,
            argv=["example", "--port", "19000"],
            env={"PORT": "19000", "DATABASE_URL": "new-secret"},
            managed_env={"PORT": "19000", "DATABASE_URL": "new-secret"},
        )
        processes.write_state(
            runtime_dir,
            {
                "services": {
                    "example": {
                        "pid": 123,
                        "port": 19000,
                        "cwd": "service",
                        "config_fingerprint": "old-fingerprint",
                    }
                }
            },
        )
        alive = {123: True, 456: True}
        terminated: list[int] = []

        monkeypatch.setattr(
            processes,
            "build_service_specs",
            lambda *args, **kwargs: [spec],
        )
        monkeypatch.setattr(
            processes,
            "_pid_alive",
            lambda pid: alive.get(pid, False),
        )
        monkeypatch.setattr(processes, "_port_open", lambda *args, **kwargs: False)
        monkeypatch.setattr(processes, "_service_healthy", lambda value: True)

        def fake_terminate(pid, log, service_id) -> None:
            terminated.append(pid)
            alive[pid] = False

        class FakeProcess:
            pid = 456

        monkeypatch.setattr(processes, "_terminate_pid", fake_terminate)
        monkeypatch.setattr(
            processes.subprocess,
            "Popen",
            lambda *args, **kwargs: FakeProcess(),
        )

        result = processes.start_processes(
            repo_root,
            runtime_dir,
            resolve_ports(),
            StartLog(action="start", scope="apps", plain=True),
            env_local={},
            ready_timeout_s=0.1,
        )

        assert result == 0
        assert terminated == [123]
        saved = processes.read_state(runtime_dir)["services"]["example"]
        assert saved["pid"] == 456
        assert saved["config_fingerprint"] == _service_fingerprint(spec)
        assert "new-secret" not in str(saved)
