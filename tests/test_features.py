"""Tests for Customer 360 Feature Mart generation, basket grain, and safety in DuckDB."""

import subprocess
import sys
from pathlib import Path
import duckdb
import pytest

from custoloom.config import DatabaseConfig
from custoloom.db import DatabaseManager
from custoloom.features import (
    FEATURE_CUTOFF_TIMESTAMP,
    LOAD_MART_TABLE,
    FINAL_MART_TABLE,
    build_feature_mart_stage,
    validate_feature_mart,
    promote_feature_mart,
    run_customer_360_pipeline,
)

SQL_SCRIPT = Path(__file__).resolve().parent.parent / "sql" / "001_create_staging_tables.sql"


@pytest.fixture
def feature_test_db(tmp_path):
    """Create an isolated DuckDB instance with staging tables and synthetic test data."""
    db_file = tmp_path / "feature_test.duckdb"
    con = duckdb.connect(str(db_file))

    # Initialize staging tables schema
    con.execute(SQL_SCRIPT.read_text(encoding="utf-8"))

    # Populate 3 clients:
    # c1: active multi-basket customer
    # c2: customer with 1 multi-item basket
    # c3: customer with ZERO purchases
    con.execute("""
        INSERT INTO stg_clients VALUES 
            ('c1', '2018-01-01 10:00:00'::TIMESTAMP, '2018-05-01 12:00:00'::TIMESTAMP, 35, 'F', CURRENT_TIMESTAMP),
            ('c2', '2018-06-01 10:00:00'::TIMESTAMP, NULL, 65, 'M', CURRENT_TIMESTAMP),
            ('c3', '2018-09-01 10:00:00'::TIMESTAMP, NULL, 28, 'U', CURRENT_TIMESTAMP);
    """)

    # Populate products
    con.execute("""
        INSERT INTO stg_products VALUES 
            ('p1', 'CatA', 'Sub1', 'L3', 'L4', 1.0, 'B1', 'V1', 100.0, 0, 0, CURRENT_TIMESTAMP),
            ('p2', 'CatB', 'Sub2', 'L3', 'L4', 2.0, 'B2', 'V2', 200.0, 1, 0, CURRENT_TIMESTAMP),
            ('p_alc', 'CatA', 'Sub3', 'L3', 'L4', 3.0, 'B3', 'V3', 500.0, 0, 1, CURRENT_TIMESTAMP);
    """)

    # Populate purchases:
    # c1:
    #   Basket t1: 2019-03-01 (within 30d of 2019-03-19). Store s1. sum=100. lines=2 (p1, p2).
    #   Basket t2: 2019-01-20 (within 60d). Store s1. sum=200. lines=1 (p_alc).
    #   Basket t3: 2018-12-25 (within 90d). Store s2. sum=150. lines=1 (p1).
    # c2:
    #   Basket t4: 2018-12-01 (outside 90d). Store s1. sum=500. lines=3 (p1, p2, p_unknown).
    #   Notice: purchase_sum is 500 on all 3 lines of basket t4.
    con.execute("""
        INSERT INTO stg_purchases VALUES
            (1, 'c1', 't1', '2019-03-01 14:00:00'::TIMESTAMP, 5.0, 0.0, 0.0, 0.0, 100.0, 's1', 'p1', 1.0, 50.0, NULL, CURRENT_TIMESTAMP),
            (2, 'c1', 't1', '2019-03-01 14:00:00'::TIMESTAMP, 5.0, 0.0, 0.0, 0.0, 100.0, 's1', 'p2', 1.0, 50.0, NULL, CURRENT_TIMESTAMP),
            (3, 'c1', 't2', '2019-01-20 16:00:00'::TIMESTAMP, 10.0, 0.0, 0.0, 0.0, 200.0, 's1', 'p_alc', 2.0, 200.0, NULL, CURRENT_TIMESTAMP),
            (4, 'c1', 't3', '2018-12-25 11:00:00'::TIMESTAMP, 0.0, 0.0, 5.0, 0.0, 150.0, 's2', 'p1', 1.0, 150.0, NULL, CURRENT_TIMESTAMP),
            (5, 'c2', 't4', '2018-12-01 10:00:00'::TIMESTAMP, 25.0, 0.0, 0.0, 0.0, 500.0, 's1', 'p1', 1.0, 150.0, NULL, CURRENT_TIMESTAMP),
            (6, 'c2', 't4', '2018-12-01 10:00:00'::TIMESTAMP, 25.0, 0.0, 0.0, 0.0, 500.0, 's1', 'p2', 1.0, 150.0, NULL, CURRENT_TIMESTAMP),
            (7, 'c2', 't4', '2018-12-01 10:00:00'::TIMESTAMP, 25.0, 0.0, 0.0, 0.0, 500.0, 's1', 'p_unknown', 2.0, 200.0, NULL, CURRENT_TIMESTAMP);
    """)

    cfg = DatabaseConfig(db_path=db_file)
    mgr = DatabaseManager(config=cfg)
    yield mgr, con
    con.close()


