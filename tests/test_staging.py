"""Tests for staging module CLI and utilities."""

import subprocess
import sys
from pathlib import Path
import pytest

from custoloom.config import DatabaseConfig
from custoloom.db import DatabaseManager
from custoloom.staging import (
    get_existing_purchase_source_row_numbers,
    inspect_representative_records,
    load_staging_samples,
)


SQL_SCRIPT = Path(__file__).resolve().parent.parent / "sql" / "001_create_staging_tables.sql"


@pytest.fixture
def isolated_staging_manager(tmp_path):
    """Provide an isolated DuckDB manager with staging DDL and minimal sample data."""
    db_file = tmp_path / "staging_test.duckdb"
    cfg = DatabaseConfig(db_path=db_file)
    mgr = DatabaseManager(config=cfg)
    mgr.execute_script(SQL_SCRIPT)

    # Insert sample rows for representative inspection
    mgr.load_sample_batch("stg_clients", ["client_id", "age", "gender"], [["c1", 30, "M"]])
    mgr.load_sample_batch("stg_products", ["product_id", "level_1"], [["p1", "Cat1"]])
    mgr.load_sample_batch(
        "stg_purchases",
        ["source_row_number", "client_id", "transaction_id", "product_id"],
        [[1, "c1", "t1", "p1"], [2, "c1", "t2", "p2"]],
    )
    mgr.load_sample_batch("stg_uplift_train", ["client_id", "treatment_flg", "target"], [["c1", 1, 0]])
    mgr.load_sample_batch("stg_uplift_test", ["client_id"], [["c2"]])
    return mgr


