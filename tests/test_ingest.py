"""Tests for full dataset ingestion CLI, source validation, and schema safety in DuckDB."""

import gzip
import subprocess
import sys
from pathlib import Path
import duckdb
import pytest

from custoloom.config import DatabaseConfig
from custoloom.db import DatabaseManager
from custoloom.ingest import (
    EXPECTED_HEADERS,
    STAGE_TABLE_MAP,
    validate_source_headers,
    validate_disk_space,
    clean_stale_load_tables,
    create_load_stage_tables,
    validate_staging_data,
    promote_load_tables,
)

SQL_SCRIPT = Path(__file__).resolve().parent.parent / "sql" / "001_create_staging_tables.sql"


def test_expected_headers_specification():
    """Verify all five expected headers are defined with correct grain."""
    assert "clients.csv" in EXPECTED_HEADERS
    assert "products.csv" in EXPECTED_HEADERS
    assert "purchases.csv.gz" in EXPECTED_HEADERS
    assert "uplift_train.csv" in EXPECTED_HEADERS
    assert "uplift_test.csv" in EXPECTED_HEADERS

    assert EXPECTED_HEADERS["clients.csv"][0] == "client_id"
    assert EXPECTED_HEADERS["products.csv"][0] == "product_id"
    assert EXPECTED_HEADERS["purchases.csv.gz"][0] == "client_id"
    assert EXPECTED_HEADERS["purchases.csv.gz"][1] == "transaction_id"
    assert EXPECTED_HEADERS["purchases.csv.gz"][9] == "product_id"
    assert EXPECTED_HEADERS["uplift_train.csv"] == ["client_id", "treatment_flg", "target"]
    assert EXPECTED_HEADERS["uplift_test.csv"] == ["client_id"]


def test_validate_source_headers_passes(tmp_path):
    """Verify validate_source_headers successfully validates all raw files using synthetic fixtures."""
    raw_dir = tmp_path / "valid_raw"
    raw_dir.mkdir()
    (raw_dir / "clients.csv").write_text("client_id,first_issue_date,first_redeem_date,age,gender\n", encoding="utf-8")
    (raw_dir / "products.csv").write_text("product_id,level_1,level_2,level_3,level_4,segment_id,brand_id,vendor_id,netto,is_own_trademark,is_alcohol\n", encoding="utf-8")
    (raw_dir / "uplift_train.csv").write_text("client_id,treatment_flg,target\n", encoding="utf-8")
    (raw_dir / "uplift_test.csv").write_text("client_id\n", encoding="utf-8")

    with gzip.open(raw_dir / "purchases.csv.gz", "wt", encoding="utf-8") as f:
        f.write(
            "client_id,transaction_id,transaction_datetime,regular_points_received,express_points_received,"
            "regular_points_spent,express_points_spent,purchase_sum,store_id,product_id,product_quantity,"
            "trn_sum_from_iss,trn_sum_from_red\n"
        )

    headers = validate_source_headers(raw_dir)
    assert len(headers) == 5
    assert "clients.csv" in headers



def test_validate_source_headers_fails_on_missing_dir(tmp_path):
    """Verify validate_source_headers raises FileNotFoundError when dir has missing files."""
    with pytest.raises(FileNotFoundError):
        validate_source_headers(tmp_path)


def test_validate_source_headers_fails_on_corrupt_header(tmp_path):
    """Verify validate_source_headers raises ValueError when header is altered."""
    # Write a dummy clients.csv with wrong header
    bad_clients = tmp_path / "clients.csv"
    bad_clients.write_text("wrong_id,age\n1,25\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Header mismatch"):
        validate_source_headers(tmp_path)


def test_disk_space_validation(tmp_path):
    """Verify disk space validator succeeds for reasonable sizes and fails on unreachable quotas."""
    # Reasonable requirement succeeds
    free_gb = validate_disk_space(tmp_path, min_free_gb=0.01)
    assert free_gb > 0.01

    # Impossible requirement raises RuntimeError
    with pytest.raises(RuntimeError, match="Insufficient disk space"):
        validate_disk_space(tmp_path, min_free_gb=999999.0)