def test_repeated_basket_monetary_aggregation(feature_test_db):
    """Verify purchase_sum is NOT multiplied by line count within a basket."""
    _, con = feature_test_db
    build_feature_mart_stage(con, target_table=LOAD_MART_TABLE)

    # c2 had 1 basket (t4) with 3 lines, purchase_sum = 500.0 on each line.
    row = con.execute(f"SELECT total_baskets, total_spend, avg_basket_value, total_purchase_lines FROM {LOAD_MART_TABLE} WHERE client_id = 'c2';").fetchone()
    assert row[0] == 1  # 1 basket
    assert row[1] == 500.0  # exactly 500.0, NOT 1500.0!
    assert row[2] == 500.0
    assert row[3] == 3  # 3 lines


def test_zero_purchase_customer_preservation(feature_test_db):
    """Verify customers with no purchase history appear in the mart with clean zero values."""
    _, con = feature_test_db
    build_feature_mart_stage(con, target_table=LOAD_MART_TABLE)

    row = con.execute(f"""
        SELECT 
            client_id, raw_age, gender, total_baskets, total_spend, 
            total_purchase_lines, days_since_last_purchase, has_redeemed
        FROM {LOAD_MART_TABLE} 
        WHERE client_id = 'c3';
    """).fetchone()

    assert row[0] == "c3"
    assert row[1] == 28
    assert row[2] == "U"
    assert row[3] == 0  # 0 baskets
    assert row[4] == 0.0  # 0.0 spend
    assert row[5] == 0  # 0 lines
    assert row[6] is None  # no last purchase
    assert row[7] == 0  # never redeemed


def test_rolling_window_and_cutoff_boundaries(feature_test_db):
    """Verify 30d, 60d, 90d activity features respect rolling window thresholds."""
    _, con = feature_test_db
    build_feature_mart_stage(con, target_table=LOAD_MART_TABLE)

    # c1 has baskets on 2019-03-01 (30d), 2019-01-20 (60d), 2018-12-25 (90d).
    row = con.execute(f"""
        SELECT 
            baskets_last_30d, spend_last_30d,
            baskets_last_60d, spend_last_60d,
            baskets_last_90d, spend_last_90d,
            total_baskets, total_spend
        FROM {LOAD_MART_TABLE} 
        WHERE client_id = 'c1';
    """).fetchone()

    assert row[0] == 1  # 1 basket in 30d
    assert row[1] == 100.0
    assert row[2] == 2  # 2 baskets in 60d
    assert row[3] == 300.0  # 100 + 200
    assert row[4] == 3  # 3 baskets in 90d
    assert row[5] == 450.0  # 100 + 200 + 150
    assert row[6] == 3  # total baskets
    assert row[7] == 450.0


def test_deterministic_preference_selection(feature_test_db):
    """Verify categorical preferences select the most frequent item with deterministic tie-breaking."""
    _, con = feature_test_db
    build_feature_mart_stage(con, target_table=LOAD_MART_TABLE)

    # c1 has:
    # 2 lines in CatA (p1, p_alc)
    # 1 line in CatB (p2)
    # Most frequent store: s1 (2 baskets: t1, t2), s2 (1 basket: t3)
    row = con.execute(f"""
        SELECT 
            favorite_level_1_category, favorite_level_1_line_share,
            favorite_store_id, favorite_store_basket_share
        FROM {LOAD_MART_TABLE} 
        WHERE client_id = 'c1';
    """).fetchone()

    assert row[0] == "CatA"
    assert row[1] == pytest.approx(3 / 4, rel=1e-3)  # 3 out of 4 lines
    assert row[2] == "s1"
    assert row[3] == pytest.approx(2 / 3, rel=1e-3)  # 2 out of 3 baskets


def test_label_leakage_absence(feature_test_db):
    """Verify target and treatment_flg are strictly absent from the mart."""
    _, con = feature_test_db
    build_feature_mart_stage(con, target_table=LOAD_MART_TABLE)

    cols = [desc[0] for desc in con.execute(f"SELECT * FROM {LOAD_MART_TABLE} LIMIT 0;").description]
    assert "target" not in cols
    assert "treatment_flg" not in cols
    assert "client_id" in cols


def test_safe_mart_promotion_and_repeatability(feature_test_db):
    """Verify atomic promotion and deterministic repeat execution."""
    mgr, con = feature_test_db

    # Build and promote
    res = run_customer_360_pipeline(mgr, expected_client_count=3)
    assert res["status"] == "SUCCESS"
    assert res["final_mart_count"] == 3

    # Verify promoted mart exists and is queryable
    cnt = con.execute(f"SELECT COUNT(*) FROM {FINAL_MART_TABLE};").fetchone()[0]
    assert cnt == 3

    # Repeat build to verify idempotency
    res_repeat = run_customer_360_pipeline(mgr, expected_client_count=3)
    assert res_repeat["status"] == "SUCCESS"
    assert res_repeat["final_mart_count"] == 3


def test_features_cli_help():
    """Verify CLI help screen runs cleanly and documents flags."""
    script_path = Path(__file__).resolve().parent.parent / "src" / "custoloom" / "features.py"
    res = subprocess.run([sys.executable, str(script_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "--build-customer-360" in res.stdout
    assert "--validate-mart" in res.stdout
    assert "--cutoff-date" in res.stdout
