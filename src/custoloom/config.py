"""Application and DuckDB database configuration management."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class ConfigurationError(ValueError):
    """Raised when required configuration settings are missing or invalid."""
    pass


class DatabaseConnectionError(RuntimeError):
    """Raised when connecting to DuckDB fails."""
    pass


@dataclass(frozen=True)
class DatabaseConfig:
    """Database configuration for persistent or in-memory DuckDB."""

    db_path: Path
    threads: Optional[int] = None
    memory_limit: Optional[str] = None
    temp_directory: Optional[Path] = None

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "DatabaseConfig":
        """Load and validate DuckDB configuration from environment variables or .env file."""
        if env_file is not None:
            if env_file.exists():
                load_dotenv(env_file, override=True)
        else:
            load_dotenv()

        base_dir = Path(os.getenv("CUSTOLOOM_BASE_DIR", Path.cwd()))
        default_db = base_dir / "data" / "processed" / "custoloom.duckdb"
        db_path_raw = os.getenv("CUSTOLOOM_DB_PATH", os.getenv("DUCKDB_PATH", str(default_db)))

        if db_path_raw == ":memory:":
            db_path = Path(":memory:")
        else:
            db_path = Path(db_path_raw)

        threads_raw = os.getenv("CUSTOLOOM_DB_THREADS", os.getenv("DUCKDB_THREADS"))
        threads = None
        if threads_raw:
            try:
                threads = int(threads_raw)
            except ValueError as err:
                raise ConfigurationError(f"Invalid CUSTOLOOM_DB_THREADS: {threads_raw}") from err

        memory_limit = os.getenv("CUSTOLOOM_DB_MEMORY_LIMIT", os.getenv("DUCKDB_MEMORY_LIMIT"))

        temp_dir_raw = os.getenv("CUSTOLOOM_DB_TEMP_DIR")
        temp_dir = Path(temp_dir_raw) if temp_dir_raw else None

        return cls(
            db_path=db_path,
            threads=threads,
            memory_limit=memory_limit,
            temp_directory=temp_dir,
        )

    def safe_summary(self) -> dict[str, str | int | None]:
        """Return non-sensitive connection details for logging/diagnostics."""
        return {
            "db_path": str(self.db_path),
            "threads": self.threads,
            "memory_limit": self.memory_limit,
            "temp_directory": str(self.temp_directory) if self.temp_directory else None,
        }


@dataclass(frozen=True)
class AppConfig:
    """Top-level application settings."""

    base_dir: Path
    data_raw_dir: Path
    data_processed_dir: Path
    db: DatabaseConfig

    @classmethod
    def load(cls, env_file: Optional[Path] = None) -> "AppConfig":
        """Initialize configuration, optionally loading from a .env file."""
        if env_file is not None:
            if env_file.exists():
                load_dotenv(env_file, override=True)
        else:
            load_dotenv()

        base_dir = Path(os.getenv("CUSTOLOOM_BASE_DIR", Path.cwd()))
        data_raw_env = os.getenv("CUSTOLOOM_RAW_DATA_DIR")
        data_raw = Path(data_raw_env) if data_raw_env else (base_dir / "data" / "raw")
        data_processed = Path(
            os.getenv("CUSTOLOOM_PROCESSED_DATA_DIR", base_dir / "data" / "processed")
        )

        db_config = DatabaseConfig.from_env(env_file=env_file)

        return cls(
            base_dir=base_dir,
            data_raw_dir=data_raw,
            data_processed_dir=data_processed,
            db=db_config,
        )
