"""PostgreSQL connection and staging management utilities."""

import csv
import gzip
import logging
from pathlib import Path
from typing import Any, Optional
import psycopg
from psycopg import sql

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
        "[INFO] Read %d sample rows from %s (columns: %d)",
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
                "[INFO] Connected to PostgreSQL database: %s on %s:%d",
                self.config.name,
                self.config.host,
                self.config.port,
            )
            return conn
        except psycopg.Error as err:
            logger.error("[ERROR] Failed to connect to PostgreSQL: %s", type(err).__name__)
            raise

    def get_server_version(self) -> tuple[str, str, int]:
        """Return server version string, database name, and port (excluding secrets)."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                row = cur.fetchone()
                version_str = row[0] if row else "unknown"
                return version_str, self.config.name, self.config.port

    def execute_script(self, script_path: Path) -> None:
        """Execute a DDL/SQL script file within a single transaction."""
        if not script_path.exists():
            raise FileNotFoundError(f"SQL script not found: {script_path}")

        sql_content = script_path.read_text(encoding="utf-8")
        with self.get_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(sql_content)
        logger.info("[INFO] Successfully executed script: %s", script_path.name)

    def load_sample_batch(
        self,
        table_name: str,
        columns: list[str],
        rows: list[list[Any]],
        conflict_key: Optional[str] = None,
        truncate_first: bool = False,
    ) -> int:
        """Safely load sample rows into a table using parameterized insertion.

        Identifiers are safely quoted via psycopg.sql.Identifier. The operation
        runs within a transaction, rolling back on error.
        """
        if not rows:
            return 0

        insert_query = sql.SQL("INSERT INTO {table} ({fields}) VALUES ({values})").format(
            table=sql.Identifier(table_name),
            fields=sql.SQL(", ").join(map(sql.Identifier, columns)),
            values=sql.SQL(", ").join(sql.Placeholder() * len(columns)),
        )

        if conflict_key:
            insert_query += sql.SQL(" ON CONFLICT ({key}) DO NOTHING").format(
                key=sql.Identifier(conflict_key)
            )

        with self.get_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    if truncate_first:
                        cur.execute(
                            sql.SQL("TRUNCATE TABLE {table}").format(
                                table=sql.Identifier(table_name)
                            )
                        )
                    cur.executemany(insert_query, rows)

        logger.info(
            "[INFO] Loaded %d sample rows into %s (truncate=%s, conflict_key=%s)",
            len(rows),
            table_name,
            truncate_first,
            conflict_key,
        )
        return len(rows)

    def fetch_row_count(self, table_name: str) -> int:
        """Query and return the current row count of a table."""
        count_query = sql.SQL("SELECT COUNT(*) FROM {table}").format(
            table=sql.Identifier(table_name)
        )
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_query)
                row = cur.fetchone()
                return row[0] if row else 0

    def inspect_table_columns(self, table_name: str) -> dict[str, str]:
        """Inspect actual column names and data types from information_schema."""
        query = """
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = %s 
            ORDER BY ordinal_position;
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (table_name,))
                rows = cur.fetchall()
                return {col: dtype for col, dtype in rows}
