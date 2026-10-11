"""Unit tests for configuration validation."""

import os
from pathlib import Path
import pytest
from custoloom.config import DatabaseConfig, ConfigurationError, AppConfig


def test_database_config_missing_credentials():
    """Verify that DatabaseConfig raises ConfigurationError when credentials are missing."""
    env_backup = dict(os.environ)
    try:
        os.environ.pop("CUSTOLOOM_DB_USER", None)
        os.environ.pop("DB_USER", None)
        os.environ.pop("CUSTOLOOM_DB_PASSWORD", None)
        os.environ.pop("DB_PASSWORD", None)

        with pytest.raises(ConfigurationError, match="Missing required database settings"):
            DatabaseConfig.from_env()
    finally:
        os.environ.clear()
        os.environ.update(env_backup)


def test_database_config_valid(monkeypatch):
    """Verify that DatabaseConfig loads successfully when credentials are provided."""
    monkeypatch.setenv("CUSTOLOOM_DB_USER", "custo_user")
    monkeypatch.setenv("CUSTOLOOM_DB_PASSWORD", "secret123")
    monkeypatch.setenv("CUSTOLOOM_DB_NAME", "custoloom_db")
    monkeypatch.setenv("CUSTOLOOM_DB_PORT", "5432")

    cfg = DatabaseConfig.from_env()
    assert cfg.user == "custo_user"
    assert cfg.name == "custoloom_db"
    assert cfg.port == 5432

    summary = cfg.safe_summary()
    assert summary["user"] == "custo_user"
    assert summary["database"] == "custoloom_db"
    assert summary["password_configured"] is True
    # Ensure raw secret is not in the summary dictionary values
    assert "secret123" not in summary.values()


def test_database_config_loads_dotenv_file(tmp_path):
    """Verify that DatabaseConfig.from_env loads variables from an explicit .env file."""
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "CUSTOLOOM_DB_HOST=127.0.0.1\n"
        "CUSTOLOOM_DB_PORT=5433\n"
        "CUSTOLOOM_DB_NAME=custoloom_test\n"
        "CUSTOLOOM_DB_USER=test_user\n"
        "CUSTOLOOM_DB_PASSWORD=test_pass\n",
        encoding="utf-8",
    )

    env_backup = dict(os.environ)
    try:
        cfg = DatabaseConfig.from_env(env_file=env_file)
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 5433
        assert cfg.name == "custoloom_test"
        assert cfg.user == "test_user"
        assert cfg.password == "test_pass"
    finally:
        os.environ.clear()
        os.environ.update(env_backup)


def test_app_config_defaults():
    """Verify that AppConfig initializes standard directory paths."""
    app_cfg = AppConfig.load()
    assert app_cfg.data_raw_dir.name == "raw"
    assert app_cfg.data_processed_dir.name == "processed"
    assert app_cfg.environment in ("development", "test", "production")
