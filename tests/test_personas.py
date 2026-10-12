"""Tests for customer personas classification, CRM action rules, and safety in DuckDB."""

from pathlib import Path
import duckdb
import pytest

from custoloom.config import DatabaseConfig
from custoloom.db import DatabaseManager
from custoloom.personas import (
    PersonaThresholds,
    ActionPolicy,
    PERSONA_ACTIONS,
    VALID_PRIMARY_PERSONAS,
    SOURCE_MART_TABLE,
    LOAD_PERSONAS_TABLE,
    FINAL_PERSONAS_TABLE,
    build_personas_stage,
    validate_personas_stage,
    promote_personas,
    run_customer_personas_pipeline,
    parse_args,
)


@pytest.fixture
def persona_test_db(tmp_path):
    """Create an isolated temporary DuckDB instance with synthetic mart_customer_360 data."""
    db_file = tmp_path / "persona_test.duckdb"
    cfg = DatabaseConfig(db_path=db_file)
    mgr = DatabaseManager(config=cfg)
    con = mgr.get_connection(read_only=False)

    # Create synthetic mart_customer_360 table
    con.execute(f"""
        CREATE TABLE {SOURCE_MART_TABLE} (
            client_id VARCHAR,
            total_baskets BIGINT,
            first_purchase_datetime TIMESTAMP,
            baskets_last_30d BIGINT,
            avg_basket_value DOUBLE,
            favorite_level_2_line_share DOUBLE,
            total_spend DOUBLE,
            distinct_categories_level_2 BIGINT,
            favorite_store_basket_share DOUBLE,
            has_redeemed SMALLINT,
            feature_cutoff_date TIMESTAMP
        );
    """)

    # Populate representative test customers:
    # 1. c_non_purchaser: 0 baskets (must be non_purchaser)
    # 2. c_lapsed: 5 baskets, but 0 in last 30d (must be lapsed_shopper even with high ABV)
    # 3. c_high_basket: 4 baskets in 30d, ABV=650 (high_basket_value)
    # 4. c_frequent: 10 baskets in 30d, ABV=350 (frequent_shopper)
    # 5. c_category_focused: 3 baskets in 30d, ABV=300, cat_share=0.45 (category_focused)
    # 6. c_infrequent: 1 basket in 30d, ABV=250 (infrequent_shopper)
    # 7. c_steady: 4 baskets in 30d, ABV=350, cat_share=0.25 (steady_shopper fallback)
    # 8. c_multi_flag: ABV=750, baskets_30d=12, cat_share=0.50, total_spend=20000, cats=18, single_store=0.95
    #    (qualifies for high_basket_value, frequent, AND category_focused; precedence gives high_basket_value,
    #     while ALL overlapping flags must be 1)
    # 9. c_boundary_abv_exact: ABV=600.0 exactly -> high_basket_value
    # 10. c_boundary_freq_exact: baskets_30d=8 exactly, ABV=400 -> frequent_shopper
    # 11. c_boundary_infreq_exact: baskets_30d=2 exactly, ABV=400 -> infrequent_shopper
    # 12. c_boundary_cat_exact: cat_share=0.40 exactly, baskets_30d=5, ABV=400 -> category_focused
    cutoff = "2019-03-19 00:00:00"
    con.execute(f"""
        INSERT INTO {SOURCE_MART_TABLE} VALUES
            ('c_non_purchaser', 0, NULL, 0, 0.0, NULL, 0.0, 0, NULL, 0, '{cutoff}'::TIMESTAMP),
            ('c_lapsed', 5, '2018-05-01'::TIMESTAMP, 0, 800.0, 0.50, 4000.0, 5, 1.0, 1, '{cutoff}'::TIMESTAMP),
            ('c_high_basket', 10, '2018-05-01'::TIMESTAMP, 4, 650.0, 0.20, 6500.0, 10, 0.8, 1, '{cutoff}'::TIMESTAMP),
            ('c_frequent', 20, '2018-05-01'::TIMESTAMP, 10, 350.0, 0.25, 7000.0, 12, 0.7, 1, '{cutoff}'::TIMESTAMP),
            ('c_category_focused', 6, '2018-05-01'::TIMESTAMP, 3, 300.0, 0.45, 1800.0, 4, 0.6, 0, '{cutoff}'::TIMESTAMP),
            ('c_infrequent', 3, '2018-05-01'::TIMESTAMP, 1, 250.0, 0.20, 750.0, 3, 1.0, 0, '{cutoff}'::TIMESTAMP),
            ('c_steady', 8, '2018-05-01'::TIMESTAMP, 4, 350.0, 0.25, 2800.0, 8, 0.7, 1, '{cutoff}'::TIMESTAMP),
            ('c_multi_flag', 25, '2018-05-01'::TIMESTAMP, 12, 750.0, 0.50, 20000.0, 18, 0.95, 1, '{cutoff}'::TIMESTAMP),
            ('c_boundary_abv_exact', 5, '2018-05-01'::TIMESTAMP, 3, 600.0, 0.20, 3000.0, 6, 0.5, 0, '{cutoff}'::TIMESTAMP),
            ('c_boundary_freq_exact', 15, '2018-05-01'::TIMESTAMP, 8, 400.0, 0.20, 6000.0, 8, 0.5, 0, '{cutoff}'::TIMESTAMP),
            ('c_boundary_infreq_exact', 4, '2018-05-01'::TIMESTAMP, 2, 400.0, 0.20, 1600.0, 4, 0.5, 0, '{cutoff}'::TIMESTAMP),
            ('c_boundary_cat_exact', 10, '2018-05-01'::TIMESTAMP, 5, 400.0, 0.40, 4000.0, 6, 0.5, 0, '{cutoff}'::TIMESTAMP);
    """)

    yield mgr, con
    mgr.close()


