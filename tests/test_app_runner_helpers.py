import pytest

from storyteller.runtime.app_runner import AppRunnerError, ensure_prod_env_safety, sanitize_config


def test_sanitize_config_redacts_secret_like_keys() -> None:
    cfg = {"api_token": "secret", "normal": "ok", "db_password": "pw"}
    out = sanitize_config(cfg)
    assert out["api_token"] == "***"
    assert out["db_password"] == "***"
    assert out["normal"] == "ok"


def test_ensure_prod_env_safety_allows_dev_mode() -> None:
    ensure_prod_env_safety({"STORYTELLER_DEV_MODE": "1"})


def test_ensure_prod_env_safety_requires_token_in_prod() -> None:
    with pytest.raises(AppRunnerError, match="STORYTELLER_API_TOKEN"):
        ensure_prod_env_safety(
            {
                "STORYTELLER_DEV_MODE": "0",
                "STORYTELLER_CORS_ALLOW_ORIGINS": "https://example.com",
            }
        )


def test_ensure_prod_env_safety_rejects_wildcard_cors_in_prod() -> None:
    with pytest.raises(AppRunnerError, match="wildcard CORS"):
        ensure_prod_env_safety(
            {
                "STORYTELLER_DEV_MODE": "false",
                "STORYTELLER_API_TOKEN": "abc",
                "STORYTELLER_CORS_ALLOW_ORIGINS": "*",
            }
        )


def test_ensure_prod_env_safety_accepts_explicit_cors_in_prod() -> None:
    ensure_prod_env_safety(
        {
            "STORYTELLER_DEV_MODE": "off",
            "STORYTELLER_API_TOKEN": "abc",
            "STORYTELLER_CORS_ALLOW_ORIGINS": "https://example.com,https://app.example.com",
        }
    )
