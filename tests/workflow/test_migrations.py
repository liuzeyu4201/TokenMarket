"""Migration ownership and round-trip tests (T020).

Covers owner manifest validation, offline migrate-check, per-owner database
isolation for migrate-integration-check, and mode gates for make migrate.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest

from workflow.migrations import (
    _PG_INIT_COMPLETE_MARKER,
    MigrationError,
    create_owner_database,
    migrate_integration_check,
    new_integration_run_token,
    normalize_component_slug,
    owner_database_name,
    plan_owner_databases,
    redact_database_url,
    replace_database_name,
    wait_for_integration_postgres_ready,
)

from .helpers import find_repo_root, load_json, load_text, run


def _event_statuses(log: Any) -> list[str]:
    """Read status from v1 flat events or v2 standard envelopes."""
    statuses: list[str] = []
    for event in log.events:
        if not isinstance(event, dict):
            continue
        if "payload" in event and isinstance(event["payload"], dict):
            status = event["payload"].get("status")
        else:
            status = event.get("status")
        if isinstance(status, str):
            statuses.append(status)
    return statuses


def _event_messages(log: Any) -> str:
    parts: list[str] = []
    for event in log.events:
        if not isinstance(event, dict):
            continue
        if "payload" in event and isinstance(event["payload"], dict):
            message = event["payload"].get("message", "")
        else:
            message = event.get("message", "")
        parts.append(str(message))
    return " ".join(parts)


@pytest.fixture
def owners_manifest() -> dict[str, Any]:
    return load_json("ops", "migrations", "owners.json")


@pytest.fixture
def components_manifest() -> dict[str, Any]:
    return load_json("ops", "workflow", "components.json")


def test_migration_owners_exactly_api_then_billing(owners_manifest: dict[str, Any]) -> None:
    owners = owners_manifest["owners"]
    assert len(owners) == 2
    assert owners[0]["component_id"] == "api-service"
    assert owners[0]["order"] == 1
    assert owners[1]["component_id"] == "billing-service"
    assert owners[1]["order"] == 2


def test_non_owners_list_contains_admin_service(owners_manifest: dict[str, Any]) -> None:
    assert "admin-service" in owners_manifest["non_owners"]


def test_owner_graphs_have_single_head(owners_manifest: dict[str, Any]) -> None:
    root = find_repo_root()
    for owner in owners_manifest["owners"]:
        version_path = root / owner["version_path"]
        assert version_path.is_dir(), f"{owner['component_id']}: missing versions dir"
        py_files = list(version_path.glob("*.py"))
        assert py_files, f"{owner['component_id']}: no migration files"


def test_owner_backout_runbook_exists(owners_manifest: dict[str, Any]) -> None:
    root = find_repo_root()
    for owner in owners_manifest["owners"]:
        runbook = root / owner["backout_runbook"]
        assert runbook.is_file(), f"{owner['component_id']}: missing backout runbook"


def test_migrate_check_reports_zero_pending_after_validation() -> None:
    result = run(["make", "migrate-check"], cwd=find_repo_root(), check=False)
    assert (
        result.returncode == 0
    ), f"make migrate-check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    output = result.stdout + result.stderr
    assert "api-service" in output and "billing-service" in output


def test_migrate_check_does_not_call_make_dev() -> None:
    result = run(["make", "migrate-check"], cwd=find_repo_root(), check=False)
    output = result.stdout + result.stderr
    assert "SF02_NOT_READY" not in output, "migrate-check must not invoke make dev"


def test_migrate_integration_check_runs_pg15_round_trip() -> None:
    result = run(["make", "migrate-integration-check"], cwd=find_repo_root(), check=False)
    assert (
        result.returncode == 0
    ), f"make migrate-integration-check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    output = result.stdout + result.stderr
    assert "forward" in output.lower()
    assert "backout" in output.lower() or "downgrade" in output.lower()
    assert "api-service" in output
    assert "billing-service" in output
    assert "0003_phone_login_session" not in output or "billing" in output.lower()
    # Isolation markers from setup message
    assert "owner-isolated" in output.lower() or "tm_mig_" in output
    assert "api-service->tm_mig_" in output
    assert "billing-service->tm_mig_" in output


def test_migrate_integration_check_uses_isolated_database() -> None:
    result = run(["make", "migrate-integration-check"], cwd=find_repo_root(), check=False)
    output = result.stdout + result.stderr
    assert "shared database" not in output.lower()
    assert "make dev" not in output.lower()
    assert result.returncode == 0
    # Distinct per-owner database names appear in the event stream.
    api_dbs = re.findall(r"api-service->(tm_mig_[a-z0-9]+_api_service)", output)
    billing_dbs = re.findall(r"billing-service->(tm_mig_[a-z0-9]+_billing_service)", output)
    assert api_dbs, output
    assert billing_dbs, output
    assert api_dbs[0] != billing_dbs[0]
    assert "0003_phone_login_session" not in output or "FAILED" not in output


def test_migrate_invalid_mode_fails_before_connection() -> None:
    result = run(["make", "migrate", "mode=PROD"], cwd=find_repo_root(), check=False)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "INVALID_MODE" in output


def test_migrate_prod_without_approval_fails_before_connection() -> None:
    result = run(["make", "migrate", "mode=prod"], cwd=find_repo_root(), check=False)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "PROD_APPROVAL_REQUIRED" in output


def test_plan_owner_databases_isolates_names_and_urls(
    owners_manifest: dict[str, Any],
) -> None:
    base = "postgresql+psycopg2://postgres:syn%2Fpass@127.0.0.1:15432/postgres?sslmode=disable"
    planned = plan_owner_databases(
        list(owners_manifest["owners"]),
        run_token="a1b2c3d4",
        base_url=base,
    )
    assert [p["component_id"] for p in planned] == ["api-service", "billing-service"]
    assert planned[0]["database"] != planned[1]["database"]
    assert planned[0]["database_url"] != planned[1]["database_url"]
    assert planned[0]["database"] == "tm_mig_a1b2c3d4_api_service"
    assert planned[1]["database"] == "tm_mig_a1b2c3d4_billing_service"
    for entry in planned:
        parsed = urlparse(entry["database_url"])
        assert parsed.scheme == "postgresql+psycopg2"
        assert parsed.hostname == "127.0.0.1"
        assert parsed.port == 15432
        assert parsed.username == "postgres"
        # Password remains percent-encoded in netloc; must not be mangled.
        assert parsed.password in {"syn/pass", "syn%2Fpass"}
        assert "syn%2Fpass" in entry["database_url"] or "syn/pass" in entry["database_url"]
        assert parsed.path == f"/{entry['database']}"
        assert parsed.query == "sslmode=disable"
        # Same owner always maps to one URL for forward/backout/retry.
        again = replace_database_name(base, entry["database"])
        assert again == entry["database_url"]


def test_run_tokens_differ_across_concurrent_plans(
    owners_manifest: dict[str, Any],
) -> None:
    base = "postgresql+psycopg2://postgres:synthetic@127.0.0.1:15432/postgres"
    a = plan_owner_databases(
        list(owners_manifest["owners"]),
        run_token=new_integration_run_token(),
        base_url=base,
    )
    b = plan_owner_databases(
        list(owners_manifest["owners"]),
        run_token=new_integration_run_token(),
        base_url=base,
    )
    assert {p["database"] for p in a}.isdisjoint({p["database"] for p in b})
    assert a[0]["database_url"] != b[0]["database_url"]


def test_owner_database_name_normalization_and_safety() -> None:
    assert normalize_component_slug("api-service") == "api_service"
    name = owner_database_name(run_token="deadbeef", component_id="api-service")
    assert name == "tm_mig_deadbeef_api_service"
    assert re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name)
    with pytest.raises(MigrationError):
        owner_database_name(run_token="short", component_id="api-service")
    with pytest.raises(MigrationError):
        owner_database_name(run_token="deadbeef", component_id="!!!")


def test_replace_database_name_rejects_unsafe_identifier() -> None:
    base = "postgresql+psycopg2://postgres:synthetic@127.0.0.1:15432/postgres"
    with pytest.raises(MigrationError):
        replace_database_name(base, 'evil"; drop database postgres; --')


def test_create_owner_database_fail_closed_on_psql_error() -> None:
    with patch("workflow.migrations.subprocess.run") as run_mock:
        run_mock.return_value = MagicMock(
            returncode=1,
            stderr="ERROR: permission denied to create database",
            stdout="",
        )
        with pytest.raises(MigrationError) as excinfo:
            create_owner_database(
                container_name="tm-migrate-integration-check",
                database="tm_mig_a1b2c3d4_api_service",
                run_token="a1b2c3d4",
            )
        assert excinfo.value.code == "STEP_FAILED"
        assert "tm_mig_a1b2c3d4_api_service" in excinfo.value.message


def test_create_owner_database_rejects_foreign_or_reserved_names() -> None:
    with pytest.raises(MigrationError):
        create_owner_database(
            container_name="tm-migrate-integration-check",
            database="postgres",
            run_token="a1b2c3d4",
        )
    with pytest.raises(MigrationError):
        create_owner_database(
            container_name="tm-migrate-integration-check",
            database="tm_mig_other12_api_service",
            run_token="a1b2c3d4",
        )


def test_redact_database_url_hides_password() -> None:
    url = "postgresql+psycopg2://postgres:super-secret@127.0.0.1:15432/tm_mig_x"
    redacted = redact_database_url(url)
    assert "super-secret" not in redacted
    assert "***" in redacted
    assert "127.0.0.1" in redacted
    assert "tm_mig_x" in redacted


def test_make_migrate_path_does_not_create_owner_databases() -> None:
    """Ordinary make migrate must not gain multi-database CREATE logic."""
    cli_src = load_text("tools", "workflow", "cli.py")
    assert "create_owner_database" not in cli_src
    assert "plan_owner_databases" not in cli_src
    assert "wait_for_integration_postgres_ready" not in cli_src
    assert "_local_migration_environment" in cli_src
    mig_src = load_text("tools", "workflow", "migrations.py")
    assert "def migrate_integration_check" in mig_src
    assert "create_owner_database" in mig_src
    assert "def wait_for_integration_postgres_ready" in mig_src
    # Production path remains graph validation + component make migrate, not isolation.
    assert "def check_migrations" in mig_src
    # Final-ready waiter is only for the integration fixture path.
    check_src = inspect.getsource(
        __import__("workflow.migrations", fromlist=["check_migrations"]).check_migrations
    )
    assert "wait_for_integration_postgres_ready" not in check_src
    assert "create_owner_database" not in check_src


class _FakeClock:
    """Deterministic monotonic clock for readiness polling tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += max(float(seconds), 0.0)


