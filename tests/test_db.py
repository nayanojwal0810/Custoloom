"""Tests for database utilities, safe sample streaming, and staging migrations."""

import os
from pathlib import Path
import pytest
from psycopg import sql

from custoloom.config import ConfigurationError, DatabaseConfig
from custoloom.db import DatabaseManager, stream_csv_sample

RAW_DATA_DIR = Path("D:/DA projects/optispend-engine/data/raw")
SQL_SCRIPT = Path(__file__).resolve().parent.parent / "sql" / "001_create_staging_tables.sql"


def test_ddl_script_structure():
    """Verify that the staging DDL script defines all four required tables safely."""
    assert SQL_SCRIPT.exists(), f"DDL script not found at {SQL_SCRIPT}"
    content = SQL_SCRIPT.read_text(encoding="utf-8")
    for table_name in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train"):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in content
        assert "loaded_at TIMESTAMP" in content


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


def test_stream_csv_sample_products_and_uplift():
    """Verify streaming samples from products and uplift_train datasets."""
    products_path = RAW_DATA_DIR / "products.csv"
    header_p, rows_p = stream_csv_sample(products_path, max_rows=10, is_gzip=False)
    assert header_p[0] == "product_id"
    assert len(rows_p) == 10

    uplift_path = RAW_DATA_DIR / "uplift_train.csv"
    header_u, rows_u = stream_csv_sample(uplift_path, max_rows=10, is_gzip=False)
    assert header_u == ["client_id", "treatment_flg", "target"]
    assert len(rows_u) == 10
    for row in rows_u:
        assert row[1] in ("0", "1")
        assert row[2] in ("0", "1")


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
        # Confirm empty string fields map to None
        if row[12] == "":
            pytest.fail("Empty string was not converted to None (SQL NULL)")


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
        missing = []
        if not user:
            missing.append("CUSTOLOOM_DB_USER / DB_USER")
        if not password:
            missing.append("CUSTOLOOM_DB_PASSWORD / DB_PASSWORD")

        pytest.skip(
            f"PostgreSQL live integration blocked: missing required settings ({', '.join(missing)})."
        )

    # When credentials are provided, test live connection and table migration
    manager = DatabaseManager()
    server_ver, db_name, port = manager.get_server_version()
    assert server_ver is not None
    assert db_name == manager.config.name
    assert port == manager.config.port

    # Execute staging DDL
    manager.execute_script(SQL_SCRIPT)

    # Verify tables created
    for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train"):
        cols = manager.inspect_table_columns(tbl)
        assert len(cols) > 0, f"Table {tbl} has no columns or does not exist."
