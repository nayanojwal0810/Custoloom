"""Tests for full dataset ingestion CLI, source validation, and schema safety in DuckDB."""

import subprocess
import sys
from pathlib import Path
import pytest

from custoloom.config import DatabaseConfig
from custoloom.db import DatabaseManager
from custoloom.ingest import (
    EXPECTED_HEADERS,
    validate_source_headers,
)

RAW_DATA_DIR = Path("D:/DA projects/optispend-engine/data/raw")


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


def test_validate_source_headers_passes():
    """Verify validate_source_headers successfully validates all raw files."""
    headers = validate_source_headers(RAW_DATA_DIR)
    assert len(headers) == 5
    assert "clients.csv" in headers


def test_validate_source_headers_fails_on_missing_dir(tmp_path):
    """Verify validate_source_headers raises FileNotFoundError when dir has missing files."""
    with pytest.raises(FileNotFoundError):
        validate_source_headers(tmp_path)


def test_ingest_cli_help():
    """Verify that the ingestion CLI help screen runs cleanly."""
    script_path = Path(__file__).resolve().parent.parent / "src" / "custoloom" / "ingest.py"
    res = subprocess.run([sys.executable, str(script_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "--audit-only" in res.stdout
    assert "--sample-size" in res.stdout
    assert "--full-ingest" in res.stdout


def test_ingest_full_load_is_safely_deferred():
    """Verify that calling --full-ingest does not inadvertently trigger 45M row load."""
    script_path = Path(__file__).resolve().parent.parent / "src" / "custoloom" / "ingest.py"
    res = subprocess.run(
        [sys.executable, str(script_path), "--full-ingest"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "FULL INGESTION DEFERRED" in res.stderr or "FULL INGESTION DEFERRED" in res.stdout


def test_staging_tables_schema_duckdb():
    """Verify DuckDB staging tables schema defines columns for all 5 datasets."""
    manager = DatabaseManager()
    for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train", "stg_uplift_test"):
        assert manager.inspect_table_exists(tbl)
        cols = manager.inspect_table_columns(tbl)
        assert len(cols) > 0