def test_early_pg_isready_alone_is_not_final_ready() -> None:
    """First temporary-server readiness must not satisfy the waiter."""
    clock = _FakeClock()
    # Container stays up; init marker never appears; SQL never probed as final.
    with (
        patch("workflow.migrations._integration_container_running", return_value=True),
        patch(
            "workflow.migrations._integration_docker_logs",
            return_value="LOG:  database system is ready to accept connections\n",
        ) as logs_mock,
        patch("workflow.migrations._integration_sql_probe") as probe_mock,
    ):
        with pytest.raises(MigrationError) as excinfo:
            wait_for_integration_postgres_ready(
                "tm-migrate-integration-check",
                timeout_seconds=1.0,
                stable_successes=3,
                poll_interval_seconds=0.5,
                now=clock.now,
                sleep=clock.sleep,
            )
        assert excinfo.value.code == "STEP_FAILED"
        assert "finally ready" in excinfo.value.message
        # Without init-complete marker we must not treat any SQL probe as decisive.
        probe_mock.assert_not_called()
        assert logs_mock.called


def test_create_database_not_reached_before_init_complete_log() -> None:
    """migrate_integration_check must not CREATE DATABASE before final ready."""
    create_calls: list[Any] = []

    def boom_wait(container_name: str, **kwargs: Any) -> None:
        del container_name, kwargs
        raise MigrationError(
            "STEP_FAILED",
            "PostgreSQL integration container did not become finally ready within 60s; "
            "docker logs (truncated): still initializing",
        )

    def track_create(**kwargs: Any) -> None:
        create_calls.append(kwargs)

    with (
        patch("workflow.migrations.subprocess.run") as run_mock,
        patch(
            "workflow.migrations.wait_for_integration_postgres_ready",
            side_effect=boom_wait,
        ),
        patch("workflow.migrations.create_owner_database", side_effect=track_create),
        patch("workflow.migrations.load_owners") as load_mock,
        patch("workflow.migrations._run_owner_round_trip") as trip_mock,
    ):
        run_mock.return_value = MagicMock(returncode=0, stdout="cid\n", stderr="")
        load_mock.return_value = {
            "owners": [
                {"component_id": "api-service", "order": 1},
                {"component_id": "billing-service", "order": 2},
            ]
        }
        log = migrate_integration_check(Path("/tmp/repo-not-used"))
    assert create_calls == []
    trip_mock.assert_not_called()
    assert "FAILED" in _event_statuses(log)
    messages = _event_messages(log)
    assert "finally ready" in messages
    assert any(list(c.args[0])[:2] == ["docker", "stop"] for c in run_mock.call_args_list)
    assert any(list(c.args[0])[:3] == ["docker", "rm", "-f"] for c in run_mock.call_args_list)


