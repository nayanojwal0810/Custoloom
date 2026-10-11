"""Tests for database utilities, safe sample streaming, and staging migrations."""

import os
from pathlib import Path
import pytest
from psycopg import sql

from custoloom.config import ConfigurationError, DatabaseConfig, DatabaseConnectionError
from custoloom.db import DatabaseManager, stream_csv_sample, load_all_staging_samples

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


def test_database_manager_fails_cleanly_when_unconfigured(tmp_path, monkeypatch):
    """Verify DatabaseManager raises ConfigurationError when settings are absent."""
    empty_env = tmp_path / ".env.empty"
    empty_env.write_text("", encoding="utf-8")
    monkeypatch.delenv("CUSTOLOOM_DB_USER", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("CUSTOLOOM_DB_PASSWORD", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    manager = DatabaseManager(env_file=empty_env)
    with pytest.raises(ConfigurationError, match="Missing required database settings"):
        _ = manager.config


def test_failed_connection_produces_safe_error():
    """Verify that a failed connection produces a clear, safe error without leaking passwords."""
    cfg = DatabaseConfig(
        host="127.0.0.1",
        port=59999,
        name="nonexistent_db",
        user="test_user",
        password="super_secret_password_12345",
        connect_timeout=1,
    )
    manager = DatabaseManager(config=cfg)
    with pytest.raises(DatabaseConnectionError) as exc_info:
        manager.get_connection()

    err_str = str(exc_info.value)
    assert "super_secret_password_12345" not in err_str
    assert "nonexistent_db" in err_str
    assert "59999" in err_str


def test_postgres_integration_status():
    """Verify integration test state: executes migration & validation if target DB is reachable, skips cleanly if blocked."""
    try:
        manager = DatabaseManager()
        _ = manager.config
    except ConfigurationError as err:
        pytest.skip(f"PostgreSQL live integration blocked: {err}")

    try:
        server_ver, db_name, port = manager.get_server_version()
    except DatabaseConnectionError as err:
        pytest.skip(f"PostgreSQL live integration blocked: {err}")

    assert server_ver is not None
    assert db_name == manager.config.name
    assert port == manager.config.port

    # Verify existing tables safely without dropping
    for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train"):
        manager.inspect_table_exists(tbl)

    # Execute staging DDL safely
    manager.execute_script(SQL_SCRIPT)

    # Verify tables created
    for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train"):
        cols = manager.inspect_table_columns(tbl)
        assert len(cols) > 0, f"Table {tbl} has no columns or does not exist."

    # Load and verify small staging samples
    counts = load_all_staging_samples(
        manager,
        RAW_DATA_DIR,
        sample_sizes={"clients": 50, "products": 50, "purchases": 50, "uplift_train": 50},
        truncate_first=True,
    )
    for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train"):
        assert counts.get(tbl, 0) == 50, f"Unexpected row count for {tbl}: {counts.get(tbl)}"
