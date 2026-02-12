from shared.runtime_settings import (
    DEFAULT_DEV_CORS_ALLOW_ORIGINS,
    env_flag,
    load_security_settings,
    parse_cors_allowlist,
)


def test_env_flag_truthy_and_falsey() -> None:
    assert env_flag("X", default=False, environ={"X": "true"}) is True
    assert env_flag("X", default=True, environ={"X": "0"}) is False


def test_parse_cors_allowlist_uses_fallback_when_empty() -> None:
    assert parse_cors_allowlist("") == list(DEFAULT_DEV_CORS_ALLOW_ORIGINS)


def test_parse_cors_allowlist_parses_csv_values() -> None:
    raw = " http://localhost:3000, https://example.com "
    assert parse_cors_allowlist(raw) == ["http://localhost:3000", "https://example.com"]


def test_load_security_settings_reads_expected_keys() -> None:
    settings = load_security_settings(
        {
            "STORYTELLER_DEV_MODE": "false",
            "STORYTELLER_API_TOKEN": "abc123",
            "STORYTELLER_CORS_ALLOW_ORIGINS": "https://app.example.com",
        }
    )
    assert settings.dev_mode is False
    assert settings.api_token == "abc123"
    assert settings.cors_allow_origins == ["https://app.example.com"]