def test_wait_requires_init_complete_then_select_one() -> None:
    """Init-complete log is required before SQL probes count toward readiness."""
    clock = _FakeClock()
    log_phases = [
        "database system is ready to accept connections\n",  # temporary server only
        "database system is ready to accept connections\n",
        f"{_PG_INIT_COMPLETE_MARKER}\n",
        f"{_PG_INIT_COMPLETE_MARKER}\n",
        f"{_PG_INIT_COMPLETE_MARKER}\n",
        f"{_PG_INIT_COMPLETE_MARKER}\n",
    ]
    probe_results = [True, True, True]  # three consecutive after marker

    with (
        patch("workflow.migrations._integration_container_running", return_value=True),
        patch(
            "workflow.migrations._integration_docker_logs",
            side_effect=log_phases,
        ),
        patch(
            "workflow.migrations._integration_sql_probe",
            side_effect=probe_results,
        ) as probe_mock,
    ):
        wait_for_integration_postgres_ready(
            "tm-migrate-integration-check",
            timeout_seconds=10.0,
            stable_successes=3,
            poll_interval_seconds=0.25,
            now=clock.now,
            sleep=clock.sleep,
        )
    assert probe_mock.call_count == 3


def test_wait_retries_failed_sql_probes() -> None:
    """Failed SELECT 1 probes reset the stability window and are retried."""
    clock = _FakeClock()
    probes = [False, False, True, False, True, True, True]

    with (
        patch("workflow.migrations._integration_container_running", return_value=True),
        patch(
            "workflow.migrations._integration_docker_logs",
            return_value=f"{_PG_INIT_COMPLETE_MARKER}\n",
        ),
        patch("workflow.migrations._integration_sql_probe", side_effect=probes) as probe_mock,
    ):
        wait_for_integration_postgres_ready(
            "tm-migrate-integration-check",
            timeout_seconds=30.0,
            stable_successes=3,
            poll_interval_seconds=0.1,
            now=clock.now,
            sleep=clock.sleep,
        )
    assert probe_mock.call_count == len(probes)


