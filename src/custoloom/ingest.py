"""DuckDB ingestion pipeline, source audit, and key validation for Custoloom.

Audits candidate keys and row grains across raw X5 RetailHero files and provides
high-performance native DuckDB bulk-loading capabilities using safe load-stage
replacement tables and atomic transactional promotion.
"""

import argparse
import logging
import shutil
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
from custoloom.db import DatabaseManager, stream_csv_sample

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("custoloom.ingest")

EXPECTED_HEADERS = {
    "clients.csv": ["client_id", "first_issue_date", "first_redeem_date", "age", "gender"],
    "products.csv": [
        "product_id", "level_1", "level_2", "level_3", "level_4",
        "segment_id", "brand_id", "vendor_id", "netto", "is_own_trademark", "is_alcohol"
    ],
    "purchases.csv.gz": [
        "client_id", "transaction_id", "transaction_datetime",
        "regular_points_received", "express_points_received",
        "regular_points_spent", "express_points_spent", "purchase_sum",
        "store_id", "product_id", "product_quantity", "trn_sum_from_iss", "trn_sum_from_red"
    ],
    "uplift_train.csv": ["client_id", "treatment_flg", "target"],
    "uplift_test.csv": ["client_id"],
}

EXPECTED_ROW_COUNTS = {
    "clients.csv": 400_162,
    "products.csv": 43_038,
    "purchases.csv.gz": 45_786_568,
    "uplift_train.csv": 200_039,
    "uplift_test.csv": 200_123,
}

# Explicitly typed identifiers to ensure leading zeros and string formats are preserved
PURCHASES_TYPES = {
    "client_id": "VARCHAR",
    "transaction_id": "VARCHAR",
    "store_id": "VARCHAR",
    "product_id": "VARCHAR",
}

STAGE_TABLE_MAP = {
    "load_stg_clients": "stg_clients",
    "load_stg_products": "stg_products",
    "load_stg_purchases": "stg_purchases",
    "load_stg_uplift_train": "stg_uplift_train",
    "load_stg_uplift_test": "stg_uplift_test",
}


def validate_source_headers(raw_data_dir: Path) -> dict[str, list[str]]:
    """Validate that raw file headers match expected schemas."""
    actual_headers = {}
    for filename, expected in EXPECTED_HEADERS.items():
        filepath = raw_data_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Source file missing: {filepath}")
        is_gz = filename.endswith(".gz")
        header, _ = stream_csv_sample(filepath, max_rows=1, is_gzip=is_gz)
        if header != expected:
            raise ValueError(f"Header mismatch in {filename}: expected {expected}, got {header}")
        actual_headers[filename] = header
    logger.info("All 5 raw source file headers validated successfully.")
    return actual_headers


def validate_disk_space(target_path: Path, min_free_gb: float = 10.0) -> float:
    """Check that available disk space is sufficient before running ingestion."""
    check_dir = target_path.parent if target_path.parent.exists() else Path.cwd()
    du = shutil.disk_usage(check_dir)
    free_gb = du.free / (1024 ** 3)
    logger.info("Available disk space on [%s]: %.2f GB (minimum required: %.2f GB)", check_dir, free_gb, min_free_gb)
    if free_gb < min_free_gb:
        raise RuntimeError(
            f"Insufficient disk space on {check_dir}: {free_gb:.2f} GB free, "
            f"minimum required: {min_free_gb:.2f} GB."
        )
    return free_gb


def clean_stale_load_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Inspect and cleanly drop any leftover load-stage tables from an interrupted run."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'load_stg_%';"
    ).fetchall()
    existing_load_tables = [r[0] for r in rows]
    allowed_load_tables = set(STAGE_TABLE_MAP.keys())

    for tbl in existing_load_tables:
        if tbl in allowed_load_tables:
            logger.warning("Found stale load-stage table '%s' from previous interrupted run. Dropping...", tbl)
            con.execute(f"DROP TABLE IF EXISTS {tbl};")
        else:
            raise RuntimeError(f"Unrecognized table found with load prefix: {tbl}")


