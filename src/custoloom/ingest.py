"""DuckDB ingestion pipeline, source audit, and key validation for Custoloom.

Audits candidate keys and row grains across raw X5 RetailHero files and provides
high-performance native DuckDB bulk-loading capabilities.
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

# Explicitly typed identifiers to ensure leading zeros and string formats are preserved
PURCHASES_TYPES = {
    "client_id": "VARCHAR",
    "transaction_id": "VARCHAR",
    "store_id": "VARCHAR",
    "product_id": "VARCHAR",
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
    parser = argparse.ArgumentParser(description="Custoloom DuckDB Ingestion and Source Audit CLI.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("D:/DA projects/optispend-engine/data/raw"),
        help="Path to raw datasets directory",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Perform complete source row counts and purchase key audit",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Load small sample into DuckDB staging tables",
    )
    parser.add_argument(
        "--full-ingest",
        action="store_true",
        help="Perform full ingestion (deferred in Task 4 until audit approval)",
    )
    args = parser.parse_args()

    # Validate headers
    validate_source_headers(args.raw_dir)

    if args.audit_only:
        results = audit_source_datasets(args.raw_dir)
        print("\n================ SOURCE DATA & KEY AUDIT REPORT ================")
        import pprint
        pprint.pprint(results)
        return

    if args.full_ingest:
        logger.warning(
            "FULL INGESTION DEFERRED: Full 45M-row ingestion is intentionally deferred in Task 4 "
            "to verify purchase row identity and staging architecture first."
        )
        return

    if args.sample_size:
        from custoloom.staging import load_staging_samples, inspect_representative_records
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

    logger.info("No action specified. Run with --audit-only to audit source data and purchase keys.")


if __name__ == "__main__":
    main()
