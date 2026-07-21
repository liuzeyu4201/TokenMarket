"""Strict ``.env.local`` parsing, validation, and projection tests (T019).

Covers the configuration contract of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and research Decision 6: mode-first rejection (``INVALID_MODE`` before any
other work), strict local URL grammar, loopback-literal-only hosts,
placeholder/empty rejection, percent-decoding after syntax validation, the
``tm_local_`` synthetic-secret grammar, pairwise-distinct ports, derived
container connections, safe displayed endpoints, and field-name-only errors.

These tests fail until T026 implements
``tools/workflow/local_env/config.py``.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from .helpers import repo_path


def _config() -> Any:
    try:
        return importlib.import_module("workflow.local_env.config")
    except ImportError as exc:
        pytest.fail(f"workflow.local_env.config is not implemented yet (T026): {exc}")


def _models() -> Any:
    return importlib.import_module("workflow.local_env.models")


_FIELD_ORDER = (
    "MODE",
    "DATABASE_URL",
    "REDIS_URL",
    "GRAFANA_URL",
    "GRAFANA_ADMIN_PASSWORD",
)


@dataclass(frozen=True)
class _ValidInput:
    pg_secret: str
    redis_secret: str
    grafana_secret: str
    values: dict[str, str]


@pytest.fixture
def valid_input(synthetic_secret_factory: Any) -> _ValidInput:
    pg_secret = synthetic_secret_factory.new()
    redis_secret = synthetic_secret_factory.new()
    grafana_secret = synthetic_secret_factory.new()
    return _ValidInput(
        pg_secret=pg_secret,
        redis_secret=redis_secret,
        grafana_secret=grafana_secret,
        values={
            "MODE": "local",
            "DATABASE_URL": f"postgresql://app:{pg_secret}@127.0.0.1:5432/tokenmarket",
            "REDIS_URL": f"redis://default:{redis_secret}@127.0.0.1:6379/0",
            "GRAFANA_URL": "http://127.0.0.1:3000",
            "GRAFANA_ADMIN_PASSWORD": grafana_secret,
        },
    )


def _render(values: Mapping[str, str], *, drop: tuple[str, ...] = ()) -> str:
    lines = [
        f"{key}={values[key]}"
        for key in _FIELD_ORDER
        if key in values and key not in drop
    ]
    return "\n".join(lines) + "\n"


def _parse(values: Mapping[str, str], *, drop: tuple[str, ...] = ()) -> Any:
    return _config().parse_local_environment(_render(values, drop=drop))


def _example_assignments() -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in repo_path(".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


class TestValidParsing:
    def test_valid_file_parses_all_fields(self, valid_input: _ValidInput) -> None:
        models = _models()
        parsed = _parse(valid_input.values)
        assert parsed.mode == "local"
        postgres = parsed.connection(models.DependencyId.POSTGRES)
        redis = parsed.connection(models.DependencyId.REDIS)
        grafana = parsed.connection(models.DependencyId.GRAFANA)
        assert postgres.host_scheme == "postgresql"
        assert postgres.host_address == "127.0.0.1"
        assert postgres.host_port == 5432
        assert postgres.username == "app"
        assert postgres.database == "tokenmarket"
        assert postgres.secret == valid_input.pg_secret
        assert redis.host_scheme == "redis"
        assert redis.host_port == 6379
        assert redis.username == "default"
        assert redis.database == 0
        assert redis.secret == valid_input.redis_secret
        assert grafana.host_scheme == "http"
        assert grafana.host_port == 3000
        assert grafana.username == "admin"
        assert grafana.secret == valid_input.grafana_secret

    def test_connections_cover_dependencies_in_order(
        self, valid_input: _ValidInput
    ) -> None:
        models = _models()
        parsed = _parse(valid_input.values)
        ids = [connection.dependency_id for connection in parsed.connections]
        assert ids == [
            models.DependencyId.POSTGRES,
            models.DependencyId.REDIS,
            models.DependencyId.GRAFANA,
        ]

    def test_comments_and_blank_lines_are_ignored(
        self, valid_input: _ValidInput
    ) -> None:
        text = (
            "# leading comment\n\n" + _render(valid_input.values) + "   \n# trailing\n"
        )
        parsed = _config().parse_local_environment(text)
        assert parsed.mode == "local"

    def test_unknown_fields_are_ignored(self, valid_input: _ValidInput) -> None:
        text = _render(valid_input.values)
        text += "KAFKA_BROKERS=localhost:9092\nAI_GATEWAY_KEY=sk-replace-me\n"
        parsed = _config().parse_local_environment(text)
        assert parsed.mode == "local"

    def test_non_default_distinct_ports_are_accepted(
        self, valid_input: _ValidInput
    ) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:{valid_input.pg_secret}@127.0.0.1:15432/tokenmarket"
        )
        values["REDIS_URL"] = (
            f"redis://default:{valid_input.redis_secret}@127.0.0.1:16379/0"
        )
        values["GRAFANA_URL"] = "http://127.0.0.1:13000"
        models = _models()
        parsed = _parse(values)
        assert parsed.connection(models.DependencyId.POSTGRES).host_port == 15432
        assert parsed.connection(models.DependencyId.REDIS).host_port == 16379
        assert parsed.connection(models.DependencyId.GRAFANA).host_port == 13000

    def test_boundary_ports_are_accepted(self, valid_input: _ValidInput) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:{valid_input.pg_secret}@127.0.0.1:1/tokenmarket"
        )
        values["REDIS_URL"] = (
            f"redis://default:{valid_input.redis_secret}@127.0.0.1:65535/0"
        )
        parsed = _parse(values)
        models = _models()
        assert parsed.connection(models.DependencyId.POSTGRES).host_port == 1
        assert parsed.connection(models.DependencyId.REDIS).host_port == 65535

    def test_redis_multi_digit_database_number(self, valid_input: _ValidInput) -> None:
        values = dict(valid_input.values)
        values["REDIS_URL"] = (
            f"redis://default:{valid_input.redis_secret}@127.0.0.1:6379/12"
        )
        models = _models()
        parsed = _parse(values)
        assert parsed.connection(models.DependencyId.REDIS).database == 12

    def test_repeated_parse_is_deterministic(self, valid_input: _ValidInput) -> None:
        text = _render(valid_input.values)
        config = _config()
        assert config.parse_local_environment(text) == config.parse_local_environment(
            text
        )


class TestStrictFileParsing:
    def test_malformed_line_is_rejected(self, valid_input: _ValidInput) -> None:
        text = _render(valid_input.values) + "this line has no key separator\n"
        with pytest.raises(_config().InvalidConfigError):
            _config().parse_local_environment(text)

    def test_lowercase_key_is_rejected(self, valid_input: _ValidInput) -> None:
        text = _render(valid_input.values, drop=("DATABASE_URL",))
        text += (
            f"database_url=postgresql://app:{valid_input.pg_secret}@127.0.0.1:5432/db\n"
        )
        with pytest.raises(_config().InvalidConfigError):
            _config().parse_local_environment(text)

    def test_export_prefix_is_rejected(self, valid_input: _ValidInput) -> None:
        # An "export MODE=local" line is not a MODE declaration, so the file
        # has no valid mode and fails mode-first with INVALID_MODE.
        text = "export " + _render(valid_input.values)
        with pytest.raises(_config().InvalidModeError):
            _config().parse_local_environment(text)

    def test_leading_whitespace_line_is_rejected(
        self, valid_input: _ValidInput
    ) -> None:
        text = _render(valid_input.values) + "  EXTRA_FIELD=value\n"
        with pytest.raises(_config().InvalidConfigError):
            _config().parse_local_environment(text)

    def test_inline_comment_is_not_stripped(self, valid_input: _ValidInput) -> None:
        values = dict(valid_input.values)
        values["GRAFANA_URL"] = "http://127.0.0.1:3000 # comment"
        with pytest.raises(_config().InvalidConfigError):
            _parse(values)

    def test_crlf_line_endings_fail_closed(self, valid_input: _ValidInput) -> None:
        text = _render(valid_input.values).replace("\n", "\r\n")
        with pytest.raises(_config().InvalidModeError):
            _config().parse_local_environment(text)

    def test_duplicate_lifecycle_field_is_rejected(
        self, valid_input: _ValidInput
    ) -> None:
        text = (
            _render(valid_input.values)
            + f"GRAFANA_URL={valid_input.values['GRAFANA_URL']}\n"
        )
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _config().parse_local_environment(text)
        assert "GRAFANA_URL" in str(exc_info.value)


class TestModeOrigin:
    def test_missing_mode_is_invalid_mode(self, valid_input: _ValidInput) -> None:
        with pytest.raises(_config().InvalidModeError) as exc_info:
            _parse(valid_input.values, drop=("MODE",))
        assert exc_info.value.code == "INVALID_MODE"
        assert "MODE" in str(exc_info.value)

    @pytest.mark.parametrize("mode", ["prod", "test", "stage", "LOCAL", "Local"])
    def test_non_local_mode_is_invalid_mode(
        self, valid_input: _ValidInput, mode: str
    ) -> None:
        values = dict(valid_input.values)
        values["MODE"] = mode
        with pytest.raises(_config().InvalidModeError) as exc_info:
            _parse(values)
        assert exc_info.value.code == "INVALID_MODE"
        assert mode not in str(exc_info.value)

    @pytest.mark.parametrize("mode", ["", " local", "local ", '"local"', "local,test"])
    def test_imprecise_mode_is_invalid_mode(
        self, valid_input: _ValidInput, mode: str
    ) -> None:
        values = dict(valid_input.values)
        values["MODE"] = mode
        with pytest.raises(_config().InvalidModeError):
            _parse(values)

    def test_duplicate_mode_is_invalid_mode(self, valid_input: _ValidInput) -> None:
        text = "MODE=local\n" + _render(valid_input.values)
        with pytest.raises(_config().InvalidModeError):
            _config().parse_local_environment(text)

    def test_mode_rejection_precedes_config_errors(
        self, valid_input: _ValidInput
    ) -> None:
        values = dict(valid_input.values)
        values["MODE"] = "prod"
        values["DATABASE_URL"] = "not a url at all"
        with pytest.raises(_config().InvalidModeError):
            _parse(values)

    def test_mode_rejection_precedes_malformed_lines(
        self, valid_input: _ValidInput
    ) -> None:
        text = "MODE=test\ngarbage line without separator\n"
        with pytest.raises(_config().InvalidModeError):
            _config().parse_local_environment(text)

    def test_commented_mode_does_not_count(self, valid_input: _ValidInput) -> None:
        text = "#MODE=local\n" + _render(valid_input.values, drop=("MODE",))
        with pytest.raises(_config().InvalidModeError):
            _config().parse_local_environment(text)

    def test_comment_lines_may_mention_mode(self, valid_input: _ValidInput) -> None:
        text = "# MODE=prod is not allowed here\n" + _render(valid_input.values)
        parsed = _config().parse_local_environment(text)
        assert parsed.mode == "local"

    def test_shell_environment_cannot_override_file(
        self, valid_input: _ValidInput, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MODE", "prod")
        monkeypatch.setenv("DATABASE_URL", "postgresql://evil:pw@192.0.2.1:5432/prod")
        models = _models()
        parsed = _parse(valid_input.values)
        assert parsed.mode == "local"
        assert parsed.connection(models.DependencyId.POSTGRES).host_port == 5432

    def test_shell_environment_cannot_satisfy_missing_field(
        self, valid_input: _ValidInput, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", valid_input.grafana_secret)
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(valid_input.values, drop=("GRAFANA_ADMIN_PASSWORD",))
        assert "GRAFANA_ADMIN_PASSWORD" in str(exc_info.value)

    def test_error_codes_match_event_v2_taxonomy(self) -> None:
        config = _config()
        events = importlib.import_module("workflow.events")
        assert (
            config.InvalidModeError.code == events.DiagnosticCodeV2.INVALID_MODE.value
        )
        assert (
            config.InvalidConfigError.code
            == events.DiagnosticCodeV2.INVALID_CONFIG.value
        )

    def test_errors_extend_models_taxonomy(self) -> None:
        config = _config()
        models = _models()
        assert issubclass(config.InvalidModeError, models.LocalEnvironmentError)
        assert issubclass(config.InvalidConfigError, models.LocalEnvironmentError)


class TestDatabaseUrlGrammar:
    @pytest.mark.parametrize(
        "bad_url",
        [
            "postgres://app:{pg}@127.0.0.1:5432/tokenmarket",
            "POSTGRESQL://app:{pg}@127.0.0.1:5432/tokenmarket",
            "postgresql://app:{pg}@127.0.0.1:5432",
            "postgresql://app:{pg}@127.0.0.1:5432/",
            "postgresql://app:{pg}@127.0.0.1:5432/db/extra",
            "postgresql://:{pg}@127.0.0.1:5432/tokenmarket",
            "postgresql://app@127.0.0.1:5432/tokenmarket",
            "postgresql://app:@127.0.0.1:5432/tokenmarket",
            "postgresql://app:{pg}@127.0.0.1:5432/tokenmarket?sslmode=disable",
            "postgresql://app:{pg}@127.0.0.1:5432/tokenmarket#frag",
            "postgresql://app:{pg}@127.0.0.1:5432/token market",
            "postgresql://ap p:{pg}@127.0.0.1:5432/tokenmarket",
            "postgresql://app:{pg}@127.0.0.1/tokenmarket",
            "postgresql://app:{pg}@127.0.0.1:0/tokenmarket",
            "postgresql://app:{pg}@127.0.0.1:65536/tokenmarket",
            "postgresql://app:{pg}@127.0.0.1:abc/tokenmarket",
            "postgresql://app:{pg}@127.0.0.1:5432/token%market",
        ],
    )
    def test_invalid_database_urls_are_rejected(
        self, valid_input: _ValidInput, bad_url: str
    ) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = bad_url.format(pg=valid_input.pg_secret)
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert "DATABASE_URL" in str(exc_info.value)
        assert valid_input.pg_secret not in str(exc_info.value)

    def test_missing_database_url_is_rejected(self, valid_input: _ValidInput) -> None:
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(valid_input.values, drop=("DATABASE_URL",))
        assert "DATABASE_URL" in str(exc_info.value)

    def test_empty_database_url_is_rejected(self, valid_input: _ValidInput) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = ""
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert "DATABASE_URL" in str(exc_info.value)


class TestRedisUrlGrammar:
    @pytest.mark.parametrize(
        "bad_url",
        [
            "rediss://default:{rd}@127.0.0.1:6379/0",
            "redis://app:{rd}@127.0.0.1:6379/0",
            "redis://DEFAULT:{rd}@127.0.0.1:6379/0",
            "redis://default@127.0.0.1:6379/0",
            "redis://default:@127.0.0.1:6379/0",
            "redis://default:{rd}@127.0.0.1:6379",
            "redis://default:{rd}@127.0.0.1:6379/",
            "redis://default:{rd}@127.0.0.1:6379/-1",
            "redis://default:{rd}@127.0.0.1:6379/abc",
            "redis://default:{rd}@127.0.0.1:6379/0/1",
            "redis://default:{rd}@127.0.0.1:6379/0?x=1",
            "redis://default:{rd}@127.0.0.1:6379/0#f",
            "redis://default:{rd}@127.0.0.1:70000/0",
        ],
    )
    def test_invalid_redis_urls_are_rejected(
        self, valid_input: _ValidInput, bad_url: str
    ) -> None:
        values = dict(valid_input.values)
        values["REDIS_URL"] = bad_url.format(rd=valid_input.redis_secret)
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert "REDIS_URL" in str(exc_info.value)
        assert valid_input.redis_secret not in str(exc_info.value)

    def test_missing_redis_url_is_rejected(self, valid_input: _ValidInput) -> None:
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(valid_input.values, drop=("REDIS_URL",))
        assert "REDIS_URL" in str(exc_info.value)


class TestGrafanaUrlGrammar:
    @pytest.mark.parametrize(
        "bad_url",
        [
            "https://127.0.0.1:3000",
            "http://admin:pw@127.0.0.1:3000",
            "http://admin@127.0.0.1:3000",
            "http://127.0.0.1:3000/grafana",
            "http://127.0.0.1:3000?orgId=1",
            "http://127.0.0.1:3000/#/dash",
            "http://127.0.0.1",
            "http://127.0.0.1:70000",
            "http://127.0.0.1:not-a-port",
        ],
    )
    def test_invalid_grafana_urls_are_rejected(
        self, valid_input: _ValidInput, bad_url: str
    ) -> None:
        values = dict(valid_input.values)
        values["GRAFANA_URL"] = bad_url
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert "GRAFANA_URL" in str(exc_info.value)

    def test_trailing_root_slash_is_accepted(self, valid_input: _ValidInput) -> None:
        values = dict(valid_input.values)
        values["GRAFANA_URL"] = "http://127.0.0.1:3000/"
        models = _models()
        parsed = _parse(values)
        assert parsed.connection(models.DependencyId.GRAFANA).host_port == 3000

    def test_missing_grafana_url_is_rejected(self, valid_input: _ValidInput) -> None:
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(valid_input.values, drop=("GRAFANA_URL",))
        assert "GRAFANA_URL" in str(exc_info.value)

    def test_missing_grafana_admin_password_is_rejected(
        self, valid_input: _ValidInput
    ) -> None:
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(valid_input.values, drop=("GRAFANA_ADMIN_PASSWORD",))
        assert "GRAFANA_ADMIN_PASSWORD" in str(exc_info.value)


class TestLoopbackOnly:
    @pytest.mark.parametrize(
        "host",
        [
            "localhost",
            "LOCALHOST",
            "0.0.0.0",
            "192.168.1.10",
            "db.internal",
            "[::1]",
            "127.0.0.1.",
            "0177.0.0.1",
            "127.0.0.2",
        ],
    )
    @pytest.mark.parametrize("field", ["DATABASE_URL", "REDIS_URL", "GRAFANA_URL"])
    def test_non_loopback_literal_hosts_are_rejected(
        self, valid_input: _ValidInput, field: str, host: str
    ) -> None:
        values = dict(valid_input.values)
        if field == "DATABASE_URL":
            values[field] = (
                f"postgresql://app:{valid_input.pg_secret}@{host}:5432/tokenmarket"
            )
        elif field == "REDIS_URL":
            values[field] = f"redis://default:{valid_input.redis_secret}@{host}:6379/0"
        else:
            values[field] = f"http://{host}:3000"
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert field in str(exc_info.value)
        assert host not in str(exc_info.value)


class TestPlaceholders:
    @pytest.mark.parametrize(
        "password",
        [
            "replace-me",
            "changeme",
            "password",
            "placeholder",
            "tm_local_short",
            "tm_local_REPLACE_ME",
        ],
    )
    def test_placeholder_passwords_are_rejected(
        self, valid_input: _ValidInput, password: str
    ) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:{password}@127.0.0.1:5432/tokenmarket"
        )
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert "DATABASE_URL" in str(exc_info.value)
        assert password not in str(exc_info.value)

    def test_committed_env_example_fails_closed(self) -> None:
        text = repo_path(".env.example").read_text(encoding="utf-8")
        with pytest.raises(_config().InvalidConfigError):
            _config().parse_local_environment(text)

    @pytest.mark.parametrize(
        "field", ["DATABASE_URL", "REDIS_URL", "GRAFANA_ADMIN_PASSWORD"]
    )
    def test_example_secret_placeholders_are_unusable(
        self, valid_input: _ValidInput, field: str
    ) -> None:
        example = _example_assignments()
        assert field in example, f".env.example must declare {field} (T033)"
        values = dict(valid_input.values)
        values[field] = example[field]
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert field in str(exc_info.value)


class TestSecretGrammar:
    @pytest.mark.parametrize("length", [32, 48, 96])
    def test_valid_suffix_lengths_are_accepted(
        self, valid_input: _ValidInput, synthetic_secret_factory: Any, length: int
    ) -> None:
        values = dict(valid_input.values)
        values["GRAFANA_ADMIN_PASSWORD"] = synthetic_secret_factory.new(length)
        parsed = _parse(values)
        models = _models()
        assert (
            parsed.connection(models.DependencyId.GRAFANA).secret
            == values["GRAFANA_ADMIN_PASSWORD"]
        )

    @pytest.mark.parametrize("length", [0, 1, 31, 97, 128])
    def test_invalid_suffix_lengths_are_rejected(
        self, valid_input: _ValidInput, length: int
    ) -> None:
        values = dict(valid_input.values)
        values["GRAFANA_ADMIN_PASSWORD"] = "tm_local_" + "a" * length
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert "GRAFANA_ADMIN_PASSWORD" in str(exc_info.value)

    @pytest.mark.parametrize("prefix", ["tm_prod_", "tm_test_", "sk-live-", "local_"])
    def test_wrong_secret_prefixes_are_rejected(
        self, valid_input: _ValidInput, prefix: str
    ) -> None:
        values = dict(valid_input.values)
        values["GRAFANA_ADMIN_PASSWORD"] = prefix + "a" * 40
        with pytest.raises(_config().InvalidConfigError):
            _parse(values)

    @pytest.mark.parametrize(
        "bad_char",
        [
            ".",
            " ",
            "/",
            "\\",
            '"',
            "'",
            ";",
            "$",
            "+",
            "%",
            "~",
            ":",
            "@",
            "?",
            "#",
            "\t",
        ],
    )
    def test_forbidden_secret_characters_are_rejected(
        self, valid_input: _ValidInput, bad_char: str
    ) -> None:
        suffix = "a" * 20 + bad_char + "b" * 20
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:tm_local_{suffix}@127.0.0.1:5432/tokenmarket"
        )
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert "DATABASE_URL" in str(exc_info.value)

    def test_grafana_admin_password_is_not_percent_decoded(
        self, valid_input: _ValidInput
    ) -> None:
        values = dict(valid_input.values)
        values["GRAFANA_ADMIN_PASSWORD"] = "tm_local_" + "%2D" + "a" * 37
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert "GRAFANA_ADMIN_PASSWORD" in str(exc_info.value)

    def test_redis_password_cannot_inject_configuration(
        self, valid_input: _ValidInput
    ) -> None:
        values = dict(valid_input.values)
        injected = "tm_local_" + "a" * 39 + ";" + "requirepass other"
        values["REDIS_URL"] = f"redis://default:{injected}@127.0.0.1:6379/0"
        with pytest.raises(_config().InvalidConfigError):
            _parse(values)


class TestPercentDecoding:
    def test_percent_encoded_password_decodes_to_grammar(
        self, valid_input: _ValidInput
    ) -> None:
        secret = "tm_local_" + "aB3_-xY9" * 5
        encoded = secret.replace("-", "%2D").replace("_", "%5F")
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:{encoded}@127.0.0.1:5432/tokenmarket"
        )
        models = _models()
        parsed = _parse(values)
        assert parsed.connection(models.DependencyId.POSTGRES).secret == secret

    @pytest.mark.parametrize(
        "token", ["%40", "%2F", "%0A", "%00", "%20", "%25", "%3B", "%C3%A9"]
    )
    def test_decoding_outside_the_grammar_is_rejected(
        self, valid_input: _ValidInput, token: str
    ) -> None:
        raw_suffix = "a" * 39 + token
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:tm_local_{raw_suffix}@127.0.0.1:5432/tokenmarket"
        )
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert "DATABASE_URL" in str(exc_info.value)

    @pytest.mark.parametrize("token", ["%zz", "%2", "%"])
    def test_invalid_percent_sequences_are_rejected(
        self, valid_input: _ValidInput, token: str
    ) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:tm_local_{'a' * 40}{token}@127.0.0.1:5432/tokenmarket"
        )
        with pytest.raises(_config().InvalidConfigError):
            _parse(values)

    def test_invalid_utf8_encoding_is_rejected(self, valid_input: _ValidInput) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:tm_local_{'a' * 38}%FF%FE@127.0.0.1:5432/tokenmarket"
        )
        with pytest.raises(_config().InvalidConfigError):
            _parse(values)

    def test_decoded_length_is_enforced(self, valid_input: _ValidInput) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:tm_local_{'%2D' * 11}{'a' * 10}@127.0.0.1:5432/tokenmarket"
        )
        with pytest.raises(_config().InvalidConfigError):
            _parse(values)

    def test_short_encoded_secret_that_decodes_valid_is_accepted(
        self, valid_input: _ValidInput
    ) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:tm_local_%2D{'a' * 31}@127.0.0.1:5432/db"
        )
        models = _models()
        parsed = _parse(values)
        assert (
            parsed.connection(models.DependencyId.POSTGRES).secret
            == "tm_local_-" + "a" * 31
        )

    def test_percent_encoding_in_host_is_not_decoded(
        self, valid_input: _ValidInput
    ) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:{valid_input.pg_secret}@%31%32%37.0.0.1:5432/tokenmarket"
        )
        with pytest.raises(_config().InvalidConfigError):
            _parse(values)


class TestPorts:
    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ("DATABASE_URL", "REDIS_URL"),
            ("DATABASE_URL", "GRAFANA_URL"),
            ("REDIS_URL", "GRAFANA_URL"),
        ],
    )
    def test_duplicate_ports_are_rejected(
        self, valid_input: _ValidInput, first: str, second: str
    ) -> None:
        values = dict(valid_input.values)
        for field in (first, second):
            if field == "DATABASE_URL":
                values[field] = (
                    f"postgresql://app:{valid_input.pg_secret}@127.0.0.1:40000/tokenmarket"
                )
            elif field == "REDIS_URL":
                values[field] = (
                    f"redis://default:{valid_input.redis_secret}@127.0.0.1:40000/0"
                )
            else:
                values[field] = "http://127.0.0.1:40000"
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        assert first in str(exc_info.value)
        assert second in str(exc_info.value)


class TestDerivedConnections:
    def test_container_urls_replace_only_host_and_port(
        self, valid_input: _ValidInput
    ) -> None:
        models = _models()
        parsed = _parse(valid_input.values)
        postgres = parsed.connection(models.DependencyId.POSTGRES)
        redis = parsed.connection(models.DependencyId.REDIS)
        grafana = parsed.connection(models.DependencyId.GRAFANA)
        assert postgres.container_url == (
            f"postgresql://app:{valid_input.pg_secret}@postgres:5432/tokenmarket"
        )
        assert redis.container_url == (
            f"redis://default:{valid_input.redis_secret}@redis:6379/0"
        )
        assert grafana.container_url == "http://grafana:3000"

    def test_container_endpoints_are_canonical(self, valid_input: _ValidInput) -> None:
        models = _models()
        parsed = _parse(valid_input.values)
        expected = {
            models.DependencyId.POSTGRES: ("postgres", 5432),
            models.DependencyId.REDIS: ("redis", 6379),
            models.DependencyId.GRAFANA: ("grafana", 3000),
        }
        for dependency_id, (host, port) in expected.items():
            connection = parsed.connection(dependency_id)
            assert connection.container_host == host
            assert connection.container_port == port

    def test_custom_host_port_never_changes_container_port(
        self, valid_input: _ValidInput
    ) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            f"postgresql://app:{valid_input.pg_secret}@127.0.0.1:25432/tokenmarket"
        )
        models = _models()
        parsed = _parse(values)
        postgres = parsed.connection(models.DependencyId.POSTGRES)
        assert postgres.host_port == 25432
        assert postgres.container_port == 5432
        assert postgres.container_url == (
            f"postgresql://app:{valid_input.pg_secret}@postgres:5432/tokenmarket"
        )

    def test_displayed_endpoints_strip_user_info(
        self, valid_input: _ValidInput
    ) -> None:
        parsed = _parse(valid_input.values)
        endpoints = parsed.displayed_endpoints()
        assert endpoints == {
            "postgres": "postgresql://127.0.0.1:5432/tokenmarket",
            "redis": "redis://127.0.0.1:6379/0",
            "grafana": "http://127.0.0.1:3000",
        }
        for endpoint in endpoints.values():
            assert "@" not in endpoint
        secrets = (
            valid_input.pg_secret,
            valid_input.redis_secret,
            valid_input.grafana_secret,
        )
        for secret in secrets:
            assert all(secret not in endpoint for endpoint in endpoints.values())

    def test_repr_and_str_exclude_secrets_and_urls(
        self, valid_input: _ValidInput
    ) -> None:
        models = _models()
        parsed = _parse(valid_input.values)
        surface = repr(parsed) + str(parsed)
        for connection in parsed.connections:
            surface += repr(connection) + str(connection)
        for secret in (
            valid_input.pg_secret,
            valid_input.redis_secret,
            valid_input.grafana_secret,
        ):
            assert secret not in surface
        postgres = parsed.connection(models.DependencyId.POSTGRES)
        assert postgres.container_url not in surface

    def test_secret_bytes_are_excluded_from_equality(
        self, valid_input: _ValidInput
    ) -> None:
        first = _parse(valid_input.values)
        other = dict(valid_input.values)
        other["GRAFANA_ADMIN_PASSWORD"] = "tm_local_" + "z" * 40
        second = _parse(other)
        assert first == second

    def test_inequality_when_facts_differ(self, valid_input: _ValidInput) -> None:
        first = _parse(valid_input.values)
        other = dict(valid_input.values)
        other["GRAFANA_URL"] = "http://127.0.0.1:13001"
        second = _parse(other)
        assert first != second


class TestFieldNameOnlyErrors:
    def test_database_url_error_names_field_not_value(
        self, valid_input: _ValidInput
    ) -> None:
        values = dict(valid_input.values)
        values["DATABASE_URL"] = (
            "postgresql://app:totally-bogus-secret-value@127.0.0.1:5432/tokenmarket"
        )
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        message = str(exc_info.value)
        assert "DATABASE_URL" in message
        assert "totally-bogus-secret-value" not in message

    def test_grafana_admin_error_names_field_not_value(
        self, valid_input: _ValidInput
    ) -> None:
        values = dict(valid_input.values)
        values["GRAFANA_ADMIN_PASSWORD"] = "bogus-admin-value-that-must-not-leak"
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(values)
        message = str(exc_info.value)
        assert "GRAFANA_ADMIN_PASSWORD" in message
        assert "bogus-admin-value-that-must-not-leak" not in message

    def test_malformed_line_is_not_echoed(self, valid_input: _ValidInput) -> None:
        text = _render(valid_input.values) + "raw junk line must not leak\n"
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _config().parse_local_environment(text)
        assert "raw junk line must not leak" not in str(exc_info.value)

    @pytest.mark.parametrize(
        "field", ["DATABASE_URL", "REDIS_URL", "GRAFANA_URL", "GRAFANA_ADMIN_PASSWORD"]
    )
    def test_missing_field_names_only_itself(
        self, valid_input: _ValidInput, field: str
    ) -> None:
        with pytest.raises(_config().InvalidConfigError) as exc_info:
            _parse(valid_input.values, drop=(field,))
        message = str(exc_info.value)
        assert field in message
        for other in _FIELD_ORDER:
            if other not in (field, "MODE"):
                assert other not in message


def _connection(
    config: Any, models: Any, dependency: str, *, host_port: int, secret: str
) -> Any:
    if dependency == "postgres":
        return config.DerivedConnection(
            dependency_id=models.DependencyId.POSTGRES,
            host_scheme="postgresql",
            host_address="127.0.0.1",
            host_port=host_port,
            container_host="postgres",
            container_port=5432,
            username="app",
            database="tokenmarket",
            secret=secret,
            container_url=f"postgresql://app:{secret}@postgres:5432/tokenmarket",
        )
    if dependency == "redis":
        return config.DerivedConnection(
            dependency_id=models.DependencyId.REDIS,
            host_scheme="redis",
            host_address="127.0.0.1",
            host_port=host_port,
            container_host="redis",
            container_port=6379,
            username="default",
            database=0,
            secret=secret,
            container_url=f"redis://default:{secret}@redis:6379/0",
        )
    return config.DerivedConnection(
        dependency_id=models.DependencyId.GRAFANA,
        host_scheme="http",
        host_address="127.0.0.1",
        host_port=host_port,
        container_host="grafana",
        container_port=3000,
        username="admin",
        database=None,
        secret=secret,
        container_url="http://grafana:3000",
    )


class TestEntityInvariants:
    def test_non_loopback_host_is_rejected(self, synthetic_secret: str) -> None:
        import dataclasses

        config = _config()
        models = _models()
        postgres = _connection(
            config, models, "postgres", host_port=5432, secret=synthetic_secret
        )
        with pytest.raises(ValueError):
            dataclasses.replace(postgres, host_address="0.0.0.0")

    def test_non_canonical_container_endpoint_is_rejected(
        self, synthetic_secret: str
    ) -> None:
        import dataclasses

        config = _config()
        models = _models()
        postgres = _connection(
            config, models, "postgres", host_port=5432, secret=synthetic_secret
        )
        with pytest.raises(ValueError):
            dataclasses.replace(postgres, container_port=15432)

    def test_out_of_range_host_port_is_rejected(self, synthetic_secret: str) -> None:
        config = _config()
        models = _models()
        with pytest.raises(ValueError):
            _connection(
                config, models, "postgres", host_port=0, secret=synthetic_secret
            )

    def test_wrong_database_type_is_rejected(self, synthetic_secret: str) -> None:
        import dataclasses

        config = _config()
        models = _models()
        redis = _connection(
            config, models, "redis", host_port=6379, secret=synthetic_secret
        )
        with pytest.raises(ValueError):
            dataclasses.replace(redis, database="zero")

    def test_configuration_requires_local_mode(self, synthetic_secret: str) -> None:
        config = _config()
        models = _models()
        connections = (
            _connection(
                config, models, "postgres", host_port=5432, secret=synthetic_secret
            ),
            _connection(
                config, models, "redis", host_port=6379, secret=synthetic_secret
            ),
            _connection(
                config, models, "grafana", host_port=3000, secret=synthetic_secret
            ),
        )
        with pytest.raises(ValueError):
            config.LocalEnvironmentConfiguration(mode="test", connections=connections)

    def test_configuration_requires_all_three_dependencies(
        self, synthetic_secret: str
    ) -> None:
        config = _config()
        models = _models()
        connections = (
            _connection(
                config, models, "postgres", host_port=5432, secret=synthetic_secret
            ),
            _connection(
                config, models, "redis", host_port=6379, secret=synthetic_secret
            ),
        )
        with pytest.raises(ValueError):
            config.LocalEnvironmentConfiguration(mode="local", connections=connections)

    def test_configuration_rejects_duplicate_host_ports(
        self, synthetic_secret: str
    ) -> None:
        config = _config()
        models = _models()
        connections = (
            _connection(
                config, models, "postgres", host_port=5432, secret=synthetic_secret
            ),
            _connection(
                config, models, "redis", host_port=5432, secret=synthetic_secret
            ),
            _connection(
                config, models, "grafana", host_port=3000, secret=synthetic_secret
            ),
        )
        with pytest.raises(ValueError):
            config.LocalEnvironmentConfiguration(mode="local", connections=connections)
