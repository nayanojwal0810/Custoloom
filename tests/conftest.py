import os
import sys
from pathlib import Path
import pytest

# Add src to Python path for test discovery
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom CLI options."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run live integration tests against persistent DuckDB database",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip tests marked 'integration' unless --run-integration or env var is set."""
    run_integration = config.getoption("--run-integration") or os.getenv("CUSTOLOOM_RUN_INTEGRATION_TESTS") == "1"
    if run_integration:
        return

    skip_marker = pytest.mark.skip(
        reason="Skipped: requires --run-integration or CUSTOLOOM_RUN_INTEGRATION_TESTS=1 (persistent database test)"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)