def test_no_purchase_customers_receive_non_purchaser_persona(persona_test_db):
    """Verify customers with 0 baskets are classified as non_purchaser and not active."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)

    row = con.execute(f"""
        SELECT 
            primary_persona, 
            persona_reason, 
            recommended_action, 
            flag_non_purchaser, 
            flag_active_30d
        FROM {FINAL_PERSONAS_TABLE}
        WHERE client_id = 'c_non_purchaser';
    """).fetchone()

    assert row[0] == "non_purchaser"
    assert "No recorded purchase transactions" in row[1]
    assert row[2] == "first_purchase_onboarding"
    assert row[3] == 1  # flag_non_purchaser = 1
    assert row[4] == 0  # flag_active_30d = 0 (MUST NOT be active)


def test_lapsed_shopper_with_no_recent_activity(persona_test_db):
    """Verify historical purchasers with 0 baskets in last 30d are classified as lapsed_shopper."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)

    row = con.execute(f"""
        SELECT 
            primary_persona, 
            persona_reason, 
            recommended_action, 
            flag_non_purchaser, 
            flag_active_30d,
            flag_high_basket_value
        FROM {FINAL_PERSONAS_TABLE}
        WHERE client_id = 'c_lapsed';
    """).fetchone()

    assert row[0] == "lapsed_shopper"
    assert "0 baskets in past 30 days" in row[1]
    assert row[2] == "reactivation_outreach"
    assert row[3] == 0  # flag_non_purchaser = 0 (has 5 lifetime baskets)
    assert row[4] == 0  # flag_active_30d = 0 (inactive in last 30d)
    assert row[5] == 1  # flag_high_basket_value = 1 (historical ABV was 800.0, preserved as secondary flag)


def test_null_and_zero_feature_handling(persona_test_db):
    """Verify that NULL feature shares or 0 counts on active shoppers fall back safely."""
    mgr, con = persona_test_db
    # Insert an active customer whose items had no level 2 category (cat_share is NULL)
    cutoff = "2019-03-19 00:00:00"
    con.execute(f"""
        INSERT INTO {SOURCE_MART_TABLE} VALUES
            ('c_null_cat_active', 4, '2018-05-01'::TIMESTAMP, 3, 350.0, NULL, 1400.0, 0, 0.8, 0, '{cutoff}'::TIMESTAMP);
    """)
    run_customer_personas_pipeline(manager=mgr)

    row = con.execute(f"""
        SELECT primary_persona, flag_category_concentrated, flag_active_30d
        FROM {FINAL_PERSONAS_TABLE}
        WHERE client_id = 'c_null_cat_active';
    """).fetchone()

    # Falls back to steady_shopper, NOT category_focused, and flag is 0
    assert row[0] == "steady_shopper"
    assert row[1] == 0
    assert row[2] == 1


