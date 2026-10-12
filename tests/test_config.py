"""Unit tests for DuckDB configuration validation."""

import os
from pathlib import Path
import pytest
from custoloom.config import DatabaseConfig, ConfigurationError, AppConfig


def test_database_config_defaults():
    """Verify DatabaseConfig defaults to persistent DuckDB path."""
    cfg = DatabaseConfig.from_env()
    assert "custoloom.duckdb" in str(cfg.db_path)
    summary = cfg.safe_summary()
    assert "custoloom.duckdb" in str(summary["db_path"])


def test_database_config_env_override(monkeypatch):
    """Verify DatabaseConfig respects environment variable overrides."""
    monkeypatch.setenv("CUSTOLOOM_DB_PATH", ":memory:")
    monkeypatch.setenv("CUSTOLOOM_DB_THREADS", "4")
    monkeypatch.setenv("CUSTOLOOM_DB_MEMORY_LIMIT", "2GB")

    cfg = DatabaseConfig.from_env()
    assert str(cfg.db_path) == ":memory:"
    assert cfg.threads == 4
    assert cfg.memory_limit == "2GB"

    summary = cfg.safe_summary()
    assert summary["threads"] == 4
    assert summary["memory_limit"] == "2GB"


def test_database_config_invalid_threads(monkeypatch):
    """Verify DatabaseConfig raises ConfigurationError on invalid threads."""
    monkeypatch.setenv("CUSTOLOOM_DB_THREADS", "invalid_number")
    with pytest.raises(ConfigurationError, match="Invalid CUSTOLOOM_DB_THREADS"):
        DatabaseConfig.from_env()


def test_database_config_loads_dotenv_file(tmp_path):
    """Verify that DatabaseConfig.from_env loads variables from an explicit .env file."""
    env_file = tmp_path / ".env.test"
    custom_db = tmp_path / "custom.duckdb"
    env_file.write_text(
        f"CUSTOLOOM_DB_PATH={custom_db.as_posix()}\n"
        "CUSTOLOOM_DB_THREADS=2\n"
        "CUSTOLOOM_DB_MEMORY_LIMIT=1GB\n",
        encoding="utf-8",
    )

    env_backup = dict(os.environ)
    try:
        cfg = DatabaseConfig.from_env(env_file=env_file)
        assert cfg.db_path == custom_db
        assert cfg.threads == 2
        assert cfg.memory_limit == "1GB"
    finally:
        os.environ.clear()
        os.environ.update(env_backup)


def test_app_config_defaults():
    """Verify that AppConfig resolves paths correctly."""
    app_cfg = AppConfig.load()
    assert app_cfg.base_dir.exists()
    assert app_cfg.data_raw_dir.exists()
    assert "custoloom.duckdb" in str(app_cfg.db.db_path)
