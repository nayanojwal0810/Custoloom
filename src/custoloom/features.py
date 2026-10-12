"""Customer 360 Feature Mart generation and validation for Custoloom.

Transforms raw staging data in DuckDB into an interpretable, SQL-native
analytical feature mart (mart_customer_360) with customer profile, recency,
frequency, monetary, product category, and store shopping dynamics.
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional
import duckdb

# Bootstrap package root for direct script execution
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from custoloom.config import DatabaseConfig, DatabaseConnectionError
from custoloom.db import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("custoloom.features")

# Historical observation cutoff date (end of observed purchase period)
FEATURE_CUTOFF_TIMESTAMP = "2019-03-19 00:00:00"

# Rolling window day intervals
WINDOW_30D_CUTOFF = "2019-02-17 00:00:00"
WINDOW_60D_CUTOFF = "2019-01-18 00:00:00"
WINDOW_90D_CUTOFF = "2018-12-19 00:00:00"

LOAD_MART_TABLE = "load_mart_customer_360"
FINAL_MART_TABLE = "mart_customer_360"


def clean_stale_feature_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Clean up any stale load-stage feature tables from interrupted runs."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name = ?;",
        [LOAD_MART_TABLE],
    ).fetchall()
    if rows:
        logger.warning("Found stale feature table '%s'. Dropping before build...", LOAD_MART_TABLE)
        con.execute(f"DROP TABLE IF EXISTS {LOAD_MART_TABLE};")


def build_feature_mart_stage(
    con: duckdb.DuckDBPyConnection,
    cutoff_dt: str = FEATURE_CUTOFF_TIMESTAMP,
    target_table: str = LOAD_MART_TABLE,
    staging_prefix: str = "stg_",
) -> dict[str, float]:
    """Execute SQL-native transformations to materialize the Customer 360 feature mart.

    Maintains strict aggregation grain:
    1. Baskets are aggregated to (client_id, transaction_id) to avoid multiplying
       repeated transaction-level purchase_sum across lines.
    2. Customer-level aggregates join to stg_clients via LEFT JOIN to preserve all
       customers, including those with zero purchases.
    3. Treatment flag and target are strictly excluded to avoid causal data leakage.
    """
    logger.info("Starting Customer 360 feature mart construction into '%s'...", target_table)
    timings: dict[str, float] = {}
    t_start = time.time()

    tbl_clients = f"{staging_prefix}clients"
    tbl_purchases = f"{staging_prefix}purchases"
    tbl_products = f"{staging_prefix}products"

    # Step 1: Basket-level summary
    # Basket grain: (client_id, transaction_id).
    # purchase_sum and loyalty points are constant within basket and aggregated once.
    t0 = time.time()
    con.execute(f"""
        CREATE TEMP TABLE tmp_baskets AS
        SELECT 
            client_id,
            transaction_id,
            MAX(transaction_datetime) AS transaction_datetime,
            MAX(store_id) AS store_id,
            MAX(purchase_sum) AS purchase_sum,
            MAX(regular_points_received) AS regular_points_received,
            MAX(regular_points_spent) AS regular_points_spent,
            COUNT(*) AS basket_line_count,
            SUM(product_quantity) AS basket_quantity
        FROM {tbl_purchases}
        GROUP BY client_id, transaction_id;
    """)
    timings["tmp_baskets"] = round(time.time() - t0, 2)
    logger.info("1. Basket-level aggregation completed in %.2fs", timings["tmp_baskets"])

    # Step 2: Customer basket-level recency, frequency, monetary, and rolling windows
    t0 = time.time()
    con.execute(f"""
        CREATE TEMP TABLE tmp_cust_baskets AS
        SELECT 
            client_id,
            MIN(transaction_datetime) AS first_purchase_datetime,
            MAX(transaction_datetime) AS last_purchase_datetime,
            DATEDIFF('day', MAX(transaction_datetime), '{cutoff_dt}'::TIMESTAMP) AS days_since_last_purchase,
            DATEDIFF('day', MIN(transaction_datetime), '{cutoff_dt}'::TIMESTAMP) AS customer_tenure_days,
            COUNT(*) AS total_baskets,
            SUM(purchase_sum) AS total_spend,
            ROUND(AVG(purchase_sum), 2) AS avg_basket_value,
            ROUND(MEDIAN(purchase_sum), 2) AS median_basket_value,
            MIN(purchase_sum) AS min_basket_value,
            MAX(purchase_sum) AS max_basket_value,
            ROUND(AVG(basket_line_count), 2) AS avg_lines_per_basket,
            ROUND(AVG(basket_quantity), 2) AS avg_quantity_per_basket,
            ROUND(SUM(basket_quantity), 2) AS total_product_quantity,
            COUNT(DISTINCT store_id) AS distinct_stores_visited,
            ROUND(SUM(CASE WHEN dayofweek(transaction_datetime) IN (0, 6) THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS weekend_basket_share,
            ROUND(SUM(CASE WHEN hour(transaction_datetime) BETWEEN 9 AND 17 THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS daytime_basket_share,
            ROUND(SUM(CASE WHEN hour(transaction_datetime) >= 18 OR hour(transaction_datetime) < 9 THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS evening_basket_share,
            SUM(regular_points_received) AS total_regular_points_received,
            SUM(regular_points_spent) AS total_regular_points_spent,
            -- 30d window
            COUNT(CASE WHEN transaction_datetime >= '{WINDOW_30D_CUTOFF}'::TIMESTAMP THEN 1 END) AS baskets_last_30d,
            COALESCE(SUM(CASE WHEN transaction_datetime >= '{WINDOW_30D_CUTOFF}'::TIMESTAMP THEN purchase_sum END), 0.0) AS spend_last_30d,
            COALESCE(SUM(CASE WHEN transaction_datetime >= '{WINDOW_30D_CUTOFF}'::TIMESTAMP THEN basket_line_count END), 0) AS lines_last_30d,
            -- 60d window
            COUNT(CASE WHEN transaction_datetime >= '{WINDOW_60D_CUTOFF}'::TIMESTAMP THEN 1 END) AS baskets_last_60d,
            COALESCE(SUM(CASE WHEN transaction_datetime >= '{WINDOW_60D_CUTOFF}'::TIMESTAMP THEN purchase_sum END), 0.0) AS spend_last_60d,
            COALESCE(SUM(CASE WHEN transaction_datetime >= '{WINDOW_60D_CUTOFF}'::TIMESTAMP THEN basket_line_count END), 0) AS lines_last_60d,
            -- 90d window
            COUNT(CASE WHEN transaction_datetime >= '{WINDOW_90D_CUTOFF}'::TIMESTAMP THEN 1 END) AS baskets_last_90d,
            COALESCE(SUM(CASE WHEN transaction_datetime >= '{WINDOW_90D_CUTOFF}'::TIMESTAMP THEN purchase_sum END), 0.0) AS spend_last_90d,
            COALESCE(SUM(CASE WHEN transaction_datetime >= '{WINDOW_90D_CUTOFF}'::TIMESTAMP THEN basket_line_count END), 0) AS lines_last_90d
        FROM tmp_baskets
        GROUP BY client_id;
    """)
    timings["tmp_cust_baskets"] = round(time.time() - t0, 2)
    logger.info("2. Customer basket metrics and rolling windows completed in %.2fs", timings["tmp_cust_baskets"])

    # Step 3: Favorite store per customer (deterministic tie-breaking: basket count DESC, store_id ASC)
    t0 = time.time()
    con.execute("""
        CREATE TEMP TABLE tmp_cust_stores AS
        WITH ranked_stores AS (
            SELECT 
                client_id,
                store_id,
                COUNT(*) AS store_baskets,
                ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY COUNT(*) DESC, store_id ASC) AS rnk
            FROM tmp_baskets
            GROUP BY client_id, store_id
        )
        SELECT client_id, store_id AS favorite_store_id, store_baskets AS favorite_store_baskets
        FROM ranked_stores
        WHERE rnk = 1;
    """)
    timings["tmp_cust_stores"] = round(time.time() - t0, 2)
    logger.info("3. Store shopping preferences completed in %.2fs", timings["tmp_cust_stores"])

    # Step 4: Line-level product aggregates and diversity
    t0 = time.time()
    con.execute(f"""
        CREATE TEMP TABLE tmp_cust_products AS
        SELECT 
            p.client_id,
            COUNT(*) AS total_purchase_lines,
            COUNT(DISTINCT p.product_id) AS distinct_products_purchased,
            COUNT(DISTINCT pr.level_1) AS distinct_categories_level_1,
            COUNT(DISTINCT pr.level_2) AS distinct_categories_level_2,
            ROUND(COUNT(CASE WHEN pr.is_alcohol = 1 THEN 1 END) * 1.0 / COUNT(*), 4) AS alcohol_line_share,
            ROUND(COUNT(CASE WHEN pr.is_own_trademark = 1 THEN 1 END) * 1.0 / COUNT(*), 4) AS own_trademark_line_share
        FROM {tbl_purchases} p
        LEFT JOIN {tbl_products} pr ON p.product_id = pr.product_id
        GROUP BY p.client_id;
    """)
    timings["tmp_cust_products"] = round(time.time() - t0, 2)
    logger.info("4. Product and category diversity metrics completed in %.2fs", timings["tmp_cust_products"])

    # Step 5: Favorite Level 1 Category (deterministic tie-breaking: count DESC, level_1 ASC)
    t0 = time.time()
    con.execute(f"""
        CREATE TEMP TABLE tmp_cust_cat1 AS
        WITH ranked_cats AS (
            SELECT 
                p.client_id,
                pr.level_1,
                COUNT(*) AS cat_lines,
                ROW_NUMBER() OVER (PARTITION BY p.client_id ORDER BY COUNT(*) DESC, pr.level_1 ASC) AS rnk
            FROM {tbl_purchases} p
            JOIN {tbl_products} pr ON p.product_id = pr.product_id
            WHERE pr.level_1 IS NOT NULL
            GROUP BY p.client_id, pr.level_1
        )
        SELECT client_id, level_1 AS favorite_level_1_category, cat_lines AS favorite_level_1_lines
        FROM ranked_cats
        WHERE rnk = 1;
    """)
    timings["tmp_cust_cat1"] = round(time.time() - t0, 2)
    logger.info("5. Favorite Level 1 categories completed in %.2fs", timings["tmp_cust_cat1"])

    # Step 6: Favorite Level 2 Category (department level: count DESC, level_2 ASC)
    t0 = time.time()
    con.execute(f"""
        CREATE TEMP TABLE tmp_cust_cat2 AS
        WITH ranked_cats2 AS (
            SELECT 
                p.client_id,
                pr.level_2,
                COUNT(*) AS cat_lines,
                ROW_NUMBER() OVER (PARTITION BY p.client_id ORDER BY COUNT(*) DESC, pr.level_2 ASC) AS rnk
            FROM {tbl_purchases} p
            JOIN {tbl_products} pr ON p.product_id = pr.product_id
            WHERE pr.level_2 IS NOT NULL
            GROUP BY p.client_id, pr.level_2
        )
        SELECT client_id, level_2 AS favorite_level_2_category, cat_lines AS favorite_level_2_lines
        FROM ranked_cats2
        WHERE rnk = 1;
    """)
    timings["tmp_cust_cat2"] = round(time.time() - t0, 2)
    logger.info("6. Favorite Level 2 categories completed in %.2fs", timings["tmp_cust_cat2"])

    # Step 7: Materialize final feature table
    t0 = time.time()
    con.execute(f"""
        CREATE TABLE {target_table} AS
        SELECT 
            c.client_id,
            -- Customer Profile Group
            c.age AS raw_age,
            c.gender AS gender,
            CASE WHEN c.age BETWEEN 18 AND 100 THEN 1::SMALLINT ELSE 0::SMALLINT END AS is_age_valid,
            CASE WHEN c.gender IN ('F', 'M') THEN 1::SMALLINT ELSE 0::SMALLINT END AS is_gender_known,
            c.first_issue_date,
            c.first_redeem_date,
            DATEDIFF('day', c.first_issue_date, '{cutoff_dt}'::TIMESTAMP) AS days_since_first_issue,
            CASE WHEN c.first_redeem_date IS NOT NULL 
                 THEN DATEDIFF('day', c.first_redeem_date, '{cutoff_dt}'::TIMESTAMP) 
                 ELSE NULL END AS days_since_first_redeem,
            CASE WHEN c.first_redeem_date IS NOT NULL THEN 1::SMALLINT ELSE 0::SMALLINT END AS has_redeemed,
            
            -- Purchase Recency & Frequency Group
            b.first_purchase_datetime,
            b.last_purchase_datetime,
            b.days_since_last_purchase,
            b.customer_tenure_days,
            COALESCE(b.total_baskets, 0) AS total_baskets,
            COALESCE(p.total_purchase_lines, 0) AS total_purchase_lines,
            COALESCE(p.distinct_products_purchased, 0) AS distinct_products_purchased,
            COALESCE(b.distinct_stores_visited, 0) AS distinct_stores_visited,
            COALESCE(b.avg_lines_per_basket, 0.0) AS avg_lines_per_basket,
            COALESCE(b.avg_quantity_per_basket, 0.0) AS avg_quantity_per_basket,
            COALESCE(b.total_product_quantity, 0.0) AS total_product_quantity,
            
            -- Monetary & Basket Value Group
            COALESCE(b.total_spend, 0.0) AS total_spend,
            COALESCE(b.avg_basket_value, 0.0) AS avg_basket_value,
            COALESCE(b.median_basket_value, 0.0) AS median_basket_value,
            COALESCE(b.min_basket_value, 0.0) AS min_basket_value,
            COALESCE(b.max_basket_value, 0.0) AS max_basket_value,
            COALESCE(b.total_regular_points_received, 0.0) AS total_regular_points_received,
            COALESCE(b.total_regular_points_spent, 0.0) AS total_regular_points_spent,
            
            -- Rolling Activity Windows Group
            COALESCE(b.baskets_last_30d, 0) AS baskets_last_30d,
            COALESCE(b.spend_last_30d, 0.0) AS spend_last_30d,
            COALESCE(b.lines_last_30d, 0) AS lines_last_30d,
            COALESCE(b.baskets_last_60d, 0) AS baskets_last_60d,
            COALESCE(b.spend_last_60d, 0.0) AS spend_last_60d,
            COALESCE(b.lines_last_60d, 0) AS lines_last_60d,
            COALESCE(b.baskets_last_90d, 0) AS baskets_last_90d,
            COALESCE(b.spend_last_90d, 0.0) AS spend_last_90d,
            COALESCE(b.lines_last_90d, 0) AS lines_last_90d,
            ROUND(COALESCE(b.spend_last_30d, 0.0) / NULLIF(b.spend_last_90d, 0.0), 4) AS spend_ratio_30d_vs_90d,
            
            -- Product & Category Preferences Group
            COALESCE(p.distinct_categories_level_1, 0) AS distinct_categories_level_1,
            COALESCE(p.distinct_categories_level_2, 0) AS distinct_categories_level_2,
            c1.favorite_level_1_category,
            ROUND(COALESCE(c1.favorite_level_1_lines, 0) * 1.0 / NULLIF(p.total_purchase_lines, 0), 4) AS favorite_level_1_line_share,
            c2.favorite_level_2_category,
            ROUND(COALESCE(c2.favorite_level_2_lines, 0) * 1.0 / NULLIF(p.total_purchase_lines, 0), 4) AS favorite_level_2_line_share,
            COALESCE(p.alcohol_line_share, 0.0) AS alcohol_line_share,
            COALESCE(p.own_trademark_line_share, 0.0) AS own_trademark_line_share,
            
            -- Store & Shopping Dynamics Group
            s.favorite_store_id,
            ROUND(COALESCE(s.favorite_store_baskets, 0) * 1.0 / NULLIF(b.total_baskets, 0), 4) AS favorite_store_basket_share,
            COALESCE(b.weekend_basket_share, 0.0) AS weekend_basket_share,
            COALESCE(b.daytime_basket_share, 0.0) AS daytime_basket_share,
            COALESCE(b.evening_basket_share, 0.0) AS evening_basket_share,
            
            -- Metadata Group
            '{cutoff_dt}'::TIMESTAMP AS feature_cutoff_date,
            CURRENT_TIMESTAMP AS mart_created_at
        FROM {tbl_clients} c
        LEFT JOIN tmp_cust_baskets b ON c.client_id = b.client_id
        LEFT JOIN tmp_cust_products p ON c.client_id = p.client_id
        LEFT JOIN tmp_cust_stores s ON c.client_id = s.client_id
        LEFT JOIN tmp_cust_cat1 c1 ON c.client_id = c1.client_id
        LEFT JOIN tmp_cust_cat2 c2 ON c.client_id = c2.client_id;
    """)
    timings["materialization"] = round(time.time() - t0, 2)
    timings["total"] = round(time.time() - t_start, 2)

    # Clean up temp tables
    con.execute("""
        DROP TABLE IF EXISTS tmp_baskets;
        DROP TABLE IF EXISTS tmp_cust_baskets;
        DROP TABLE IF EXISTS tmp_cust_stores;
        DROP TABLE IF EXISTS tmp_cust_products;
        DROP TABLE IF EXISTS tmp_cust_cat1;
        DROP TABLE IF EXISTS tmp_cust_cat2;
    """)

    logger.info("Materialized table '%s' in %.2fs total.", target_table, timings["total"])
    return timings


def validate_feature_mart(
    con: duckdb.DuckDBPyConnection,
    table_name: str = LOAD_MART_TABLE,
    staging_prefix: str = "stg_",
    expected_client_count: Optional[int] = None,
) -> dict[str, Any]:
    """Execute comprehensive data quality and analytical integrity checks on the feature mart."""
    logger.info("Validating Customer 360 mart table '%s'...", table_name)
    t0 = time.time()
    tbl_clients = f"{staging_prefix}clients"

    # 1. Total row counts and client coverage
    mart_count = con.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()[0]
    expected_clients = (
        expected_client_count
        if expected_client_count is not None
        else con.execute(f"SELECT COUNT(*) FROM {tbl_clients};").fetchone()[0]
    )

    if mart_count != expected_clients:
        raise ValueError(
            f"Mart row count mismatch: expected {expected_clients} clients, found {mart_count}"
        )

    # 2. Key uniqueness and null check
    key_audit = con.execute(f"""
        SELECT 
            COUNT(DISTINCT client_id) as distinct_clients,
            COUNT(CASE WHEN client_id IS NULL OR client_id = '' THEN 1 END) as null_clients
        FROM {table_name};
    """).fetchone()

    if key_audit[0] != mart_count:
        raise ValueError(f"Primary key client_id has duplicates in {table_name}: distinct={key_audit[0]}, total={mart_count}")
    if key_audit[1] != 0:
        raise ValueError(f"Found {key_audit[1]} NULL or empty client_id values in {table_name}")

    # 3. Label leakage check (strictly verify target and treatment_flg are absent)
    cols = [desc[0] for desc in con.execute(f"SELECT * FROM {table_name} LIMIT 0;").description]
    for forbidden in ["target", "treatment_flg"]:
        if forbidden in cols:
            raise ValueError(f"CAUSAL LEAKAGE DETECTED: Column '{forbidden}' is present in {table_name}!")

    # 4. Non-negative constraints and value sanity
    numeric_violations = con.execute(f"""
        SELECT 
            COUNT(CASE WHEN total_baskets < 0 THEN 1 END),
            COUNT(CASE WHEN total_spend < 0.0 THEN 1 END),
            COUNT(CASE WHEN total_purchase_lines < 0 THEN 1 END),
            COUNT(CASE WHEN distinct_products_purchased < 0 THEN 1 END),
            COUNT(CASE WHEN distinct_stores_visited < 0 THEN 1 END),
            COUNT(CASE WHEN baskets_last_30d < 0 THEN 1 END),
            COUNT(CASE WHEN spend_last_30d < 0.0 THEN 1 END),
            COUNT(CASE WHEN baskets_last_60d < 0 THEN 1 END),
            COUNT(CASE WHEN spend_last_60d < 0.0 THEN 1 END),
            COUNT(CASE WHEN baskets_last_90d < 0 THEN 1 END),
            COUNT(CASE WHEN spend_last_90d < 0.0 THEN 1 END),
            COUNT(CASE WHEN weekend_basket_share < 0.0 OR weekend_basket_share > 1.0 THEN 1 END),
            COUNT(CASE WHEN daytime_basket_share < 0.0 OR daytime_basket_share > 1.0 THEN 1 END)
        FROM {table_name};
    """).fetchone()

    if any(v > 0 for v in numeric_violations):
        raise ValueError(f"Numeric domain constraints violated in {table_name}: {numeric_violations}")

    # 5. Window hierarchy validation: 30d <= 60d <= 90d <= total
    window_violations = con.execute(f"""
        SELECT 
            COUNT(CASE WHEN baskets_last_30d > baskets_last_60d THEN 1 END),
            COUNT(CASE WHEN baskets_last_60d > baskets_last_90d THEN 1 END),
            COUNT(CASE WHEN baskets_last_90d > total_baskets THEN 1 END),
            COUNT(CASE WHEN spend_last_30d > spend_last_60d + 0.01 THEN 1 END),
            COUNT(CASE WHEN spend_last_60d > spend_last_90d + 0.01 THEN 1 END)
        FROM {table_name};
    """).fetchone()

    if any(w > 0 for w in window_violations):
        raise ValueError(f"Rolling window monotonicity violated: {window_violations}")

    # 6. Recency check (days_since_last_purchase >= 0)
    recency_audit = con.execute(f"""
        SELECT 
            MIN(days_since_last_purchase),
            MAX(days_since_last_purchase),
            AVG(days_since_last_purchase),
            COUNT(CASE WHEN days_since_last_purchase < 0 THEN 1 END)
        FROM {table_name}
        WHERE total_baskets > 0;
    """).fetchone()

    if recency_audit[3] > 0:
        raise ValueError(f"Found {recency_audit[3]} negative days_since_last_purchase values!")

    # 7. Summary metrics across the mart
    stats = con.execute(f"""
        SELECT 
            ROUND(AVG(total_baskets), 2) as avg_baskets,
            ROUND(AVG(total_spend), 2) as avg_spend,
            ROUND(AVG(avg_basket_value), 2) as avg_basket_val,
            ROUND(AVG(distinct_products_purchased), 2) as avg_products,
            COUNT(CASE WHEN total_baskets = 0 THEN 1 END) as zero_purchase_customers,
            COUNT(CASE WHEN has_redeemed = 1 THEN 1 END) as redeemed_customers,
            COUNT(CASE WHEN is_age_valid = 1 THEN 1 END) as valid_age_customers
        FROM {table_name};
    """).fetchone()

    report = {
        "mart_table": table_name,
        "total_customers": mart_count,
        "total_columns": len(cols),
        "column_names": cols,
        "key_audit": {
            "distinct_clients": key_audit[0],
            "null_clients": key_audit[1],
        },
        "recency_summary": {
            "min_days": recency_audit[0],
            "max_days": recency_audit[1],
            "avg_days": round(recency_audit[2], 2) if recency_audit[2] is not None else None,
        },
        "aggregate_metrics": {
            "avg_baskets": stats[0],
            "avg_spend": stats[1],
            "avg_basket_value": stats[2],
            "avg_distinct_products": stats[3],
            "zero_purchase_customers": stats[4],
            "redeemed_customers": stats[5],
            "valid_age_customers": stats[6],
        },
        "validation_seconds": round(time.time() - t0, 2),
    }

    logger.info("Validation passed successfully in %.2fs. All analytical constraints verified.", report["validation_seconds"])
    return report


def promote_feature_mart(con: duckdb.DuckDBPyConnection) -> None:
    """Atomically promote load_mart_customer_360 to mart_customer_360 inside a transaction."""
    logger.info("Promoting '%s' to '%s' in an atomic transaction...", LOAD_MART_TABLE, FINAL_MART_TABLE)
    con.execute("BEGIN TRANSACTION;")
    try:
        con.execute(f"DROP TABLE IF EXISTS {FINAL_MART_TABLE};")
        con.execute(f"ALTER TABLE {LOAD_MART_TABLE} RENAME TO {FINAL_MART_TABLE};")
        con.execute("COMMIT;")
        logger.info("Successfully promoted '%s'.", FINAL_MART_TABLE)
    except Exception as err:
        con.execute("ROLLBACK;")
        logger.error("Promotion failed, transaction rolled back safely: %s", err)
        raise RuntimeError(f"Mart promotion failed: {err}") from err


def run_customer_360_pipeline(
    manager: DatabaseManager,
    cutoff_dt: str = FEATURE_CUTOFF_TIMESTAMP,
    expected_client_count: Optional[int] = None,
) -> dict[str, Any]:
    """Execute end-to-end safe construction, validation, and promotion of Customer 360 mart."""
    logger.info("Starting safe Customer 360 Feature Mart engineering pipeline...")
    pipeline_start = time.time()

    with manager.get_connection() as con:
        # 1. Clean any stale replacement tables
        clean_stale_feature_tables(con)

        # 2. Materialize into replacement table
        timings = build_feature_mart_stage(con, cutoff_dt=cutoff_dt, target_table=LOAD_MART_TABLE)

        # 3. Validate replacement table before schema promotion
        validation_report = validate_feature_mart(
            con,
            table_name=LOAD_MART_TABLE,
            expected_client_count=expected_client_count,
        )

        # 4. Atomically promote table
        promote_feature_mart(con)

        # 5. Final check on promoted table
        final_count = con.execute(f"SELECT COUNT(*) FROM {FINAL_MART_TABLE};").fetchone()[0]

    total_time = round(time.time() - pipeline_start, 2)
    logger.info("Customer 360 pipeline successfully finished in %.2fs. Rows: %d.", total_time, final_count)

    return {
        "status": "SUCCESS",
        "total_seconds": total_time,
        "timings": timings,
        "validation_report": validation_report,
        "final_mart_count": final_count,
    }


def main() -> None:
    """CLI entrypoint for building and validating Customer 360 mart."""
    parser = argparse.ArgumentParser(description="Custoloom Customer 360 Feature Mart CLI.")
    parser.add_argument(
        "--build-customer-360",
        action="store_true",
        help="Execute safe construction, validation, and promotion of mart_customer_360",
    )
    parser.add_argument(
        "--validate-mart",
        action="store_true",
        help="Run comprehensive data quality checks on the active mart_customer_360",
    )
    parser.add_argument(
        "--cutoff-date",
        type=str,
        default=FEATURE_CUTOFF_TIMESTAMP,
        help=f"Historical observation cutoff datetime (default: {FEATURE_CUTOFF_TIMESTAMP})",
    )
    args = parser.parse_args()

    if args.build_customer_360:
        manager = DatabaseManager()
        results = run_customer_360_pipeline(manager, cutoff_dt=args.cutoff_date)
        print("\n================ CUSTOMER 360 BUILD REPORT ================")
        import pprint
        pprint.pprint(results)
        return

    if args.validate_mart:
        manager = DatabaseManager()
        with manager.get_connection(read_only=True) as con:
            report = validate_feature_mart(con, table_name=FINAL_MART_TABLE)
        print("\n================ CUSTOMER 360 VALIDATION REPORT ================")
        import pprint
        pprint.pprint(report)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
