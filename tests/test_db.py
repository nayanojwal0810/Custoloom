"""Tests for database utilities and safe sample data streaming."""

import os
from pathlib import Path
import pytest

from custoloom.config import ConfigurationError, DatabaseConfig
from custoloom.db import DatabaseManager, stream_csv_sample

RAW_DATA_DIR = Path("D:/DA projects/optispend-engine/data/raw")
SQL_SCRIPT = Path(__file__).resolve().parent.parent / "sql" / "001_create_staging_tables.sql"


def test_ddl_script_structure():
    """Verify that the staging DDL script defines all four required tables."""
    assert SQL_SCRIPT.exists(), f"DDL script not found at {SQL_SCRIPT}"
    content = SQL_SCRIPT.read_text(encoding="utf-8")
    for table_name in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train"):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in content


def test_stream_csv_sample_clients():
    """Verify streaming a small sample from flat clients.csv."""
    clients_path = RAW_DATA_DIR / "clients.csv"
    assert clients_path.exists(), f"Source clients.csv not found at {clients_path}"

    header, rows = stream_csv_sample(clients_path, max_rows=15, is_gzip=False)
    assert header == ["client_id", "first_issue_date", "first_redeem_date", "age", "gender"]
    assert len(rows) == 15
    for row in rows:
        assert len(row) == 5
        assert row[0] is not None  # client_id must be populated


def test_stream_csv_sample_purchases_gzip():
    """Verify streaming from compressed purchases.csv.gz without full decompression."""
    purchases_path = RAW_DATA_DIR / "purchases.csv.gz"
    assert purchases_path.exists(), f"Source purchases.csv.gz not found at {purchases_path}"

    header, rows = stream_csv_sample(purchases_path, max_rows=25, is_gzip=True)
    expected_header = [
        "client_id",
        "transaction_id",
        "transaction_datetime",
        "regular_points_received",
        "express_points_received",
        "regular_points_spent",
        "express_points_spent",
        "purchase_sum",
        "store_id",
        "product_id",
        "product_quantity",
        "trn_sum_from_iss",
        "trn_sum_from_red",
    ]
    assert header == expected_header
    assert len(rows) == 25
    for row in rows:
        assert len(row) == 13
        assert row[0] is not None  # client_id
        assert row[1] is not None  # transaction_id


def test_database_manager_fails_cleanly_when_unconfigured():
    """Verify DatabaseManager raises ConfigurationError when settings are absent."""
    env_backup = dict(os.environ)
    try:
        os.environ.pop("CUSTOLOOM_DB_USER", None)
        os.environ.pop("DB_USER", None)
        os.environ.pop("CUSTOLOOM_DB_PASSWORD", None)
        os.environ.pop("DB_PASSWORD", None)

        manager = DatabaseManager()
        with pytest.raises(ConfigurationError, match="Missing required database settings"):
            _ = manager.config
    finally:
        os.environ.clear()
        os.environ.update(env_backup)


def test_postgres_integration_status():
    """Verify integration test state: runs if credentials configured, explicitly blocked otherwise."""
    user = os.getenv("CUSTOLOOM_DB_USER", os.getenv("DB_USER"))
    password = os.getenv("CUSTOLOOM_DB_PASSWORD", os.getenv("DB_PASSWORD"))

    if not user or not password:
        pytest.skip(
            "PostgreSQL integration blocked: missing DB_USER/DB_PASSWORD environment configuration."
        )

    # If configured, test connection lifecycle safely
    manager = DatabaseManager()
    with manager.get_connection() as conn:
        assert conn.closed is False