def test_invalid_threshold_configuration_validation():
    """Verify PersonaThresholds rejects illegal negative or contradictory thresholds."""
    with pytest.raises(ValueError, match="high_basket_value_rub must be positive"):
        PersonaThresholds(high_basket_value_rub=-50.0)

    with pytest.raises(ValueError, match="infrequent cutoff .* must be less than frequent cutoff"):
        PersonaThresholds(frequent_shopper_baskets_30d=5, infrequent_shopper_max_baskets_30d=8)

    with pytest.raises(ValueError, match="category_concentration_share must be in"):
        PersonaThresholds(category_concentration_share=1.5)

    with pytest.raises(ValueError, match="rule_version cannot be empty"):
        PersonaThresholds(rule_version="")


def test_representative_examples_for_all_personas(persona_test_db):
    """Verify that every defined persona and the fallback are correctly assigned to representative cases."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)

    expected = {
        "c_non_purchaser": "non_purchaser",
        "c_lapsed": "lapsed_shopper",
        "c_high_basket": "high_basket_value",
        "c_frequent": "frequent_shopper",
        "c_category_focused": "category_focused",
        "c_infrequent": "infrequent_shopper",
        "c_steady": "steady_shopper",
        "c_boundary_abv_exact": "high_basket_value",
        "c_boundary_freq_exact": "frequent_shopper",
        "c_boundary_infreq_exact": "infrequent_shopper",
        "c_boundary_cat_exact": "category_focused",
    }

    for client_id, expected_persona in expected.items():
        res = con.execute(
            f"SELECT primary_persona FROM {FINAL_PERSONAS_TABLE} WHERE client_id = ?;", [client_id]
        ).fetchone()
        assert res is not None, f"Client {client_id} missing from persona table"
        assert res[0] == expected_persona, f"Client {client_id}: expected {expected_persona}, got {res[0]}"


def test_exactly_one_primary_persona_per_customer(persona_test_db):
    """Verify every customer has exactly 1 row and 1 non-null primary persona."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)

    total_rows = con.execute(f"SELECT COUNT(*) FROM {FINAL_PERSONAS_TABLE};").fetchone()[0]
    distinct_clients = con.execute(f"SELECT COUNT(DISTINCT client_id) FROM {FINAL_PERSONAS_TABLE};").fetchone()[0]
    null_personas = con.execute(f"SELECT COUNT(*) FROM {FINAL_PERSONAS_TABLE} WHERE primary_persona IS NULL;").fetchone()[0]

    assert total_rows == 12
    assert distinct_clients == 12
    assert null_personas == 0


def test_deterministic_precedence_when_multiple_rules_match(persona_test_db):
    """Verify strict precedence: high_basket_value > frequent_shopper > category_focused."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)

    # c_multi_flag qualifies for high_basket_value (ABV=750), frequent (baskets=12), and category_focused (cat=0.50).
    # Precedence rule specifies high_basket_value takes precedence over frequent_shopper.
    row = con.execute(f"""
        SELECT primary_persona, flag_high_basket_value, flag_frequent_shopper, flag_category_concentrated
        FROM {FINAL_PERSONAS_TABLE}
        WHERE client_id = 'c_multi_flag';
    """).fetchone()

    assert row[0] == "high_basket_value"
    # All secondary conditions are preserved as overlapping flags
    assert row[1] == 1  # flag_high_basket_value
    assert row[2] == 1  # flag_frequent_shopper
    assert row[3] == 1  # flag_category_concentrated


def test_intentional_overlap_among_behavioral_flags(persona_test_db):
    """Verify that multiple behavioral flags can be 1 simultaneously on the same customer."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)

    flags = con.execute(f"""
        SELECT 
            flag_active_30d,
            flag_high_basket_value,
            flag_frequent_shopper,
            flag_high_historical_spend,
            flag_category_concentrated,
            flag_broad_category_range,
            flag_single_store_shopper,
            flag_points_redeemer
        FROM {FINAL_PERSONAS_TABLE}
        WHERE client_id = 'c_multi_flag';
    """).fetchone()

    # In c_multi_flag, all of these flags were designed to be 1
    assert all(f == 1 for f in flags), f"Expected all flags to be 1, got {flags}"