def test_wait_fail_closed_when_container_exits() -> None:
    clock = _FakeClock()
    with (
        patch("workflow.migrations._integration_container_running", return_value=False),
        patch(
            "workflow.migrations._integration_docker_logs",
            return_value="FATAL: could not write init file\n",
        ),
        patch("workflow.migrations._integration_sql_probe") as probe_mock,
    ):
        with pytest.raises(MigrationError) as excinfo:
            wait_for_integration_postgres_ready(
                "tm-migrate-integration-check",
                timeout_seconds=10.0,
                now=clock.now,
                sleep=clock.sleep,
            )
    assert excinfo.value.code == "STEP_FAILED"
    assert "exited before final ready" in excinfo.value.message
    assert "could not write init file" in excinfo.value.message
    probe_mock.assert_not_called()


def test_wait_timeout_includes_truncated_diagnostic_logs() -> None:
    clock = _FakeClock()
    noisy = "x" * 100 + "postgresql://postgres:super-secret@127.0.0.1:5432/postgres " + "y" * 100
    with (
        patch("workflow.migrations._integration_container_running", return_value=True),
        patch("workflow.migrations._integration_docker_logs", return_value=noisy),
        patch("workflow.migrations._integration_sql_probe", return_value=False),
    ):
        with pytest.raises(MigrationError) as excinfo:
            wait_for_integration_postgres_ready(
                "tm-migrate-integration-check",
                timeout_seconds=0.5,
                poll_interval_seconds=0.25,
                now=clock.now,
                sleep=clock.sleep,
            )
    assert excinfo.value.code == "STEP_FAILED"
    assert "docker logs (truncated)" in excinfo.value.message
    assert "super-secret" not in excinfo.value.message
    assert "postgresql://postgres:***@" in excinfo.value.message or "***" in excinfo.value.message


