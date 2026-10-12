"""Tests for DuckDB database utilities, safe sample streaming, and staging migrations."""

import gzip
from pathlib import Path
import pytest

from custoloom.config import DatabaseConfig, DatabaseConnectionError
from custoloom.db import DatabaseManager, stream_csv_sample
from custoloom.staging import validate_basket_invariants

SQL_SCRIPT = Path(__file__).resolve().parent.parent / "sql" / "001_create_staging_tables.sql"


@pytest.fixture
def synthetic_raw_data_dir(tmp_path):
    """Generate temporary synthetic CSV and gzip datasets for isolated streaming tests."""
    raw_dir = tmp_path / "synthetic_raw"
    raw_dir.mkdir()

    # clients.csv
    clients_lines = ["client_id,first_issue_date,first_redeem_date,age,gender\n"]
    for i in range(15):
        clients_lines.append(f"c{i:03d},2018-01-01 10:00:00,,30,M\n")
    (raw_dir / "clients.csv").write_text("".join(clients_lines), encoding="utf-8")

    # products.csv
    prod_lines = ["product_id,level_1,level_2,level_3,level_4,segment_id,brand_id,vendor_id,netto,is_own_trademark,is_alcohol\n"]
    for i in range(10):
        prod_lines.append(f"p{i:03d},CatA,Sub1,L3,L4,1.0,B1,V1,100,0,0\n")
    (raw_dir / "products.csv").write_text("".join(prod_lines), encoding="utf-8")

    # uplift_train.csv
    up_train_lines = ["client_id,treatment_flg,target\n"]
    for i in range(10):
        up_train_lines.append(f"c{i:03d},1,0\n")
    (raw_dir / "uplift_train.csv").write_text("".join(up_train_lines), encoding="utf-8")

    # uplift_test.csv
    up_test_lines = ["client_id\n"]
    for i in range(10):
        up_test_lines.append(f"c{i:03d}\n")
    (raw_dir / "uplift_test.csv").write_text("".join(up_test_lines), encoding="utf-8")

    # purchases.csv.gz
    purchases_lines = [
        "client_id,transaction_id,transaction_datetime,regular_points_received,express_points_received,"
        "regular_points_spent,express_points_spent,purchase_sum,store_id,product_id,product_quantity,"
        "trn_sum_from_iss,trn_sum_from_red\n"
    ]
    for i in range(25):
        purchases_lines.append(
            f"c001,t001,2019-01-01 10:00:00,10.0,0.0,0.0,0.0,200.0,s1,p{i:03d},1.0,100.0,\n"
        )
    with gzip.open(raw_dir / "purchases.csv.gz", "wt", encoding="utf-8") as f:
        f.writelines(purchases_lines)

    return raw_dir


