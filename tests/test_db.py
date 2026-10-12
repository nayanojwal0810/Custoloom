"""Tests for DuckDB database utilities, safe sample streaming, and staging migrations."""

from pathlib import Path
import pytest

from custoloom.config import DatabaseConfig, DatabaseConnectionError
from custoloom.db import DatabaseManager, stream_csv_sample

RAW_DATA_DIR = Path("D:/DA projects/optispend-engine/data/raw")
SQL_SCRIPT = Path(__file__).resolve().parent.parent / "sql" / "001_create_staging_tables.sql"


def test_ddl_script_structure():
    """Verify that the staging DDL script defines all five required tables safely."""
    assert SQL_SCRIPT.exists(), f"DDL script not found at {SQL_SCRIPT}"
    content = SQL_SCRIPT.read_text(encoding="utf-8")
    for table_name in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train", "stg_uplift_test"):
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
    """Verify streaming samples from products, uplift_train, and uplift_test datasets."""
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

    uplift_test_path = RAW_DATA_DIR / "uplift_test.csv"
    header_t, rows_t = stream_csv_sample(uplift_test_path, max_rows=10, is_gzip=False)
    assert header_t == ["client_id"]
    assert len(rows_t) == 10


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
        if row[12] == "":
            pytest.fail("Empty string was not converted to None (SQL NULL)")


def test_duckdb_manager_in_memory():
    """Verify DatabaseManager connects cleanly to an in-memory database."""
    cfg = DatabaseConfig(db_path=Path(":memory:"), threads=2, memory_limit="512MB")
    manager = DatabaseManager(config=cfg)
    with manager.get_connection() as conn:
        res = conn.execute("SELECT 42;").fetchone()
        assert res[0] == 42


def test_duckdb_schema_and_batch_operations():
    """Verify executing staging DDL and table inspection in an in-memory DuckDB."""
    cfg = DatabaseConfig(db_path=Path(":memory:"))
    manager = DatabaseManager(config=cfg)

    # Execute DDL
    manager.execute_script(SQL_SCRIPT)

    # Verify tables created
    for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train", "stg_uplift_test"):
        assert manager.inspect_table_exists(tbl)
        cols = manager.inspect_table_columns(tbl)
        assert len(cols) > 0

    # Test sample batch insert
    cols = ["client_id", "first_issue_date", "first_redeem_date", "age", "gender"]
    sample_rows = [
        ["00001", "2018-01-01 10:00:00", None, 30, "M"],
        ["00002", "2018-02-01 12:00:00", "2018-03-01 15:00:00", 45, "F"],
    ]
    loaded = manager.load_sample_batch("stg_clients", cols, sample_rows, conflict_key="client_id")
    assert loaded == 2
    assert manager.fetch_row_count("stg_clients") == 2

    # Verify idempotency on conflict
    loaded_again = manager.load_sample_batch("stg_clients", cols, sample_rows, conflict_key="client_id")
    assert loaded_again == 2
    assert manager.fetch_row_count("stg_clients") == 2


def test_duckdb_persistent_read_only_status():
    """Verify live read-only inspection of persistent DuckDB staging database.

    Ordinary pytest runs do not create databases or modify real staging data.
    """
    manager = DatabaseManager()
    # Confirm database is queryable
    with manager.get_connection(read_only=True) as conn:
        res = conn.execute("SELECT 1;").fetchone()
        assert res[0] == 1

    for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train", "stg_uplift_test"):
        assert manager.inspect_table_exists(tbl)
        cols = manager.inspect_table_columns(tbl)
        assert len(cols) > 0
        count = manager.fetch_row_count(tbl)
        assert count >= 0