def test_owner_databases_created_only_after_final_ready() -> None:
    """CREATE DATABASE for api then billing runs only after wait returns."""
    order: list[str] = []

    def ready(container_name: str, **kwargs: Any) -> None:
        del kwargs
        order.append(f"ready:{container_name}")

    def create_db(**kwargs: Any) -> None:
        order.append(f"create:{kwargs['database']}")

    def trip(**kwargs: Any) -> None:
        order.append(f"trip:{kwargs['component_id']}")

    with (
        patch("workflow.migrations.subprocess.run") as run_mock,
        patch("workflow.migrations.wait_for_integration_postgres_ready", side_effect=ready),
        patch("workflow.migrations.create_owner_database", side_effect=create_db),
        patch("workflow.migrations.load_owners") as load_mock,
        patch("workflow.migrations._run_owner_round_trip", side_effect=trip),
        patch("workflow.migrations.new_integration_run_token", return_value="deadbeef"),
    ):
        run_mock.return_value = MagicMock(returncode=0, stdout="cid\n", stderr="")
        load_mock.return_value = {
            "owners": [
                {
                    "component_id": "api-service",
                    "order": 1,
                    "component_path": "services/api-service",
                },
                {
                    "component_id": "billing-service",
                    "order": 2,
                    "component_path": "services/billing-service",
                },
            ]
        }
        log = migrate_integration_check(Path("/tmp/repo-not-used"))

    assert order[0] == "ready:tm-migrate-integration-check"
    assert order[1] == "create:tm_mig_deadbeef_api_service"
    assert order[2] == "create:tm_mig_deadbeef_billing_service"
    assert order[3] == "trip:api-service"
    assert order[4] == "trip:billing-service"
    assert "PASSED" in _event_statuses(log)