def test_staging_ddl_behavioral_schema_validation():
    """Verify staging DDL script executes cleanly in isolated DuckDB with exact column types."""
    assert SQL_SCRIPT.exists(), f"DDL script not found at {SQL_SCRIPT}"
    cfg = DatabaseConfig(db_path=Path(":memory:"))
    manager = DatabaseManager(config=cfg)
    manager.execute_script(SQL_SCRIPT)

    expected_schemas = {
        "stg_clients": {
            "client_id": "VARCHAR",
            "first_issue_date": "TIMESTAMP",
            "first_redeem_date": "TIMESTAMP",
            "age": "INTEGER",
            "gender": "VARCHAR",
            "loaded_at": "TIMESTAMP",
        },
        "stg_products": {
            "product_id": "VARCHAR",
            "level_1": "VARCHAR",
            "level_2": "VARCHAR",
            "level_3": "VARCHAR",
            "level_4": "VARCHAR",
            "segment_id": "DOUBLE",
            "brand_id": "VARCHAR",
            "vendor_id": "VARCHAR",
            "netto": "DOUBLE",
            "is_own_trademark": "SMALLINT",
            "is_alcohol": "SMALLINT",
            "loaded_at": "TIMESTAMP",
        },
        "stg_purchases": {
            "source_row_number": "BIGINT",
            "client_id": "VARCHAR",
            "transaction_id": "VARCHAR",
            "transaction_datetime": "TIMESTAMP",
            "regular_points_received": "DOUBLE",
            "express_points_received": "DOUBLE",
            "regular_points_spent": "DOUBLE",
            "express_points_spent": "DOUBLE",
            "purchase_sum": "DOUBLE",
            "store_id": "VARCHAR",
            "product_id": "VARCHAR",
            "product_quantity": "DOUBLE",
            "trn_sum_from_iss": "DOUBLE",
            "trn_sum_from_red": "DOUBLE",
            "loaded_at": "TIMESTAMP",
        },
        "stg_uplift_train": {
            "client_id": "VARCHAR",
            "treatment_flg": "SMALLINT",
            "target": "SMALLINT",
            "loaded_at": "TIMESTAMP",
        },
        "stg_uplift_test": {
            "client_id": "VARCHAR",
            "loaded_at": "TIMESTAMP",
        },
        "v_baskets": {
            "client_id": "VARCHAR",
            "transaction_id": "VARCHAR",
            "transaction_datetime": "TIMESTAMP",
            "store_id": "VARCHAR",
            "purchase_sum": "DOUBLE",
            "regular_points_received": "DOUBLE",
            "regular_points_spent": "DOUBLE",
            "basket_line_count": "BIGINT",
            "basket_quantity": "DOUBLE",
            "basket_trn_sum_from_iss": "DOUBLE",
            "basket_trn_sum_from_red": "DOUBLE",
        },
        "v_basket_invariant_violations": {
            "client_id": "VARCHAR",
            "transaction_id": "VARCHAR",
            "min_dt": "TIMESTAMP",
            "max_dt": "TIMESTAMP",
            "cnt_dt": "BIGINT",
            "min_store": "VARCHAR",
            "max_store": "VARCHAR",
            "cnt_store": "BIGINT",
            "min_sum": "DOUBLE",
            "max_sum": "DOUBLE",
            "cnt_sum": "BIGINT",
            "min_reg_pts_recv": "DOUBLE",
            "max_reg_pts_recv": "DOUBLE",
            "cnt_reg_pts_recv": "BIGINT",
            "min_exp_pts_recv": "DOUBLE",
            "max_exp_pts_recv": "DOUBLE",
            "cnt_exp_pts_recv": "BIGINT",
            "min_reg_pts_spent": "DOUBLE",
            "max_reg_pts_spent": "DOUBLE",
            "cnt_reg_pts_spent": "BIGINT",
            "min_exp_pts_spent": "DOUBLE",
            "max_exp_pts_spent": "DOUBLE",
            "cnt_exp_pts_spent": "BIGINT",
            "basket_line_count": "BIGINT",
        },

    }

    with manager.get_connection(read_only=True) as conn:
        for relation_name, expected_cols in expected_schemas.items():
            pragma_info = conn.execute(f"PRAGMA table_info({relation_name});").fetchall()
            assert len(pragma_info) > 0, f"Relation {relation_name} was not created"
            actual_cols = {row[1]: row[2] for row in pragma_info}
            assert actual_cols == expected_cols, f"Column mismatch in {relation_name}: {actual_cols} != {expected_cols}"


def test_stream_csv_sample_clients(synthetic_raw_data_dir):
    """Verify streaming a small sample from flat clients.csv using synthetic fixtures."""
    clients_path = synthetic_raw_data_dir / "clients.csv"
    assert clients_path.exists(), f"Source clients.csv not found at {clients_path}"

    header, rows = stream_csv_sample(clients_path, max_rows=15, is_gzip=False)
    assert header == ["client_id", "first_issue_date", "first_redeem_date", "age", "gender"]
    assert len(rows) == 15
    for row in rows:
        assert len(row) == 5
        assert row[0] is not None  # client_id must be populated


