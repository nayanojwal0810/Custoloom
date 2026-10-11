"""Tests for staging module CLI and utilities."""

import subprocess
import sys
from pathlib import Path
import pytest

from custoloom.config import DatabaseConfig
from custoloom.db import DatabaseManager
from custoloom.staging import get_existing_purchase_keys, inspect_representative_records


def test_staging_cli_help():
    """Verify that staging CLI help runs without error."""
    script_path = Path(__file__).resolve().parent.parent / "src" / "custoloom" / "staging.py"
    res = subprocess.run([sys.executable, str(script_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "--sample-size" in res.stdout
    assert "--raw-dir" in res.stdout


def test_inspect_representative_records_structure():
    """Verify representative records inspection returns valid dict structure."""
    manager = DatabaseManager()
    reps = inspect_representative_records(manager)
    for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train"):
        assert tbl in reps
        assert isinstance(reps[tbl], dict)
        assert len(reps[tbl]) > 0


def test_existing_purchase_keys_query():
    """Verify purchase keys helper returns set of (transaction_id, product_id) tuples."""
    manager = DatabaseManager()
    keys = get_existing_purchase_keys(manager)
    assert isinstance(keys, set)
    assert len(keys) == 100
    sample_key = next(iter(keys))
    assert isinstance(sample_key, tuple)
    assert len(sample_key) == 2