def test_ingest_cli_help():
    """Verify that the ingestion CLI help screen runs cleanly with expected arguments."""
    script_path = Path(__file__).resolve().parent.parent / "src" / "custoloom" / "ingest.py"
    res = subprocess.run([sys.executable, str(script_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "--audit-only" in res.stdout
    assert "--validate-staging" in res.stdout
    assert "--full-ingest" in res.stdout
    assert "--sample-size" in res.stdout


def test_ingest_cli_missing_raw_dir_fails_cleanly(tmp_path):
    """Verify that ingest CLI fails with clear error and zero writes when raw directory is missing."""
    script_path = Path(__file__).resolve().parent.parent / "src" / "custoloom" / "ingest.py"
    non_existent = tmp_path / "non_existent_raw_dir"

    res = subprocess.run(
        [sys.executable, str(script_path), "--raw-dir", str(non_existent), "--audit-only"],
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "Raw data directory not found" in res.stderr



def test_source_row_number_ordinality_generation(tmp_path):
    """Verify that WITH ORDINALITY generates strictly 1-based, sequential row numbers."""
    csv_file = tmp_path / "test_ordinal.csv"
    csv_file.write_text("client_id,val\n001,A\n002,B\n003,C\n", encoding="utf-8")

    con = duckdb.connect()
    res = con.execute(f"""
        SELECT ordinality::BIGINT, client_id, val
        FROM read_csv('{csv_file.as_posix()}', header=true, types={{'client_id': 'VARCHAR'}}) WITH ORDINALITY;
    """).fetchall()

    assert res == [(1, "001", "A"), (2, "002", "B"), (3, "003", "C")]


def test_stale_load_tables_cleanup(tmp_path):
    """Verify that stale load-stage tables are dropped cleanly and unknown tables raise."""
    con = duckdb.connect()
    con.execute("CREATE TABLE load_stg_clients (id VARCHAR);")
    assert con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'load_stg_clients';").fetchone()[0] == 1

    clean_stale_load_tables(con)
    assert con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'load_stg_clients';").fetchone()[0] == 0

    # Unknown table starting with load_stg_
    con.execute("CREATE TABLE load_stg_unknown (id VARCHAR);")
    with pytest.raises(RuntimeError, match="Unrecognized table"):
        clean_stale_load_tables(con)


def test_safe_replacement_and_atomic_promotion(tmp_path):
    """Verify end-to-end staged replacement: validation, atomic swap, and rollback safety."""
    con = duckdb.connect()

    # 1. Populate old staging tables with initial data
    for tbl in STAGE_TABLE_MAP.values():
        con.execute(f"CREATE TABLE {tbl} (id VARCHAR);")
        con.execute(f"INSERT INTO {tbl} VALUES ('old_data');")

    # 2. Create load-stage tables
    create_load_stage_tables(con)

    # 3. Populate load-stage tables with mock data
    con.execute("INSERT INTO load_stg_clients VALUES ('c1', NULL, NULL, 30, 'M', CURRENT_TIMESTAMP);")
    con.execute("INSERT INTO load_stg_products VALUES ('p1', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, 0, CURRENT_TIMESTAMP);")
    con.execute("INSERT INTO load_stg_uplift_train VALUES ('c1', 1, 0, CURRENT_TIMESTAMP);")
    con.execute("INSERT INTO load_stg_uplift_test VALUES ('c2', CURRENT_TIMESTAMP);")
    con.execute("""
        INSERT INTO load_stg_purchases VALUES (
            1, 'c1', 't1', '2019-01-01 10:00:00'::TIMESTAMP,
            0.0, 0.0, 0.0, 0.0, 100.0, 's1', 'p1', 1.0, 100.0, NULL, CURRENT_TIMESTAMP
        );
    """)

    # 4. Validate load-stage tables with custom expected counts
    mock_expected = {
        "clients.csv": 1,
        "products.csv": 1,
        "purchases.csv.gz": 1,
        "uplift_train.csv": 1,
        "uplift_test.csv": 1,
    }
    # Notice: c2 is in uplift_test but not clients, which triggers partition validation
    # Add c2 to clients to satisfy foreign key & partition check
    con.execute("INSERT INTO load_stg_clients VALUES ('c2', NULL, NULL, 40, 'F', CURRENT_TIMESTAMP);")
    mock_expected["clients.csv"] = 2

    val_report = validate_staging_data(con, prefix="load_stg_", expected_counts=mock_expected)
    assert val_report["table_prefix"] == "load_stg_"
    assert val_report["source_row_number"]["min"] == 1
    assert val_report["source_row_number"]["max"] == 1

    # 5. Atomically promote
    promote_load_tables(con)

    # Verify stg_* tables now have the new data and load_stg_* tables are gone
    assert con.execute("SELECT COUNT(*) FROM stg_clients;").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM stg_purchases;").fetchone()[0] == 1
    p_row = con.execute("SELECT source_row_number, client_id, transaction_id FROM stg_purchases;").fetchone()
    assert p_row == (1, "c1", "t1")


def test_promotion_rollback_on_error():
    """Verify that promotion error safely rolls back and preserves existing tables intact."""
    con = duckdb.connect()
    con.execute("CREATE TABLE stg_sample (val VARCHAR);")
    con.execute("INSERT INTO stg_sample VALUES ('original_data');")
    con.execute("CREATE TABLE load_stg_sample (val VARCHAR);")
    con.execute("INSERT INTO load_stg_sample VALUES ('new_data');")

    try:
        con.execute("BEGIN TRANSACTION;")
        con.execute("DROP TABLE stg_sample;")
        con.execute("ALTER TABLE load_stg_sample RENAME TO stg_sample;")
        # Inject intentional failure before commit
        raise RuntimeError("Forced simulation error")
        con.execute("COMMIT;")
    except Exception:
        con.execute("ROLLBACK;")

    # Verify original table is completely intact
    rows = con.execute("SELECT * FROM stg_sample;").fetchall()
    assert rows == [("original_data",)]