def test_stream_csv_sample_products_and_uplift(synthetic_raw_data_dir):
    """Verify streaming samples from products, uplift_train, and uplift_test datasets."""
    products_path = synthetic_raw_data_dir / "products.csv"
    header_p, rows_p = stream_csv_sample(products_path, max_rows=10, is_gzip=False)
    assert header_p[0] == "product_id"
    assert len(rows_p) == 10

    uplift_path = synthetic_raw_data_dir / "uplift_train.csv"
    header_u, rows_u = stream_csv_sample(uplift_path, max_rows=10, is_gzip=False)
    assert header_u == ["client_id", "treatment_flg", "target"]
    assert len(rows_u) == 10
    for row in rows_u:
        assert row[1] in ("0", "1")
        assert row[2] in ("0", "1")

    uplift_test_path = synthetic_raw_data_dir / "uplift_test.csv"
    header_t, rows_t = stream_csv_sample(uplift_test_path, max_rows=10, is_gzip=False)
    assert header_t == ["client_id"]
    assert len(rows_t) == 10


def test_stream_csv_sample_purchases_gzip(synthetic_raw_data_dir):
    """Verify streaming from compressed purchases.csv.gz without full decompression."""
    purchases_path = synthetic_raw_data_dir / "purchases.csv.gz"
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