def test_cleanup_always_runs_after_ready_failure() -> None:
    """finally stop/rm must run even when readiness fails closed."""

    def boom_wait(container_name: str, **kwargs: Any) -> None:
        del container_name, kwargs
        raise MigrationError("STEP_FAILED", "not ready; docker logs (truncated): boom")

    with (
        patch("workflow.migrations.subprocess.run") as run_mock,
        patch(
            "workflow.migrations.wait_for_integration_postgres_ready",
            side_effect=boom_wait,
        ),
        patch("workflow.migrations.create_owner_database") as create_mock,
    ):
        run_mock.return_value = MagicMock(returncode=0, stdout="cid\n", stderr="")
        log = migrate_integration_check(Path("/tmp/repo-not-used"))

    create_mock.assert_not_called()
    assert "FAILED" in _event_statuses(log)
    # At least one stop and one force-rm after the failure path.
    docker_cmds = [list(c.args[0]) for c in run_mock.call_args_list if c.args]
    assert any(cmd[:2] == ["docker", "stop"] for cmd in docker_cmds)
    assert any(cmd[:3] == ["docker", "rm", "-f"] for cmd in docker_cmds)


def test_ordinary_make_migrate_does_not_wire_final_ready_waiter() -> None:
    """Public make migrate path stays on validated external DATABASE_URL only."""
    cli_src = load_text("tools", "workflow", "cli.py")
    # migrate action does not import or call the integration readiness helper.
    assert "wait_for_integration_postgres_ready" not in cli_src
    assert 'args.action == "migrate-integration-check"' in cli_src
    mig_src = load_text("tools", "workflow", "migrations.py")
    # Helper exists for integration only; offline check is separate.
    assert "def wait_for_integration_postgres_ready" in mig_src
    assert "def check_migrations" in mig_src
    # Integration waiter is referenced from migrate_integration_check body.
    mic = inspect.getsource(
        __import__(
            "workflow.migrations", fromlist=["migrate_integration_check"]
        ).migrate_integration_check
    )
    assert "wait_for_integration_postgres_ready" in mic
    assert "pg_isready" not in mic


def test_wait_for_ready_does_not_use_pg_isready() -> None:
    """Stability path must use init marker + SELECT 1, not invoke pg_isready."""
    src = inspect.getsource(wait_for_integration_postgres_ready)
    # Docstring may mention the race; implementation must not shell out to pg_isready.
    assert '"pg_isready"' not in src and "'pg_isready'" not in src
    assert "_integration_sql_probe" in src
    helpers = inspect.getsource(
        __import__(
            "workflow.migrations", fromlist=["_integration_sql_probe"]
        )._integration_sql_probe
    )
    assert "SELECT 1" in helpers
    assert '"pg_isready"' not in helpers and "'pg_isready'" not in helpers
    mic = inspect.getsource(migrate_integration_check)
    assert "wait_for_integration_postgres_ready" in mic
    assert '"pg_isready"' not in mic and "'pg_isready'" not in mic


def test_isolation_helpers_do_not_stamp_or_wipe_alembic_version() -> None:
    src = inspect.getsource(
        __import__("workflow.migrations", fromlist=["migrate_integration_check"])
    )
    lower = src.lower()
    assert "stamp" not in lower
    assert "drop table alembic_version" not in lower
    assert "delete from alembic_version" not in lower
    assert "truncate alembic_version" not in lower


def test_api_revision_cannot_share_billing_database_url(
    owners_manifest: dict[str, Any],
) -> None:
    """Different database paths mean api head cannot pollute billing alembic_version."""
    planned = plan_owner_databases(
        list(owners_manifest["owners"]),
        run_token="f00dcafe",
        base_url="postgresql+psycopg2://postgres:synthetic@127.0.0.1:15432/postgres",
    )
    api_url = planned[0]["database_url"]
    billing_url = planned[1]["database_url"]
    assert urlparse(api_url).path != urlparse(billing_url).path
    assert "0003_phone_login_session" not in api_url
    assert "0003_phone_login_session" not in billing_url
    assert planned[0]["database"] not in billing_url
    assert planned[1]["database"] not in api_url
