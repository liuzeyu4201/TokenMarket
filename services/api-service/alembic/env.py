"""Alembic environment for API service baseline migration."""

import os
from logging.config import fileConfig
from urllib.parse import parse_qsl, urlparse

from alembic import context
from sqlalchemy import engine_from_config, pool

_HOST_AFFECTING = frozenset(
    {
        "host",
        "hostaddr",
        "port",
        "passfile",
        "service",
        "options",
        "unix_socket",
        "unix_socket_dir",
        "unix_socket_directories",
    }
)


def _refuse_host_override(url: str) -> str:
    """Fail closed if driver query parameters can retarget the host."""
    text = (url or "").strip()
    if not text:
        raise RuntimeError("DATABASE_URL is missing")
    parsed = urlparse(text)
    netloc = parsed.netloc or ""
    if "," in netloc:
        raise RuntimeError("DATABASE_URL multi-host form is not allowed")
    host = (parsed.hostname or "").strip()
    if not host or host.startswith("/") or "/" in host:
        raise RuntimeError("DATABASE_URL unix-socket form is not allowed")
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in _HOST_AFFECTING:
            raise RuntimeError(
                f"DATABASE_URL query parameter {key!r} can retarget the host"
            )
    return text


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

if os.environ.get("DATABASE_URL"):
    config.set_section_option(
        config.config_ini_section,
        "sqlalchemy.url",
        _refuse_host_override(os.environ["DATABASE_URL"]),
    )

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
