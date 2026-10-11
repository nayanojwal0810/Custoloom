"""Unit tests for configuration validation."""

import pytest
import os
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


def test_app_config_defaults():
    """Verify that AppConfig initializes standard directory paths."""
    app_cfg = AppConfig.load()
    assert app_cfg.data_raw_dir.name == "raw"
    assert app_cfg.data_processed_dir.name == "processed"
    assert app_cfg.environment in ("development", "test", "production")
