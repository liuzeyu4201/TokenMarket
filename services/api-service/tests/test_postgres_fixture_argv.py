"""Disposable Postgres fixture must not persist anonymous volumes."""

from __future__ import annotations

from conftest import POSTGRES_IMAGE, PostgresHandle, postgres_run_argv


def test_postgres_run_argv_uses_tmpfs_data_dir() -> None:
    handle = PostgresHandle(
        name="tmtest-fixtureargv",
        port=15999,
        user="tmtest",
        database="tmtest",
        _password="tm_local_synthetic_not_logged",
    )
    argv = postgres_run_argv(handle)
    assert argv[0] == "run"
    assert "--detach" in argv
    assert "--pull" in argv
    assert argv[argv.index("--pull") + 1] == "never"
    assert "--mount" in argv
    assert argv[argv.index("--mount") + 1] == (
        "type=tmpfs,destination=/var/lib/postgresql/data"
    )
    assert argv[-1] == POSTGRES_IMAGE
