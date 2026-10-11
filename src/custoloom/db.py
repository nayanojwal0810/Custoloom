"""PostgreSQL connection and staging management utilities."""

import csv
import gzip
import logging
from pathlib import Path
from typing import Any, Optional
import psycopg

from custoloom.config import DatabaseConfig, ConfigurationError

logger = logging.getLogger(__name__)


def stream_csv_sample(
    file_path: Path, max_rows: int = 100, is_gzip: bool = False
) -> tuple[list[str], list[list[Optional[str]]]]:
    """Stream a small sample of rows from a flat or compressed CSV file.

    Does not decompress or load the entire file into memory. Empty string values
    are normalized to None for SQL NULL compatibility.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Source file not found: {file_path}")

    opener = gzip.open if is_gzip else open
    with opener(file_path, "rt", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        sample_rows = []
        for _, row in zip(range(max_rows), reader):
            cleaned_row = [val if val != "" else None for val in row]
            sample_rows.append(cleaned_row)

    logger.info(
        "Read %d sample rows from %s (columns: %d)",
        len(sample_rows),
        file_path.name,
        len(header),
    )
    return header, sample_rows


class DatabaseManager:
    """Manages PostgreSQL connections and staging operations."""

    def __init__(self, config: Optional[DatabaseConfig] = None):
        """Initialize database manager, resolving configuration if not provided."""
        self._config = config

    @property
    def config(self) -> DatabaseConfig:
        """Resolve and return database configuration, failing explicitly if unconfigured."""
        if self._config is None:
            self._config = DatabaseConfig.from_env()
        return self._config

    def get_connection(self) -> psycopg.Connection:
        """Open and return a new psycopg connection using the resolved DSN."""
        try:
            conn = psycopg.connect(self.config.dsn)
            logger.info(
                "Connected to PostgreSQL database: %s on %s:%d",
                self.config.name,
                self.config.host,
                self.config.port,
            )
            return conn
        except psycopg.Error as err:
            logger.error("Failed to connect to PostgreSQL: %s", type(err).__name__)
            raise

    def execute_script(self, script_path: Path) -> None:
        """Execute a DDL/SQL script file within a single transaction."""
        if not script_path.exists():
            raise FileNotFoundError(f"SQL script not found: {script_path}")

        sql_content = script_path.read_text(encoding="utf-8")
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_content)
            conn.commit()
        logger.info("Successfully executed script: %s", script_path.name)

    def insert_sample_rows(
        self,
        table_name: str,
        columns: list[str],
        rows: list[list[Any]],
    ) -> int:
        """Insert sample rows using parameterized query."""
        if not rows:
            return 0

        col_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders})"

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()

        logger.info("Inserted %d sample rows into %s", len(rows), table_name)
        return len(rows)

    def fetch_row_count(self, table_name: str) -> int:
        """Query and return the current row count of a table."""
        query = f"SELECT COUNT(*) FROM {table_name}"
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                return row[0] if row else 0