def test_threshold_boundaries_equality_and_ties(persona_test_db):
    """Verify exact equality on boundary values triggers the intended persona."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)

    # ABV == 600.0 triggers high_basket_value
    p_abv = con.execute(f"SELECT primary_persona FROM {FINAL_PERSONAS_TABLE} WHERE client_id = 'c_boundary_abv_exact';").fetchone()[0]
    assert p_abv == "high_basket_value"

    # baskets_last_30d == 8 triggers frequent_shopper
    p_freq = con.execute(f"SELECT primary_persona FROM {FINAL_PERSONAS_TABLE} WHERE client_id = 'c_boundary_freq_exact';").fetchone()[0]
    assert p_freq == "frequent_shopper"

    # baskets_last_30d == 2 triggers infrequent_shopper
    p_infreq = con.execute(f"SELECT primary_persona FROM {FINAL_PERSONAS_TABLE} WHERE client_id = 'c_boundary_infreq_exact';").fetchone()[0]
    assert p_infreq == "infrequent_shopper"

    # cat_share == 0.40 triggers category_focused
    p_cat = con.execute(f"SELECT primary_persona FROM {FINAL_PERSONAS_TABLE} WHERE client_id = 'c_boundary_cat_exact';").fetchone()[0]
    assert p_cat == "category_focused"


def test_every_persona_maps_to_valid_action_and_rationale(persona_test_db):
    """Verify every customer is mapped to an action in PERSONA_ACTIONS with non-empty rationale."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)

    rows = con.execute(f"""
        SELECT DISTINCT primary_persona, recommended_action, action_rationale, action_qualification
        FROM {FINAL_PERSONAS_TABLE};
    """).fetchall()

    for p, act, rat, qual in rows:
        assert p in PERSONA_ACTIONS, f"Unknown persona '{p}'"
        expected_policy = PERSONA_ACTIONS[p]
        assert act == expected_policy.action, f"Action mismatch for persona '{p}'"
        assert rat == expected_policy.rationale, f"Rationale mismatch for persona '{p}'"
        assert qual == expected_policy.qualification, f"Qualification mismatch for persona '{p}'"


def test_missing_source_mart_fails_cleanly(tmp_path):
    """Verify running persona pipeline on a database without mart_customer_360 raises RuntimeError."""
    empty_db = tmp_path / "empty.duckdb"
    mgr = DatabaseManager(config=DatabaseConfig(db_path=empty_db))

    with pytest.raises(RuntimeError, match="required source table 'mart_customer_360' does not exist"):
        run_customer_personas_pipeline(manager=mgr)


