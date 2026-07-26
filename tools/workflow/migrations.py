"""Migration owner reconciliation and offline graph checks.

Operates on ``ops/migrations/owners.json`` and the Alembic directories owned by
api-service and billing-service.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse, urlunparse

from .events import DiagnosticCode, EventLog
from .mode import ModeError, require_production_approval, validate_mode

# Ephemeral integration fixture only (never development/production hosts).
_INTEGRATION_CONTAINER = "tm-migrate-integration-check"
_INTEGRATION_ADMIN_URL = (
    "postgresql+psycopg2://postgres:synthetic@127.0.0.1:15432/postgres"
)
_INTEGRATION_PG_IMAGE = "postgres:15.12"
_DB_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_RUN_TOKEN_RE = re.compile(r"^[a-z0-9]{8,16}$")
_OWNER_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


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


def new_integration_run_token() -> str:
    """Return a short unique token for one migrate-integration-check run."""
    return uuid.uuid4().hex[:8]


def normalize_component_slug(component_id: str) -> str:
    """Normalize a component id into a PostgreSQL-safe slug fragment."""
    raw = (component_id or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if not slug or not _OWNER_SLUG_RE.fullmatch(slug):
        raise MigrationError(
            "MIGRATION_INVALID",
            f"component id {component_id!r} cannot form a safe database name slug",
        )
    return slug


def owner_database_name(*, run_token: str, component_id: str) -> str:
    """Build a unique, validated database name for one owner in one run.

    Format: ``tm_mig_<token>_<slug>`` (max 63 chars, ``[a-z][a-z0-9_]*``).
    """
    token = re.sub(r"[^a-z0-9]", "", (run_token or "").lower())
    if not _RUN_TOKEN_RE.fullmatch(token):
        raise MigrationError(
            "MIGRATION_INVALID",
            "integration run token must be 8–16 lowercase alphanumeric characters",
        )
    slug = normalize_component_slug(component_id)
    name = f"tm_mig_{token}_{slug}"
    if len(name) > 63:
        name = name[:63].rstrip("_")
    if not _DB_NAME_RE.fullmatch(name):
        raise MigrationError(
            "MIGRATION_INVALID",
            f"generated database name is not a safe identifier: {name!r}",
        )
    if not name.startswith(f"tm_mig_{token}_"):
        raise MigrationError(
            "MIGRATION_INVALID",
            "generated database name lost required run-token prefix",
        )
    return name


def replace_database_name(url: str, database: str) -> str:
    """Return ``url`` with only the database path segment replaced.

    Preserves scheme (including SQLAlchemy drivers), userinfo, host, port, query,
    and fragment. ``database`` must already be a validated safe identifier.
    """
    if not _DB_NAME_RE.fullmatch(database):
        raise MigrationError(
            "MIGRATION_INVALID",
            f"refusing to put unsafe database name into URL: {database!r}",
        )
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise MigrationError("MIGRATION_INVALID", "DATABASE_URL is missing scheme or host")
    # Keep empty host edge cases out of integration fixture URLs.
    if not parsed.hostname and "@" not in parsed.netloc:
        raise MigrationError("MIGRATION_INVALID", "DATABASE_URL is missing host")
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{database}",
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def redact_database_url(url: str) -> str:
    """Mask password material in a database URL for logs and events."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "<invalid-database-url>"
    user = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    auth = f"{user}:***@" if user or parsed.password else ""
    return urlunparse(
        (
            parsed.scheme,
            f"{auth}{host}{port}",
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def plan_owner_databases(
    owners: list[Mapping[str, Any]],
    *,
    run_token: str,
    base_url: str,
) -> list[dict[str, str]]:
    """Map migration owners to isolated database names and URLs (order preserved)."""
    if not owners:
        raise MigrationError("MIGRATION_INVALID", "no migration owners to plan")
    planned: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for owner in owners:
        component_id = str(owner.get("component_id") or "").strip()
        if not component_id:
            raise MigrationError("MIGRATION_INVALID", "owner missing component_id")
        db_name = owner_database_name(run_token=run_token, component_id=component_id)
        if db_name in seen_names:
            raise MigrationError(
                "MIGRATION_INVALID",
                f"duplicate owner database name planned: {db_name}",
            )
        seen_names.add(db_name)
        database_url = replace_database_name(base_url, db_name)
        planned.append(
            {
                "component_id": component_id,
                "database": db_name,
                "database_url": database_url,
            }
        )
    return planned


def _assert_integration_fixture_url(url: str) -> None:
    """Fail closed if the admin URL does not target the ephemeral integration fixture."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if host not in {"127.0.0.1", "localhost"} or port != 15432:
        raise MigrationError(
            "STEP_FAILED",
            "migrate-integration-check refuses non-fixture DATABASE_URL host/port",
        )
    path = (parsed.path or "").strip("/")
    if path and path != "postgres":
        raise MigrationError(
            "STEP_FAILED",
            "migrate-integration-check admin URL must target the default postgres database",
        )


def create_owner_database(
    *,
    container_name: str,
    database: str,
    run_token: str,
) -> None:
    """CREATE DATABASE inside the ephemeral integration container.

    Uses ``docker exec … psql`` (image-local client) so the workflow package does
    not need an extra driver. Identifier is validated before interpolation.
    """
    if not _RUN_TOKEN_RE.fullmatch(re.sub(r"[^a-z0-9]", "", run_token.lower())):
        raise MigrationError("MIGRATION_INVALID", "invalid run token for CREATE DATABASE")
    if not _DB_NAME_RE.fullmatch(database):
        raise MigrationError(
            "MIGRATION_INVALID",
            f"refusing CREATE DATABASE for unsafe name: {database!r}",
        )
    if not database.startswith(f"tm_mig_{run_token}_"):
        raise MigrationError(
            "MIGRATION_INVALID",
            "refusing CREATE DATABASE: name does not match this run token prefix",
        )
    if database in {"postgres", "template0", "template1"}:
        raise MigrationError(
            "MIGRATION_INVALID",
            "refusing CREATE DATABASE for a reserved database name",
        )
    # Name is [a-z][a-z0-9_]{…} only — safe as an unquoted PG identifier.
    sql = f"CREATE DATABASE {database}"
    result = subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "create database failed").strip()
        # Never echo connection strings; psql errors here are structural.
        raise MigrationError(
            "STEP_FAILED",
            f"failed to create owner database {database}: {detail[:300]}",
        )


def _component_path(repo_root: Path, owner: Mapping[str, Any]) -> Path:
    if "component_path" in owner:
        return repo_root / str(owner["component_path"])
    return repo_root / "services" / str(owner["component_id"])


def _run_owner_round_trip(
    *,
    component_id: str,
    component_path: Path,
    database_url: str,
    log: EventLog,
) -> None:
    """Forward / backout / retry against one owner-isolated DATABASE_URL."""
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    log.start("migrate", component_id, "forward")
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
            f"{component_id} forward migration failed: {fwd.stderr}",
        )
    log.finish("migrate", component_id, "forward", status="PASSED")

    log.start("migrate", component_id, "backout")
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
            f"{component_id} backout migration failed: {back.stderr}",
        )
    log.finish("migrate", component_id, "backout", status="PASSED")

    log.start("migrate", component_id, "retry")
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
            f"{component_id} retry migration failed: {retry.stderr}",
        )
    log.finish("migrate", component_id, "retry", status="PASSED")


def migrate_integration_check(repo_root: Path) -> EventLog:
    """Run API then Billing forward/backout/retry/final-head using a PG15 container.

    Isolation model (scheme A): one ephemeral container, one unique database per
    migration owner for the run. Owners never share ``alembic_version``. Cleanup
    relies on stopping/removing the container (databases are discarded with it);
    no explicit DROP DATABASE is required.
    """
    import time

    log = EventLog()
    container_name = _INTEGRATION_CONTAINER
    admin_url = _INTEGRATION_ADMIN_URL
    run_token = new_integration_run_token()
    planned: list[dict[str, str]] = []

    log.start("migrate-integration-check", "repository", "setup")
    try:
        _assert_integration_fixture_url(admin_url)

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
                _INTEGRATION_PG_IMAGE,
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

        owners_doc = load_owners(repo_root)
        owners = list(owners_doc["owners"])
        planned = plan_owner_databases(
            owners,
            run_token=run_token,
            base_url=admin_url,
        )
        for entry in planned:
            create_owner_database(
                container_name=container_name,
                database=entry["database"],
                run_token=run_token,
            )

        db_summary = ", ".join(
            f"{e['component_id']}->{e['database']}" for e in planned
        )
        log.finish(
            "migrate-integration-check",
            "repository",
            "setup",
            status="PASSED",
            message=(
                f"owner-isolated databases ready (run={run_token}): {db_summary}; "
                f"admin={redact_database_url(admin_url)}"
            ),
        )

        for owner, entry in zip(owners, planned, strict=True):
            component_id = entry["component_id"]
            component_path = _component_path(repo_root, owner)
            _run_owner_round_trip(
                component_id=component_id,
                component_path=component_path,
                database_url=entry["database_url"],
                log=log,
            )

        log.finish(
            "migrate-integration-check",
            "repository",
            "validation",
            status="PASSED",
            message=(
                "api-service and billing-service forward/backout/retry passed "
                f"on isolated per-owner databases (run={run_token}): {db_summary}"
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
        # Container teardown discards all per-owner databases for this run.
        # Explicit DROP DATABASE is intentionally omitted; names are run-scoped
        # and never target the default postgres database.
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
