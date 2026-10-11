"""Application and database configuration management."""

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


@dataclass(frozen=True)
class DatabaseConfig:
    """Database connection configuration for PostgreSQL."""

    host: str
    port: int
    name: str
    user: str
    password: Optional[str] = None

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "DatabaseConfig":
        """Load and validate database configuration from environment variables or .env file."""
        if env_file and env_file.exists():
            load_dotenv(env_file, override=True)
        else:
            load_dotenv()

        host = os.getenv("CUSTOLOOM_DB_HOST", os.getenv("DB_HOST", "localhost"))
        port_raw = os.getenv("CUSTOLOOM_DB_PORT", os.getenv("DB_PORT", "5432"))
        name = os.getenv("CUSTOLOOM_DB_NAME", os.getenv("DB_NAME", "custoloom"))
        user = os.getenv("CUSTOLOOM_DB_USER", os.getenv("DB_USER"))
        password = os.getenv("CUSTOLOOM_DB_PASSWORD", os.getenv("DB_PASSWORD"))

        missing = []
        if not user:
            missing.append("DB_USER (or CUSTOLOOM_DB_USER)")
        if not password:
            missing.append("DB_PASSWORD (or CUSTOLOOM_DB_PASSWORD)")

        if missing:
            raise ConfigurationError(
                f"Missing required database settings: {', '.join(missing)}"
            )

        try:
            port = int(port_raw)
        except ValueError as err:
            raise ConfigurationError(f"Invalid DB_PORT value: {port_raw}") from err

        return cls(host=host, port=port, name=name, user=user, password=password)

    @property
    def dsn(self) -> str:
        """Construct a libpq connection string."""
        return (
            f"host={self.host} port={self.port} dbname={self.name} "
            f"user={self.user} password={self.password}"
        )

    def safe_summary(self) -> dict[str, str | int | bool]:
        """Return non-sensitive connection details for logging/diagnostics."""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.name,
            "user": self.user,
            "password_configured": bool(self.password),
        }


@dataclass(frozen=True)
class AppConfig:
    """Top-level application settings."""

    base_dir: Path
    data_raw_dir: Path
    data_processed_dir: Path
    environment: str

    @classmethod
    def load(cls, env_file: Optional[Path] = None) -> "AppConfig":
        """Initialize configuration, optionally loading from a .env file."""
        if env_file and env_file.exists():
            load_dotenv(env_file, override=True)
        else:
            load_dotenv()

        base_dir = Path(os.getenv("CUSTOLOOM_BASE_DIR", Path.cwd()))
        data_raw = Path(os.getenv("CUSTOLOOM_RAW_DATA_DIR", base_dir / "data" / "raw"))
        data_processed = Path(
            os.getenv("CUSTOLOOM_PROCESSED_DATA_DIR", base_dir / "data" / "processed")
        )
        environment = os.getenv("CUSTOLOOM_ENV", "development")

        return cls(
            base_dir=base_dir,
            data_raw_dir=data_raw,
            data_processed_dir=data_processed,
            environment=environment,
        )
