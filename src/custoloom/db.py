"""DuckDB connection and staging management utilities."""

import csv
import gzip
import logging
from pathlib import Path
from typing import Any, Optional
import duckdb

from custoloom.config import DatabaseConfig, ConfigurationError, DatabaseConnectionError

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
    """Manages DuckDB connections and staging operations."""

    def __init__(
        self,
        config: Optional[DatabaseConfig] = None,
        env_file: Optional[Path] = None,
    ):
        """Initialize database manager, resolving configuration if not provided."""
        self._config = config
        self._env_file = env_file
        self._conn = None

    @property
    def config(self) -> DatabaseConfig:
        """Resolve and return database configuration."""
        if self._config is None:
            self._config = DatabaseConfig.from_env(env_file=self._env_file)
        return self._config

    def get_connection(self, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        """Open and return a DuckDB connection cursor.

        Creates target directory if necessary. Configures pragmas for threads,
        memory limit, and temp storage. Returns a cursor so exiting a context
        manager does not close the shared connection.
        """
        try:
            if self._conn is None:
                db_path_str = str(self.config.db_path)
                if db_path_str != ":memory:":
                    self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
                    if read_only and not self.config.db_path.exists():
                        read_only = False
                else:
                    read_only = False

                self._conn = duckdb.connect(db_path_str, read_only=read_only)

                if self.config.threads:
                    self._conn.execute(f"SET threads TO {self.config.threads};")
                if self.config.memory_limit:
                    self._conn.execute(f"SET memory_limit = '{self.config.memory_limit}';")
                if self.config.temp_directory:
                    self.config.temp_directory.mkdir(parents=True, exist_ok=True)
                    self._conn.execute(f"SET temp_directory = '{self.config.temp_directory.as_posix()}';")

            return self._conn.cursor()
        except Exception as err:
            safe_msg = f"Failed to connect to DuckDB at '{self.config.db_path}': {err}"
            logger.error("[ERROR] %s", safe_msg)
            raise DatabaseConnectionError(safe_msg) from None

    def close(self) -> None:
        """Explicitly close the underlying DuckDB connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def execute_script(self, script_path: Path) -> None:
        """Execute a DDL/SQL script file."""
        if not script_path.exists():
            raise FileNotFoundError(f"SQL script not found: {script_path}")

        sql_content = script_path.read_text(encoding="utf-8")
        with self.get_connection() as conn:
            conn.execute(sql_content)
        logger.info("[INFO] Successfully executed script: %s", script_path.name)

    def fetch_row_count(self, table_name: str) -> int:
        """Query and return the current row count of a table."""
        with self.get_connection(read_only=True) as conn:
            res = conn.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()
            return res[0] if res else 0

    def inspect_table_exists(self, table_name: str) -> bool:
        """Check whether a table exists in the current schema."""
        query = "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?;"
        with self.get_connection(read_only=True) as conn:
            res = conn.execute(query, [table_name]).fetchone()
            return bool(res and res[0] > 0)

    def inspect_table_columns(self, table_name: str) -> dict[str, str]:
        """Inspect actual column names and data types from information_schema."""
        query = """
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = ? 
            ORDER BY ordinal_position;
        """
        with self.get_connection(read_only=True) as conn:
            rows = conn.execute(query, [table_name]).fetchall()
            return {col: dtype for col, dtype in rows}

    def load_sample_batch(
        self,
        table_name: str,
        columns: list[str],
        rows: list[list[Any]],
        conflict_key: Optional[str] = None,
    ) -> int:
        """Safely load sample rows into a table using parameterized insertion.

        Uses INSERT OR IGNORE / ON CONFLICT DO NOTHING where supported, or checks keys.
        """
        if not rows:
            return 0

        col_str = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        sql_query = f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders})"

        if conflict_key:
            sql_query += f" ON CONFLICT ({conflict_key}) DO NOTHING"

        with self.get_connection() as conn:
            conn.executemany(sql_query, rows)

        logger.info("[INFO] Loaded %d sample rows into %s", len(rows), table_name)
        return len(rows)
