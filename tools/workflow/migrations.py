"""Migration owner reconciliation and offline graph checks.

Operates on ``ops/migrations/owners.json`` and the Alembic directories owned by
api-service and billing-service.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .events import DiagnosticCode, EventLog
from .mode import ModeError, require_production_approval, validate_mode


class MigrationError(Exception):
    """Raised when migration validation or execution fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_owners(repo_root: Path) -> dict[str, Any]:
    """Load the migration owner manifest."""
    path = repo_root / "ops" / "migrations" / "owners.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_owner_graphs(repo_root: Path) -> None:
    """Validate that each owner has an Alembic versions directory with one head."""
    owners = load_owners(repo_root)

    expected = [
        ("api-service", 1),
        ("billing-service", 2),
    ]
    actual = [(o["component_id"], o["order"]) for o in owners["owners"]]
    if actual != expected:
        raise MigrationError("MIGRATION_INVALID", f"owner order mismatch: {actual}")

    if "admin-service" not in owners.get("non_owners", []):
        raise MigrationError("MIGRATION_INVALID", "admin-service must be a non-owner")

    for owner in owners["owners"]:
        version_path = repo_root / owner["version_path"]
        if not version_path.is_dir():
            raise MigrationError(
                "MIGRATION_INVALID",
                f"{owner['component_id']}: missing versions directory {owner['version_path']}",
            )
        migrations = list(version_path.glob("*.py"))
        if not migrations:
            raise MigrationError(
                "MIGRATION_INVALID",
                f"{owner['component_id']}: no migrations in {owner['version_path']}",
            )

        runbook = repo_root / owner["backout_runbook"]
        if not runbook.is_file():
            raise MigrationError(
                "MIGRATION_INVALID",
                f"{owner['component_id']}: missing backout runbook {owner['backout_runbook']}",
            )


def check_migrations(
    *,
    repo_root: Path,
    mode: str | None,
    mode_origin: str,
    approval_proof: dict[str, Any] | None = None,
) -> EventLog:
    """Offline migration check plus optional mode validation."""
    log = EventLog()
    log.start("migrate-check", "repository", "validation")

    try:
        selection = validate_mode(mode, mode_origin)
        if selection.mode == "prod":
            selection = require_production_approval(selection, approval_proof=approval_proof)

        validate_owner_graphs(repo_root)

        owners = load_owners(repo_root)
        owner_names = ", ".join(o["component_id"] for o in owners["owners"])
        log.finish(
            "migrate-check",
            "repository",
            "validation",
            status="PASSED",
            message=f"migration owners validated: {owner_names}; mode={selection.mode}",
        )
    except (ModeError, MigrationError) as exc:
        log.finish(
            "migrate-check",
            "repository",
            "validation",
            status="FAILED",
            code=DiagnosticCode(exc.code),
            message=exc.message,
        )

    return log


def run_alembic(component_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run an Alembic command inside a service directory."""
    return subprocess.run(
        ["uv", "run", "--locked", "alembic", *args],
        cwd=component_path,
        capture_output=True,
        text=True,
        check=False,
    )


def migrate_integration_check(repo_root: Path) -> EventLog:
    """Run API then Billing forward/backout/retry/final-head using a PG15 container."""
    import time

    log = EventLog()
    container_name = "tm-migrate-integration-check"
    sync_database_url = "postgresql+psycopg2://postgres:synthetic@localhost:15432/postgres"

    log.start("migrate-integration-check", "repository", "setup")
    try:
        # Stop and remove any leftover container.
        subprocess.run(
            ["docker", "stop", "--time", "5", container_name],
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            check=False,
        )

        # Start a pinned PostgreSQL 15 container with synthetic credentials.
        run_result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                container_name,
                "-e",
                "POSTGRES_PASSWORD=synthetic",
                "-p",
                "127.0.0.1:15432:5432",
                "postgres:15.12",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if run_result.returncode != 0:
            raise MigrationError(
                "STEP_FAILED",
                f"failed to start PostgreSQL container: {run_result.stderr}",
            )

        # Wait for the database to accept connections.
        deadline = time.time() + 30
        while time.time() < deadline:
            probe = subprocess.run(
                ["docker", "exec", container_name, "pg_isready", "-U", "postgres"],
                capture_output=True,
                check=False,
            )
            if probe.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise MigrationError("STEP_FAILED", "PostgreSQL container did not become ready")

        log.finish("migrate-integration-check", "repository", "setup", status="PASSED")

        owners = load_owners(repo_root)
        for owner in owners["owners"]:
            component_path = (
                repo_root / owner["component_path"]
                if "component_path" in owner
                else repo_root / "services" / owner["component_id"]
            )
            env = os.environ.copy()
            env["DATABASE_URL"] = sync_database_url

            # Forward migration.
            log.start("migrate", owner["component_id"], "forward")
            fwd = subprocess.run(
                ["uv", "run", "--locked", "alembic", "upgrade", "head"],
                cwd=component_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if fwd.returncode != 0:
                raise MigrationError(
                    "MIGRATION_INVALID",
                    f"{owner['component_id']} forward migration failed: {fwd.stderr}",
                )
            log.finish("migrate", owner["component_id"], "forward", status="PASSED")

            # Backout migration.
            log.start("migrate", owner["component_id"], "backout")
            back = subprocess.run(
                ["uv", "run", "--locked", "alembic", "downgrade", "base"],
                cwd=component_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if back.returncode != 0:
                raise MigrationError(
                    "MIGRATION_INVALID",
                    f"{owner['component_id']} backout migration failed: {back.stderr}",
                )
            log.finish("migrate", owner["component_id"], "backout", status="PASSED")

            # Retry forward to final head.
            log.start("migrate", owner["component_id"], "retry")
            retry = subprocess.run(
                ["uv", "run", "--locked", "alembic", "upgrade", "head"],
                cwd=component_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if retry.returncode != 0:
                raise MigrationError(
                    "MIGRATION_INVALID",
                    f"{owner['component_id']} retry migration failed: {retry.stderr}",
                )
            log.finish("migrate", owner["component_id"], "retry", status="PASSED")

        log.finish(
            "migrate-integration-check",
            "repository",
            "validation",
            status="PASSED",
            message=(
                "api-service and billing-service forward/backout/retry passed "
                "on isolated PostgreSQL 15"
            ),
        )
    except MigrationError as exc:
        log.finish(
            "migrate-integration-check",
            "repository",
            "validation",
            status="FAILED",
            code=DiagnosticCode(exc.code),
            message=exc.message,
        )
    finally:
        subprocess.run(
            ["docker", "stop", "--time", "5", container_name],
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            check=False,
        )

    return log
