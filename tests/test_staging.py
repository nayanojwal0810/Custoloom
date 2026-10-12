"""Tests for staging module CLI and utilities."""

import subprocess
import sys
from pathlib import Path
import pytest

from custoloom.config import DatabaseConfig
from custoloom.db import DatabaseManager
from custoloom.staging import get_existing_purchase_keys, inspect_representative_records

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


def test_existing_purchase_keys_query(isolated_staging_manager):
    """Verify purchase keys helper returns set of (transaction_id, product_id) tuples."""
    keys = get_existing_purchase_keys(isolated_staging_manager)
    assert isinstance(keys, set)
    assert len(keys) == 2
    assert ("t1", "p1") in keys
    assert ("t2", "p2") in keys


def test_candidate_bounded_purchase_keys_query(isolated_staging_manager):
    """Verify candidate_keys filters existing pairs without scanning irrelevant keys."""
    candidates = [("t1", "p1"), ("nonexistent_t", "nonexistent_p")]
    matched = get_existing_purchase_keys(isolated_staging_manager, candidate_keys=candidates)
    assert matched == {("t1", "p1")}
    assert ("t2", "p2") not in matched

    # Empty candidates returns empty set safely
    empty_matched = get_existing_purchase_keys(isolated_staging_manager, candidate_keys=[])
    assert empty_matched == set()


def test_unbounded_safety_threshold_purchase_keys(monkeypatch, isolated_staging_manager):
    """Verify full table scan is avoided if table size exceeds safe memory threshold."""
    # Simulate stg_purchases having 45 million rows
    monkeypatch.setattr(isolated_staging_manager, "fetch_row_count", lambda tbl: 45_788_000)
    
    # Without candidate_keys, it should safely return empty set and not scan
    keys = get_existing_purchase_keys(isolated_staging_manager, candidate_keys=None)
    assert keys == set()

    # With candidate_keys, it should execute the bounded query despite high total table count
    candidates = [("t1", "p1")]
    keys_bounded = get_existing_purchase_keys(isolated_staging_manager, candidate_keys=candidates)
    assert keys_bounded == {("t1", "p1")}