def test_staging_cli_help():
    """Verify that staging CLI help runs without error."""
    script_path = Path(__file__).resolve().parent.parent / "src" / "custoloom" / "staging.py"
    res = subprocess.run([sys.executable, str(script_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "--sample-size" in res.stdout
    assert "--raw-dir" in res.stdout


def test_inspect_representative_records_structure(isolated_staging_manager):
    """Verify representative records inspection returns valid dict structure on isolated database."""
    reps = inspect_representative_records(isolated_staging_manager)
    for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train", "stg_uplift_test"):
        assert tbl in reps
        assert isinstance(reps[tbl], dict)
        assert len(reps[tbl]) > 0


def test_existing_purchase_source_row_numbers_bounded(isolated_staging_manager):
    """Verify get_existing_purchase_source_row_numbers retrieves expected row numbers safely."""
    # Bounded candidate lookup
    existing = get_existing_purchase_source_row_numbers(isolated_staging_manager, candidate_row_numbers=[1, 999])
    assert existing == {1}

    # Empty candidate list returns empty set safely
    assert get_existing_purchase_source_row_numbers(isolated_staging_manager, candidate_row_numbers=[]) == set()

    # Small table allows unconstrained lookup
    all_rows = get_existing_purchase_source_row_numbers(isolated_staging_manager, candidate_row_numbers=None)
    assert all_rows == {1, 2}


def test_unsafe_purchase_queries_raise_without_writes(monkeypatch, isolated_staging_manager):
    """Verify unsafe unconstrained queries raise RuntimeError on large tables and cause no writes."""
    # Simulate stg_purchases having 45 million rows
    monkeypatch.setattr(isolated_staging_manager, "fetch_row_count", lambda tbl: 45_788_000)

    # Calling unconstrained source_row_numbers raises RuntimeError
    with pytest.raises(RuntimeError, match="Unsafe unconstrained query refused"):
        get_existing_purchase_source_row_numbers(isolated_staging_manager, candidate_row_numbers=None)

    # With bounded candidate inputs, queries succeed cleanly
    assert get_existing_purchase_source_row_numbers(isolated_staging_manager, candidate_row_numbers=[1]) == {1}



def test_sample_preserves_duplicate_natural_keys(tmp_path):
    """Verify that multiple lines with identical (transaction_id, product_id) are preserved."""
    db_file = tmp_path / "dup_keys_test.duckdb"
    cfg = DatabaseConfig(db_path=db_file)
    mgr = DatabaseManager(config=cfg)
    mgr.execute_script(SQL_SCRIPT)

    # Insert two lines with identical transaction_id and product_id but distinct source_row_number
    mgr.load_sample_batch(
        "stg_purchases",
        ["source_row_number", "client_id", "transaction_id", "product_id"],
        [[1, "c1", "t1", "p1"], [2, "c1", "t1", "p1"]],
    )
    assert mgr.fetch_row_count("stg_purchases") == 2

    # Query source_row_numbers
    existing = get_existing_purchase_source_row_numbers(mgr, candidate_row_numbers=[1, 2, 3])
    assert existing == {1, 2}


def test_sample_rerun_idempotency_no_duplicates(tmp_path):
    """Verify that running sample loader twice on synthetic files does not duplicate records."""
    import gzip

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    # Create synthetic raw files
    (raw_dir / "clients.csv").write_text("client_id,first_issue_date,first_redeem_date,age,gender\nc1,2018-01-01 10:00:00,,30,M\n", encoding="utf-8")
    (raw_dir / "products.csv").write_text("product_id,level_1,level_2,level_3,level_4,segment_id,brand_id,vendor_id,netto,is_own_trademark,is_alcohol\np1,Cat1,Sub1,L3,L4,1.0,B1,V1,100,0,0\n", encoding="utf-8")

    (raw_dir / "uplift_train.csv").write_text("client_id,treatment_flg,target\nc1,1,0\n", encoding="utf-8")
    (raw_dir / "uplift_test.csv").write_text("client_id\nc2\n", encoding="utf-8")

    # Create synthetic gzip purchases with 2 lines sharing (t1, p1)
    purchases_content = (
        "client_id,transaction_id,transaction_datetime,regular_points_received,express_points_received,"
        "regular_points_spent,express_points_spent,purchase_sum,store_id,product_id,product_quantity,"
        "trn_sum_from_iss,trn_sum_from_red\n"
        "c1,t1,2019-01-01 10:00:00,10.0,0.0,0.0,0.0,200.0,s1,p1,1.0,100.0,\n"
        "c1,t1,2019-01-01 10:00:00,10.0,0.0,0.0,0.0,200.0,s1,p1,1.0,100.0,\n"
    )
    with gzip.open(raw_dir / "purchases.csv.gz", "wt", encoding="utf-8") as f:
        f.write(purchases_content)

    db_file = tmp_path / "idempotent_test.duckdb"
    mgr = DatabaseManager(config=DatabaseConfig(db_path=db_file))
    mgr.execute_script(SQL_SCRIPT)

    # First load
    res1 = load_staging_samples(mgr, raw_data_dir=raw_dir, sample_size=10)
    assert res1["stg_purchases"]["requested"] == 2
    assert res1["stg_purchases"]["inserted"] == 2
    assert mgr.fetch_row_count("stg_purchases") == 2

    # Second load (rerun): should detect existing source_row_numbers 1 and 2, inserting 0 rows
    res2 = load_staging_samples(mgr, raw_data_dir=raw_dir, sample_size=10)
    assert res2["stg_purchases"]["requested"] == 2
    assert res2["stg_purchases"]["inserted"] == 0
    assert mgr.fetch_row_count("stg_purchases") == 2  # Untouched total count


def test_staging_cli_missing_raw_dir_fails_cleanly(tmp_path):
    """Verify that staging CLI fails with clear error and zero writes when raw directory is missing."""
    script_path = Path(__file__).resolve().parent.parent / "src" / "custoloom" / "staging.py"
    non_existent = tmp_path / "non_existent_raw_dir"

    # Pass nonexistent path explicitly
    res = subprocess.run(
        [sys.executable, str(script_path), "--raw-dir", str(non_existent)],
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "Raw data directory not found" in res.stderr