@pytest.mark.integration
def test_duckdb_persistent_read_only_status():
    """Verify live read-only inspection of persistent DuckDB staging database.

    Opt-in integration test: runs only when --run-integration or CUSTOLOOM_RUN_INTEGRATION_TESTS=1.
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

    # Confirm canonical basket view exists and is queryable
    with manager.get_connection(read_only=True) as conn:
        basket_check = conn.execute("SELECT client_id, transaction_id, purchase_sum FROM v_baskets LIMIT 1;").fetchone()
        assert basket_check is not None
        assert len(basket_check) == 3


def test_v_baskets_multiline_grain_and_invariants(tmp_path):
    """Verify that v_baskets collapses multi-line baskets into 1 row without multiplying purchase_sum."""
    db_file = tmp_path / "baskets_test.duckdb"
    cfg = DatabaseConfig(db_path=db_file)
    manager = DatabaseManager(config=cfg)
    manager.execute_script(SQL_SCRIPT)

    # Insert 3 line items belonging to the same basket (client c1, transaction t1)
    cols = [
        "source_row_number",
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
    rows = [
        [1, "c1", "t1", "2019-01-01 10:00:00", 15.0, 0.0, 0.0, 0.0, 350.0, "s1", "p1", 1.0, 100.0, None],
        [2, "c1", "t1", "2019-01-01 10:00:00", 15.0, 0.0, 0.0, 0.0, 350.0, "s1", "p2", 2.0, 150.0, None],
        [3, "c1", "t1", "2019-01-01 10:00:00", 15.0, 0.0, 0.0, 0.0, 350.0, "s1", "p3", 1.5, 100.0, None],
    ]
    manager.load_sample_batch("stg_purchases", cols, rows)

    with manager.get_connection(read_only=True) as conn:
        res = conn.execute("""
            SELECT 
                client_id, transaction_id, transaction_datetime, store_id, 
                purchase_sum, regular_points_received, basket_line_count, 
                basket_quantity, basket_trn_sum_from_iss
            FROM v_baskets;
        """).fetchall()

        assert len(res) == 1
        basket = res[0]
        assert basket[0] == "c1"
        assert basket[1] == "t1"
        assert str(basket[2]) == "2019-01-01 10:00:00"
        assert basket[3] == "s1"
        assert basket[4] == 350.0  # NOT multiplied to 1050.0
        assert basket[5] == 15.0   # NOT multiplied to 45.0
        assert basket[6] == 3      # Exactly 3 lines
        assert basket[7] == 4.5    # Sum of quantities (1.0 + 2.0 + 1.5)
        assert basket[8] == 350.0  # Sum of line item sums

    # Verify that consistent multi-line baskets produce zero violations
    clean_report = validate_basket_invariants(manager)
    assert clean_report["total_violations"] == 0
    assert clean_report["violations"] == []


def test_v_baskets_inconsistent_attribute_handling(tmp_path):
    """Verify that production validation function and view detect discordant basket attributes."""
    db_file = tmp_path / "inconsistent_test.duckdb"
    cfg = DatabaseConfig(db_path=db_file)
    manager = DatabaseManager(config=cfg)
    manager.execute_script(SQL_SCRIPT)

    cols = [
        "source_row_number",
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
    # Synthetic inconsistent basket: line 1 reports store s1 / sum 300, line 2 reports store s2 / sum 350
    rows = [
        [1, "c1", "t_bad", "2019-01-01 10:00:00", 10.0, 0.0, 0.0, 0.0, 300.0, "s1", "p1", 1.0, 300.0, None],
        [2, "c1", "t_bad", "2019-01-01 10:05:00", 15.0, 0.0, 0.0, 0.0, 350.0, "s2", "p2", 1.0, 350.0, None],
    ]
    manager.load_sample_batch("stg_purchases", cols, rows)

    # 1. Verify production validation function catches the conflict
    report = validate_basket_invariants(manager)
    assert report["total_violations"] == 1
    viol = report["violations"][0]
    assert viol["client_id"] == "c1"
    assert viol["transaction_id"] == "t_bad"
    assert viol["min_store"] == "s1"
    assert viol["max_store"] == "s2"
    assert viol["min_sum"] == 300.0
    assert viol["max_sum"] == 350.0
    assert viol["basket_line_count"] == 2

    with manager.get_connection(read_only=True) as conn:
        # 2. Verify v_basket_invariant_violations view catches the conflict
        view_viols = conn.execute("SELECT client_id, transaction_id, min_store, max_store FROM v_basket_invariant_violations;").fetchall()
        assert len(view_viols) == 1
        assert view_viols[0] == ("c1", "t_bad", "s1", "s2")

        # 3. View aggregates using MAX deterministically
        view_row = conn.execute("SELECT store_id, purchase_sum, basket_line_count FROM v_baskets;").fetchone()
        assert view_row == ("s2", 350.0, 2)


def test_v_baskets_partial_null_attribute_handling(tmp_path):
    """Verify that partially NULL attributes within a basket are flagged as invariant violations."""
    db_file = tmp_path / "partial_null_test.duckdb"
    cfg = DatabaseConfig(db_path=db_file)
    manager = DatabaseManager(config=cfg)
    manager.execute_script(SQL_SCRIPT)

    cols = [
        "source_row_number",
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
    # Synthetic basket where line 1 has regular_points_received = 10.0 and line 2 has NULL
    rows = [
        [1, "c2", "t_part_null", "2019-01-01 10:00:00", 10.0, 0.0, 0.0, 0.0, 200.0, "s1", "p1", 1.0, 100.0, None],
        [2, "c2", "t_part_null", "2019-01-01 10:00:00", None, 0.0, 0.0, 0.0, 200.0, "s1", "p2", 1.0, 100.0, None],
    ]
    manager.load_sample_batch("stg_purchases", cols, rows)

    # 1. Verify production validation function catches the partial NULL
    report = validate_basket_invariants(manager)
    assert report["total_violations"] == 1
    viol = report["violations"][0]
    assert viol["client_id"] == "c2"
    assert viol["transaction_id"] == "t_part_null"
    assert viol["min_reg_pts_recv"] == 10.0
    assert viol["max_reg_pts_recv"] == 10.0
    assert viol["cnt_reg_pts_recv"] == 1  # 1 non-null out of 2 lines
    assert viol["basket_line_count"] == 2

    # 2. Verify v_basket_invariant_violations view catches the violation
    with manager.get_connection(read_only=True) as conn:
        view_viols = conn.execute("SELECT client_id, transaction_id, cnt_reg_pts_recv, basket_line_count FROM v_basket_invariant_violations;").fetchall()
        assert len(view_viols) == 1
        assert view_viols[0] == ("c2", "t_part_null", 1, 2)


def test_validate_basket_invariants_missing_table_fails(tmp_path):
    """Verify that validate_basket_invariants reports a validation error when stg_purchases is missing."""
    empty_db = tmp_path / "empty.duckdb"
    manager = DatabaseManager(config=DatabaseConfig(db_path=empty_db))
    # No DDL executed, table stg_purchases does not exist

    with pytest.raises(RuntimeError, match="Validation error: required table 'stg_purchases' does not exist"):
        validate_basket_invariants(manager)