def test_persona_pipeline_repeatability_and_idempotency(persona_test_db):
    """Verify running the persona pipeline twice produces identical rows and classifications."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)
    run_1_rows = con.execute(f"SELECT client_id, primary_persona, recommended_action FROM {FINAL_PERSONAS_TABLE} ORDER BY client_id;").fetchall()

    # Run second time
    run_customer_personas_pipeline(manager=mgr)
    run_2_rows = con.execute(f"SELECT client_id, primary_persona, recommended_action FROM {FINAL_PERSONAS_TABLE} ORDER BY client_id;").fetchall()

    assert run_1_rows == run_2_rows


def test_customer_id_preservation_and_one_row_per_customer(persona_test_db):
    """Verify all client_ids from source mart exist in persona table with no extras or omissions."""
    mgr, con = persona_test_db
    run_customer_personas_pipeline(manager=mgr)

    src_ids = [r[0] for r in con.execute(f"SELECT client_id FROM {SOURCE_MART_TABLE} ORDER BY client_id;").fetchall()]
    tgt_ids = [r[0] for r in con.execute(f"SELECT client_id FROM {FINAL_PERSONAS_TABLE} ORDER BY client_id;").fetchall()]

    assert src_ids == tgt_ids


def test_failed_promotion_preserves_existing_destination_table(persona_test_db):
    """Verify that promotion failure preserves the existing destination table without loss."""
    mgr, con = persona_test_db
    # 1. Establish existing destination table
    run_customer_personas_pipeline(manager=mgr)
    baseline_rows = con.execute(f"SELECT client_id, primary_persona FROM {FINAL_PERSONAS_TABLE} ORDER BY client_id;").fetchall()
    assert len(baseline_rows) > 0

    # 2. Attempt promotion with missing staging table -> raises RuntimeError, table preserved
    with pytest.raises(RuntimeError, match="required staging table 'nonexistent_stage' does not exist"):
        promote_personas(con, load_table="nonexistent_stage", final_table=FINAL_PERSONAS_TABLE)

    after_missing_rows = con.execute(f"SELECT client_id, primary_persona FROM {FINAL_PERSONAS_TABLE} ORDER BY client_id;").fetchall()
    assert after_missing_rows == baseline_rows

    # 3. Simulate failure during transaction:
    # Verify that inside BEGIN TRANSACTION, a rollback restores the dropped final_table
    con.execute("BEGIN TRANSACTION;")
    con.execute(f"DROP TABLE IF EXISTS {FINAL_PERSONAS_TABLE};")
    try:
        con.execute(f"ALTER TABLE nonexistent_table_for_rollback RENAME TO {FINAL_PERSONAS_TABLE};")
        con.execute("COMMIT;")
    except Exception:
        con.execute("ROLLBACK;")

    # Destination table must be fully restored by ROLLBACK
    after_rollback_rows = con.execute(f"SELECT client_id, primary_persona FROM {FINAL_PERSONAS_TABLE} ORDER BY client_id;").fetchall()
    assert after_rollback_rows == baseline_rows


def test_prevent_source_mart_as_target_collision(persona_test_db):
    """Verify attempts to use mart_customer_360 or protected tables as target fail before writes."""
    mgr, con = persona_test_db

    # Attempt to target mart_customer_360
    with pytest.raises(ValueError, match="target_table cannot be protected table 'mart_customer_360'"):
        run_customer_personas_pipeline(manager=mgr, target_table="mart_customer_360")

    # Attempt to target stg_purchases
    with pytest.raises(ValueError, match="target_table cannot be protected table 'stg_purchases'"):
        run_customer_personas_pipeline(manager=mgr, target_table="stg_purchases")

    # Source mart remains unchanged
    count = con.execute("SELECT COUNT(*) FROM mart_customer_360;").fetchone()[0]
    assert count == 12


def test_prevent_source_staging_destination_name_collisions(persona_test_db):
    """Verify collisions among source, staging, and destination table names are rejected."""
    mgr, con = persona_test_db

    # source == target
    with pytest.raises(ValueError, match="source_table and target_table cannot both be"):
        run_customer_personas_pipeline(
            manager=mgr, source_table="custom_mart", target_table="custom_mart"
        )

    # staging == target
    with pytest.raises(ValueError, match="target_table and staging_table cannot both be"):
        run_customer_personas_pipeline(
            manager=mgr, staging_table="mart_customer_personas", target_table="mart_customer_personas"
        )

    # source == staging
    with pytest.raises(ValueError, match="source_table and staging_table cannot both be"):
        run_customer_personas_pipeline(
            manager=mgr, source_table="custom_mart", staging_table="custom_mart"
        )


def test_personas_cli_help():
    """Verify personas CLI argument parser works without errors."""
    parsed = parse_args(["--source-table", "custom_mart", "--target-table", "custom_personas"])
    assert parsed.source_table == "custom_mart"
    assert parsed.target_table == "custom_personas"


def test_personas_persistent_database_integration(pytestconfig):
    """Opt-in integration test verifying persona construction against persistent database."""
    if not pytestconfig.getoption("--run-integration"):
        pytest.skip("Integration test requires --run-integration flag")

    db_path = Path("data/processed/custoloom.duckdb")
    if not db_path.exists():
        pytest.skip(f"Persistent database '{db_path}' not found")

    mgr = DatabaseManager(config=DatabaseConfig(db_path=db_path))
    # Run pipeline on persistent database
    summary = run_customer_personas_pipeline(manager=mgr)

    assert summary["total_customers"] == 400162
    assert sum(summary["persona_counts"].values()) == 400162

    # Verify mart_customer_360 remains completely intact
    with mgr.get_connection(read_only=True) as conn:
        src_count = conn.execute("SELECT COUNT(*) FROM mart_customer_360;").fetchone()[0]
        assert src_count == 400162
        cols = len(conn.execute("PRAGMA table_info(mart_customer_360);").fetchall())
        assert cols == 53
        spend_sum = conn.execute("SELECT ROUND(SUM(total_spend), 2) FROM mart_customer_360;").fetchone()[0]
        assert abs(spend_sum - 3444393840.48) < 0.01

    mgr.close()
