"""DuckDB staging layer sample loader and schema verification utility.

Provides safe, repeatable sample loading for X5 RetailHero raw datasets
into DuckDB staging tables without mutating existing objects or creating
duplicate records on reruns.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Optional

# Ensure package root is in sys.path when executed directly as script
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from custoloom.config import DatabaseConfig, DatabaseConnectionError
from custoloom.db import DatabaseManager, stream_csv_sample

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("custoloom.staging")

ID_COLUMN_TYPES = {
    "client_id": "VARCHAR",
    "product_id": "VARCHAR",
    "transaction_id": "VARCHAR",
    "store_id": "VARCHAR",
    "brand_id": "VARCHAR",
    "vendor_id": "VARCHAR",
    "gender": "VARCHAR",
}


def get_existing_purchase_keys(manager: DatabaseManager) -> set[tuple[str, str]]:
    """Fetch existing (transaction_id, product_id) pairs to avoid duplicate sample rows."""
    query = "SELECT transaction_id, product_id FROM stg_purchases;"
    with manager.get_connection(read_only=True) as conn:
        rows = conn.execute(query).fetchall()
        return {(str(r[0]), str(r[1])) for r in rows}


def inspect_representative_records(manager: DatabaseManager) -> dict[str, dict[str, Any]]:
    """Fetch one representative record from each staging table for inspection."""
    samples = {}
    with manager.get_connection(read_only=True) as conn:
        for tbl in ("stg_clients", "stg_products", "stg_purchases", "stg_uplift_train", "stg_uplift_test"):
            if manager.inspect_table_exists(tbl):
                res = conn.execute(f"SELECT * FROM {tbl} LIMIT 1;").fetchone()
                if res and conn.description:
                    col_names = [desc[0] for desc in conn.description]
                    samples[tbl] = dict(zip(col_names, res))
    return samples


def load_staging_samples(
    manager: DatabaseManager,
    raw_data_dir: Path,
    sample_size: int = 100,
) -> dict[str, dict[str, int]]:
    """Load small, repeatable samples into the DuckDB staging tables.

    Uses ON CONFLICT DO NOTHING for tables with primary keys, and checks
    existing candidate pairs for stg_purchases to avoid duplicates on rerun.
    """
    if not raw_data_dir.exists():
        raise FileNotFoundError(f"Raw data directory not found: {raw_data_dir}")

    results: dict[str, dict[str, int]] = {}

    # 1. stg_clients
    clients_file = raw_data_dir / "clients.csv"
    if clients_file.exists():
        header, rows = stream_csv_sample(clients_file, max_rows=sample_size, is_gzip=False)
        before_count = manager.fetch_row_count("stg_clients")
        manager.load_sample_batch("stg_clients", header, rows, conflict_key="client_id")
        after_count = manager.fetch_row_count("stg_clients")
        results["stg_clients"] = {
            "requested": len(rows),
            "inserted": after_count - before_count,
            "total": after_count,
        }

    # 2. stg_products
    products_file = raw_data_dir / "products.csv"
    if products_file.exists():
        header, rows = stream_csv_sample(products_file, max_rows=sample_size, is_gzip=False)
        before_count = manager.fetch_row_count("stg_products")
        manager.load_sample_batch("stg_products", header, rows, conflict_key="product_id")
        after_count = manager.fetch_row_count("stg_products")
        results["stg_products"] = {
            "requested": len(rows),
            "inserted": after_count - before_count,
            "total": after_count,
        }

    # 3. stg_purchases (streamed from gzip)
    purchases_file = raw_data_dir / "purchases.csv.gz"
    if purchases_file.exists():
        header, rows = stream_csv_sample(purchases_file, max_rows=sample_size, is_gzip=True)
        existing_keys = get_existing_purchase_keys(manager)
        new_rows = [r for r in rows if (str(r[1]), str(r[9])) not in existing_keys]
        before_count = manager.fetch_row_count("stg_purchases")
        if new_rows:
            manager.load_sample_batch("stg_purchases", header, new_rows)
        after_count = manager.fetch_row_count("stg_purchases")
        results["stg_purchases"] = {
            "requested": len(rows),
            "inserted": len(new_rows),
            "total": after_count,
        }

    # 4. stg_uplift_train
    uplift_file = raw_data_dir / "uplift_train.csv"
    if uplift_file.exists():
        header, rows = stream_csv_sample(uplift_file, max_rows=sample_size, is_gzip=False)
        before_count = manager.fetch_row_count("stg_uplift_train")
        manager.load_sample_batch("stg_uplift_train", header, rows, conflict_key="client_id")
        after_count = manager.fetch_row_count("stg_uplift_train")
        results["stg_uplift_train"] = {
            "requested": len(rows),
            "inserted": after_count - before_count,
            "total": after_count,
        }

    # 5. stg_uplift_test
    uplift_test_file = raw_data_dir / "uplift_test.csv"
    if uplift_test_file.exists():
        header, rows = stream_csv_sample(uplift_test_file, max_rows=sample_size, is_gzip=False)
        before_count = manager.fetch_row_count("stg_uplift_test")
        manager.load_sample_batch("stg_uplift_test", header, rows, conflict_key="client_id")
        after_count = manager.fetch_row_count("stg_uplift_test")
        results["stg_uplift_test"] = {
            "requested": len(rows),
            "inserted": after_count - before_count,
            "total": after_count,
        }

    return results


def main() -> None:
    """CLI entrypoint for loading staging samples into DuckDB."""
    parser = argparse.ArgumentParser(description="Load small samples into Custoloom DuckDB staging tables.")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of rows per dataset to load (default: 100)",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("D:/DA projects/optispend-engine/data/raw"),
        help="Path to raw datasets directory",
    )
    args = parser.parse_args()

    manager = DatabaseManager()
    logger.info("Connected to DuckDB at [%s]", manager.config.db_path)

    # Initialize staging tables if they don't exist
    project_root = Path(__file__).resolve().parents[2]
    ddl_path = project_root / "sql" / "001_create_staging_tables.sql"
    if ddl_path.exists():
        manager.execute_script(ddl_path)

    logger.info("Starting safe sample load (size: %d rows per file)...", args.sample_size)
    results = load_staging_samples(manager, args.raw_dir, sample_size=args.sample_size)

    print("\n--- Staging Sample Load Summary ---")
    for tbl, counts in results.items():
        print(f"  {tbl}: Requested={counts['requested']}, Inserted={counts['inserted']}, Total Rows={counts['total']}")

    reps = inspect_representative_records(manager)
    print("\n--- Representative Records ---")
    for tbl, rec in reps.items():
        preview = {k: v for k, v in list(rec.items())[:4]}
        print(f"  {tbl}: {preview}")


if __name__ == "__main__":
    main()