def create_load_stage_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Create fresh, empty load-stage replacement tables with strict typing."""
    logger.info("Creating clean load-stage replacement tables...")

    con.execute("""
        CREATE TABLE load_stg_clients (
            client_id VARCHAR PRIMARY KEY,
            first_issue_date TIMESTAMP,
            first_redeem_date TIMESTAMP,
            age INTEGER,
            gender VARCHAR,
            loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE load_stg_products (
            product_id VARCHAR PRIMARY KEY,
            level_1 VARCHAR,
            level_2 VARCHAR,
            level_3 VARCHAR,
            level_4 VARCHAR,
            segment_id DOUBLE,
            brand_id VARCHAR,
            vendor_id VARCHAR,
            netto DOUBLE,
            is_own_trademark SMALLINT,
            is_alcohol SMALLINT,
            loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE load_stg_purchases (
            source_row_number BIGINT,
            client_id VARCHAR,
            transaction_id VARCHAR,
            transaction_datetime TIMESTAMP,
            regular_points_received DOUBLE,
            express_points_received DOUBLE,
            regular_points_spent DOUBLE,
            express_points_spent DOUBLE,
            purchase_sum DOUBLE,
            store_id VARCHAR,
            product_id VARCHAR,
            product_quantity DOUBLE,
            trn_sum_from_iss DOUBLE,
            trn_sum_from_red DOUBLE,
            loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE load_stg_uplift_train (
            client_id VARCHAR PRIMARY KEY,
            treatment_flg SMALLINT,
            target SMALLINT,
            loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE load_stg_uplift_test (
            client_id VARCHAR PRIMARY KEY,
            loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    logger.info("All 5 load-stage replacement tables created successfully.")


def bulk_load_all_datasets(con: duckdb.DuckDBPyConnection, raw_data_dir: Path) -> dict[str, dict[str, Any]]:
    """Bulk load all 5 datasets into load-stage tables via native DuckDB SQL."""
    load_metrics: dict[str, dict[str, Any]] = {}

    # 1. clients.csv
    clients_path = (raw_data_dir / "clients.csv").as_posix()
    logger.info("Loading clients from %s...", clients_path)
    t0 = time.time()
    con.execute(f"""
        INSERT INTO load_stg_clients (client_id, first_issue_date, first_redeem_date, age, gender)
        SELECT client_id, first_issue_date, first_redeem_date, age, gender
        FROM read_csv('{clients_path}', header=true, types={{'client_id': 'VARCHAR', 'gender': 'VARCHAR'}});
    """)
    c_count = con.execute("SELECT COUNT(*) FROM load_stg_clients;").fetchone()[0]
    load_metrics["clients"] = {"rows": c_count, "seconds": round(time.time() - t0, 2)}
    logger.info("Loaded %d clients in %.2fs", c_count, load_metrics["clients"]["seconds"])

    # 2. products.csv
    products_path = (raw_data_dir / "products.csv").as_posix()
    logger.info("Loading products from %s...", products_path)
    t0 = time.time()
    con.execute(f"""
        INSERT INTO load_stg_products (
            product_id, level_1, level_2, level_3, level_4,
            segment_id, brand_id, vendor_id, netto, is_own_trademark, is_alcohol
        )
        SELECT 
            product_id, level_1, level_2, level_3, level_4,
            segment_id, brand_id, vendor_id, netto, is_own_trademark, is_alcohol
        FROM read_csv('{products_path}', header=true, types={{'product_id': 'VARCHAR', 'brand_id': 'VARCHAR', 'vendor_id': 'VARCHAR'}});
    """)
    p_count = con.execute("SELECT COUNT(*) FROM load_stg_products;").fetchone()[0]
    load_metrics["products"] = {"rows": p_count, "seconds": round(time.time() - t0, 2)}
    logger.info("Loaded %d products in %.2fs", p_count, load_metrics["products"]["seconds"])

    # 3. uplift_train.csv
    train_path = (raw_data_dir / "uplift_train.csv").as_posix()
    logger.info("Loading uplift_train from %s...", train_path)
    t0 = time.time()
    con.execute(f"""
        INSERT INTO load_stg_uplift_train (client_id, treatment_flg, target)
        SELECT client_id, treatment_flg, target
        FROM read_csv('{train_path}', header=true, types={{'client_id': 'VARCHAR'}});
    """)
    tr_count = con.execute("SELECT COUNT(*) FROM load_stg_uplift_train;").fetchone()[0]
    load_metrics["uplift_train"] = {"rows": tr_count, "seconds": round(time.time() - t0, 2)}
    logger.info("Loaded %d uplift_train rows in %.2fs", tr_count, load_metrics["uplift_train"]["seconds"])

    # 4. uplift_test.csv
    test_path = (raw_data_dir / "uplift_test.csv").as_posix()
    logger.info("Loading uplift_test from %s...", test_path)
    t0 = time.time()
    con.execute(f"""
        INSERT INTO load_stg_uplift_test (client_id)
        SELECT client_id
        FROM read_csv('{test_path}', header=true, types={{'client_id': 'VARCHAR'}});
    """)
    te_count = con.execute("SELECT COUNT(*) FROM load_stg_uplift_test;").fetchone()[0]
    load_metrics["uplift_test"] = {"rows": te_count, "seconds": round(time.time() - t0, 2)}
    logger.info("Loaded %d uplift_test rows in %.2fs", te_count, load_metrics["uplift_test"]["seconds"])

    # 5. purchases.csv.gz (native streaming bulk read with ordinality)
    purchases_path = (raw_data_dir / "purchases.csv.gz").as_posix()
    logger.info("Loading purchases from %s using WITH ORDINALITY...", purchases_path)
    t0 = time.time()
    con.execute(f"""
        INSERT INTO load_stg_purchases (
            source_row_number,
            client_id,
            transaction_id,
            transaction_datetime,
            regular_points_received,
            express_points_received,
            regular_points_spent,
            express_points_spent,
            purchase_sum,
            store_id,
            product_id,
            product_quantity,
            trn_sum_from_iss,
            trn_sum_from_red
        )
        SELECT 
            ordinality::BIGINT AS source_row_number,
            client_id,
            transaction_id,
            transaction_datetime,
            regular_points_received,
            express_points_received,
            regular_points_spent,
            express_points_spent,
            purchase_sum,
            store_id,
            product_id,
            product_quantity,
            trn_sum_from_iss,
            trn_sum_from_red
        FROM read_csv(
            '{purchases_path}',
            header=true,
            compression='gzip',
            types={PURCHASES_TYPES}
        ) WITH ORDINALITY;
    """)
    pu_count = con.execute("SELECT COUNT(*) FROM load_stg_purchases;").fetchone()[0]
    load_metrics["purchases"] = {"rows": pu_count, "seconds": round(time.time() - t0, 2)}
    logger.info("Loaded %d purchases in %.2fs", pu_count, load_metrics["purchases"]["seconds"])

    return load_metrics


def validate_staging_data(
    con: duckdb.DuckDBPyConnection,
    prefix: str = "load_stg_",
    expected_counts: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    """Perform full data integrity, row identity, key constraints, and referential validation."""
    logger.info("Running comprehensive data integrity validation on table set [%s*]...", prefix)
    t0 = time.time()
    expected = expected_counts or EXPECTED_ROW_COUNTS

    tbl_clients = f"{prefix}clients"
    tbl_products = f"{prefix}products"
    tbl_purchases = f"{prefix}purchases"
    tbl_train = f"{prefix}uplift_train"
    tbl_test = f"{prefix}uplift_test"

    # 1. Row counts
    actual_counts = {
        "clients.csv": con.execute(f"SELECT COUNT(*) FROM {tbl_clients};").fetchone()[0],
        "products.csv": con.execute(f"SELECT COUNT(*) FROM {tbl_products};").fetchone()[0],
        "purchases.csv.gz": con.execute(f"SELECT COUNT(*) FROM {tbl_purchases};").fetchone()[0],
        "uplift_train.csv": con.execute(f"SELECT COUNT(*) FROM {tbl_train};").fetchone()[0],
        "uplift_test.csv": con.execute(f"SELECT COUNT(*) FROM {tbl_test};").fetchone()[0],
    }

    for fname, exp_cnt in expected.items():
        act_cnt = actual_counts[fname]
        if act_cnt != exp_cnt:
            raise ValueError(f"Row count mismatch for {fname}: expected {exp_cnt}, found {act_cnt}")

    # 2. Purchase row identity & source_row_number checks
    p_audit = con.execute(f"""
        SELECT 
            MIN(source_row_number),
            MAX(source_row_number),
            COUNT(source_row_number),
            COUNT(CASE WHEN source_row_number IS NULL THEN 1 END),
            COUNT(DISTINCT source_row_number)
        FROM {tbl_purchases};
    """).fetchone()

    min_ord, max_ord, cnt_ord, null_ord, dist_ord = p_audit
    purchases_expected_rows = expected["purchases.csv.gz"]
    if min_ord != 1:
        raise ValueError(f"source_row_number does not start at 1: MIN is {min_ord}")
    if max_ord != purchases_expected_rows:
        raise ValueError(f"source_row_number MAX ({max_ord}) does not equal expected count ({purchases_expected_rows})")
    if null_ord != 0:
        raise ValueError(f"Found {null_ord} NULL values in source_row_number")
    if dist_ord != purchases_expected_rows:
        raise ValueError(f"source_row_number is not strictly unique: distinct count={dist_ord}, expected={purchases_expected_rows}")

    # 3. Duplicate natural keys on purchases: verify preservation
    # Audit found 3 duplicate (transaction_id, product_id) combinations.
    # If full dataset is being validated, confirm exactly 3 duplicate pairs exist.
    dup_pairs_count = con.execute(f"""
        SELECT COUNT(*)
        FROM (
            SELECT transaction_id, product_id
            FROM {tbl_purchases}
            GROUP BY transaction_id, product_id
            HAVING COUNT(*) > 1
        );
    """).fetchone()[0]

    if purchases_expected_rows == EXPECTED_ROW_COUNTS["purchases.csv.gz"] and dup_pairs_count != 3:
        raise ValueError(f"Expected exactly 3 duplicate natural purchase keys preserved, found {dup_pairs_count}")

    # 4. Null checks on required identifiers across all tables
    null_checks = con.execute(f"""
        SELECT 
            (SELECT COUNT(*) FROM {tbl_clients} WHERE client_id IS NULL OR client_id = ''),
            (SELECT COUNT(*) FROM {tbl_products} WHERE product_id IS NULL OR product_id = ''),
            (SELECT COUNT(*) FROM {tbl_train} WHERE client_id IS NULL OR client_id = ''),
            (SELECT COUNT(*) FROM {tbl_test} WHERE client_id IS NULL OR client_id = ''),
            (SELECT COUNT(*) FROM {tbl_purchases} WHERE client_id IS NULL OR client_id = ''),
            (SELECT COUNT(*) FROM {tbl_purchases} WHERE transaction_id IS NULL OR transaction_id = ''),
            (SELECT COUNT(*) FROM {tbl_purchases} WHERE store_id IS NULL OR store_id = ''),
            (SELECT COUNT(*) FROM {tbl_purchases} WHERE product_id IS NULL OR product_id = '');
    """).fetchone()

    if any(n > 0 for n in null_checks):
        raise ValueError(f"Found null or empty identifiers across tables: {null_checks}")

    # 5. Duplicate ID checks on dimension tables
    dim_dups = con.execute(f"""
        SELECT 
            (SELECT COUNT(*) - COUNT(DISTINCT client_id) FROM {tbl_clients}),
            (SELECT COUNT(*) - COUNT(DISTINCT product_id) FROM {tbl_products}),
            (SELECT COUNT(*) - COUNT(DISTINCT client_id) FROM {tbl_train}),
            (SELECT COUNT(*) - COUNT(DISTINCT client_id) FROM {tbl_test});
    """).fetchone()

    if any(d > 0 for d in dim_dups):
        raise ValueError(f"Found duplicate primary keys in dimension tables: {dim_dups}")

    # 6. Uplift partition coverage and overlap against clients
    overlap_count = con.execute(f"""
        SELECT COUNT(*) 
        FROM {tbl_train} tr
        INNER JOIN {tbl_test} te ON tr.client_id = te.client_id;
    """).fetchone()[0]

    if overlap_count != 0:
        raise ValueError(f"Uplift train and test partitions overlap by {overlap_count} clients")

    uplift_missing_in_clients = con.execute(f"""
        WITH all_uplift AS (
            SELECT client_id FROM {tbl_train}
            UNION ALL
            SELECT client_id FROM {tbl_test}
        )
        SELECT COUNT(*)
        FROM all_uplift u
        LEFT JOIN {tbl_clients} c ON u.client_id = c.client_id
        WHERE c.client_id IS NULL;
    """).fetchone()[0]

    clients_missing_in_uplift = con.execute(f"""
        WITH all_uplift AS (
            SELECT client_id FROM {tbl_train}
            UNION ALL
            SELECT client_id FROM {tbl_test}
        )
        SELECT COUNT(*)
        FROM {tbl_clients} c
        LEFT JOIN all_uplift u ON c.client_id = u.client_id
        WHERE u.client_id IS NULL;
    """).fetchone()[0]

    if uplift_missing_in_clients != 0 or clients_missing_in_uplift != 0:
        raise ValueError(
            f"Uplift partition mismatch against clients: "
            f"uplift missing in clients={uplift_missing_in_clients}, clients missing in uplift={clients_missing_in_uplift}"
        )

    # 7. Referential integrity: Purchases -> Clients and Purchases -> Products
    missing_refs = con.execute(f"""
        SELECT 
            COUNT(CASE WHEN c.client_id IS NULL THEN 1 END) as missing_clients,
            COUNT(CASE WHEN pr.product_id IS NULL THEN 1 END) as missing_products
        FROM {tbl_purchases} p
        LEFT JOIN {tbl_clients} c ON p.client_id = c.client_id
        LEFT JOIN {tbl_products} pr ON p.product_id = pr.product_id;
    """).fetchone()

    if missing_refs[0] != 0 or missing_refs[1] != 0:
        raise ValueError(f"Referential integrity failure: missing_clients={missing_refs[0]}, missing_products={missing_refs[1]}")

    # 8. Date ranges and purchase metrics
    p_metrics = con.execute(f"""
        SELECT 
            MIN(transaction_datetime),
            MAX(transaction_datetime),
            MIN(purchase_sum),
            MAX(purchase_sum),
            AVG(purchase_sum),
            COUNT(CASE WHEN purchase_sum IS NULL THEN 1 END)
        FROM {tbl_purchases};
    """).fetchone()

    # 9. Uplift train distributions
    u_dist = con.execute(f"""
        SELECT 
            treatment_flg, 
            target, 
            COUNT(*) as cnt, 
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct
        FROM {tbl_train}
        GROUP BY treatment_flg, target
        ORDER BY treatment_flg, target;
    """).fetchall()

    validation_report = {
        "table_prefix": prefix,
        "row_counts": actual_counts,
        "source_row_number": {
            "min": min_ord,
            "max": max_ord,
            "count": cnt_ord,
            "nulls": null_ord,
            "distinct": dist_ord,
        },
        "duplicate_natural_keys_preserved": dup_pairs_count,
        "null_identifiers": {
            "clients_client_id": null_checks[0],
            "products_product_id": null_checks[1],
            "train_client_id": null_checks[2],
            "test_client_id": null_checks[3],
            "purchases_client_id": null_checks[4],
            "purchases_transaction_id": null_checks[5],
            "purchases_store_id": null_checks[6],
            "purchases_product_id": null_checks[7],
        },
        "dimension_duplicate_keys": {
            "clients": dim_dups[0],
            "products": dim_dups[1],
            "uplift_train": dim_dups[2],
            "uplift_test": dim_dups[3],
        },
        "uplift_partition_checks": {
            "train_test_overlap": overlap_count,
            "uplift_missing_in_clients": uplift_missing_in_clients,
            "clients_missing_in_uplift": clients_missing_in_uplift,
        },
        "referential_integrity": {
            "purchases_missing_clients": missing_refs[0],
            "purchases_missing_products": missing_refs[1],
        },
        "purchases_summary": {
            "min_datetime": str(p_metrics[0]),
            "max_datetime": str(p_metrics[1]),
            "min_purchase_sum": float(p_metrics[2]) if p_metrics[2] is not None else None,
            "max_purchase_sum": float(p_metrics[3]) if p_metrics[3] is not None else None,
            "avg_purchase_sum": float(p_metrics[4]) if p_metrics[4] is not None else None,
            "null_purchase_sums": p_metrics[5],
        },
        "uplift_distributions": [
            {"treatment_flg": int(r[0]), "target": int(r[1]), "count": int(r[2]), "pct": float(r[3])}
            for r in u_dist
        ],
        "validation_seconds": round(time.time() - t0, 2),
    }

    logger.info("Validation completed successfully in %.2fs. All integrity checks passed.", validation_report["validation_seconds"])
    return validation_report


def promote_load_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Atomically promote load-stage tables to final staging tables inside a transaction."""
    logger.info("Promoting load-stage tables to final staging tables in an atomic transaction...")
    con.execute("BEGIN TRANSACTION;")
    try:
        for load_tbl, target_tbl in STAGE_TABLE_MAP.items():
            con.execute(f"DROP TABLE IF EXISTS {target_tbl};")
            con.execute(f"ALTER TABLE {load_tbl} RENAME TO {target_tbl};")
        con.execute("COMMIT;")
        logger.info("Successfully promoted all staging tables.")
    except Exception as err:
        con.execute("ROLLBACK;")
        logger.error("Promotion failed, transaction rolled back safely: %s", err)
        raise RuntimeError(f"Table promotion transaction failed: {err}") from err


def run_full_ingestion(
    manager: DatabaseManager,
    raw_data_dir: Path,
    expected_counts: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    """Execute the end-to-end safe full-dataset ingestion pipeline."""
    logger.info("Starting safe full-dataset ingestion pipeline...")
    overall_start = time.time()

    # Step 1: Pre-flight checks (disk space and headers)
    validate_disk_space(manager.config.db_path, min_free_gb=10.0)
    validate_source_headers(raw_data_dir)

    with manager.get_connection() as con:
        # Step 2: Clean any stale load tables from interrupted runs
        clean_stale_load_tables(con)

        # Step 3: Create fresh load-stage tables
        create_load_stage_tables(con)

        # Step 4: Bulk load all datasets into load-stage tables
        load_metrics = bulk_load_all_datasets(con, raw_data_dir)

        # Step 5: Validate replacement tables before any schema promotion
        validation_report = validate_staging_data(con, prefix="load_stg_", expected_counts=expected_counts)

        # Step 6: Atomically promote replacement tables
        promote_load_tables(con)

        # Step 7: Final quick verification on promoted tables
        final_counts = {}
        for target_tbl in STAGE_TABLE_MAP.values():
            cnt = con.execute(f"SELECT COUNT(*) FROM {target_tbl};").fetchone()[0]
            final_counts[target_tbl] = cnt

    total_time = round(time.time() - overall_start, 2)
    logger.info("Full ingestion pipeline completed successfully in %.2fs.", total_time)

    return {
        "status": "SUCCESS",
        "total_seconds": total_time,
        "load_metrics": load_metrics,
        "validation_report": validation_report,
        "final_tables": final_counts,
    }


def audit_source_datasets(raw_data_dir: Path) -> dict[str, Any]:
    """Audit source files, row counts, and candidate purchase keys using DuckDB."""
    logger.info("Starting comprehensive source data and purchase key audit with DuckDB...")
    t0 = time.time()
    con = duckdb.connect()

    audit_results: dict[str, Any] = {}

    # 1. Counts for flat CSV files
    for fname in ["clients.csv", "products.csv", "uplift_train.csv", "uplift_test.csv"]:
        fpath = (raw_data_dir / fname).as_posix()
        res = con.execute(f"SELECT COUNT(*) FROM read_csv('{fpath}', header=true);").fetchone()
        count = res[0] if res else 0
        audit_results[fname] = {"row_count": count}
        logger.info("File %s: %d rows", fname, count)

    # 2. Forensic audit of purchases.csv.gz (45.78M rows)
    purchases_path = (raw_data_dir / "purchases.csv.gz").as_posix()
    logger.info("Auditing 45M-row purchases.csv.gz (nulls, candidate keys, duplicates)...")
    
    p_audit = con.execute(f"""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(DISTINCT transaction_id) as unique_txns,
            COUNT(DISTINCT product_id) as unique_products,
            COUNT(DISTINCT (transaction_id || '_' || product_id)) as unique_pairs,
            COUNT(*) - COUNT(DISTINCT (transaction_id || '_' || product_id)) as duplicate_pairs,
            COUNT(CASE WHEN transaction_id IS NULL OR transaction_id = '' THEN 1 END) as null_txns,
            COUNT(CASE WHEN product_id IS NULL OR product_id = '' THEN 1 END) as null_prods,
            COUNT(CASE WHEN client_id IS NULL OR client_id = '' THEN 1 END) as null_clients,
            MIN(transaction_datetime) as min_date,
            MAX(transaction_datetime) as max_date,
            MIN(purchase_sum) as min_sum,
            MAX(purchase_sum) as max_sum,
            AVG(purchase_sum) as avg_sum
        FROM read_csv(
            '{purchases_path}', 
            header=true, 
            compression='gzip',
            types={PURCHASES_TYPES}
        );
    """).fetchone()

    audit_results["purchases.csv.gz"] = {
        "total_rows": p_audit[0],
        "unique_transactions": p_audit[1],
        "unique_products": p_audit[2],
        "unique_txn_prod_pairs": p_audit[3],
        "duplicate_txn_prod_pairs": p_audit[4],
        "null_transactions": p_audit[5],
        "null_products": p_audit[6],
        "null_clients": p_audit[7],
        "min_datetime": str(p_audit[8]),
        "max_datetime": str(p_audit[9]),
        "min_purchase_sum": float(p_audit[10]) if p_audit[10] is not None else None,
        "max_purchase_sum": float(p_audit[11]) if p_audit[11] is not None else None,
        "avg_purchase_sum": float(p_audit[12]) if p_audit[12] is not None else None,
    }

    # 3. Inspect duplicate combinations
    if p_audit[4] > 0:
        logger.info("Found %d duplicate (transaction_id, product_id) pairs! Inspecting duplicate records...", p_audit[4])
        dups = con.execute(f"""
            WITH dup_keys AS (
                SELECT transaction_id, product_id
                FROM read_csv('{purchases_path}', header=true, compression='gzip', types={PURCHASES_TYPES})
                GROUP BY transaction_id, product_id
                HAVING COUNT(*) > 1
            )
            SELECT p.client_id, p.transaction_id, p.transaction_datetime, p.store_id, p.product_id, p.product_quantity
            FROM read_csv('{purchases_path}', header=true, compression='gzip', types={PURCHASES_TYPES}) p
            JOIN dup_keys d ON p.transaction_id = d.transaction_id AND p.product_id = d.product_id
            ORDER BY p.transaction_id, p.product_id;
        """).fetchall()
        audit_results["purchases_duplicates_inspection"] = [
            {
                "client_id": d[0],
                "transaction_id": d[1],
                "transaction_datetime": str(d[2]),
                "store_id": d[3],
                "product_id": d[4],
                "product_quantity": float(d[5]),
            }
            for d in dups
        ]

    elapsed = time.time() - t0
    logger.info("Full source audit completed in %.2fs", elapsed)
    return audit_results


def main() -> None:
    """CLI entrypoint for source auditing and ingestion control."""
    parser = argparse.ArgumentParser(description="Custoloom DuckDB Ingestion, Validation, and Source Audit CLI.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("D:/DA projects/optispend-engine/data/raw"),
        help="Path to raw datasets directory",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Perform complete source row counts and purchase key audit without modifying database",
    )
    parser.add_argument(
        "--validate-staging",
        action="store_true",
        help="Run comprehensive data integrity validation suite on active staging tables",
    )
    parser.add_argument(
        "--full-ingest",
        action="store_true",
        help="Execute full safe dataset ingestion into persistent DuckDB database",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Load small sample into DuckDB staging tables (for development/testing)",
    )
    args = parser.parse_args()

    # Validate headers before any operation
    validate_source_headers(args.raw_dir)

    if args.audit_only:
        results = audit_source_datasets(args.raw_dir)
        print("\n================ SOURCE DATA & KEY AUDIT REPORT ================")
        import pprint
        pprint.pprint(results)
        return

    if args.validate_staging:
        manager = DatabaseManager()
        with manager.get_connection(read_only=True) as con:
            report = validate_staging_data(con, prefix="stg_")
        print("\n================ ACTIVE STAGING VALIDATION REPORT ================")
        import pprint
        pprint.pprint(report)
        return

    if args.full_ingest:
        manager = DatabaseManager()
        results = run_full_ingestion(manager, args.raw_dir)
        print("\n================ FULL INGESTION REPORT ================")
        import pprint
        pprint.pprint(results)
        return

    if args.sample_size:
        from custoloom.staging import load_staging_samples
        manager = DatabaseManager()
        ddl_path = PACKAGE_ROOT / "sql" / "001_create_staging_tables.sql"
        if ddl_path.exists():
            manager.execute_script(ddl_path)
        logger.info("Loading %d sample rows into DuckDB...", args.sample_size)
        res = load_staging_samples(manager, args.raw_dir, sample_size=args.sample_size)
        print("\n=== Sample Staging Results ===")
        import pprint
        pprint.pprint(res)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
