"""Pytest configuration and shared fixtures for all tests."""

import os
from collections.abc import Generator, Iterable
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env file if it exists (for local development and integration tests)
load_dotenv()

# =============================================================================
# SAP CREDENTIAL DETECTION
# =============================================================================


def _has_sap_config() -> bool:
    """Check if a valid sap-mcp-config systems.json is available."""
    try:
        from sapguimcp.models.config import get_sap_config

        cfg = get_sap_config()
        default = cfg.get_default()
        return bool(default.user and default.password.get_secret_value() and default.client)
    except Exception:  # pylint: disable=broad-except
        return False


def has_sap_desktop_creds() -> bool:
    """Check if SAP credentials are configured (via systems.json)."""
    return _has_sap_config()


def has_sap_webgui_creds() -> bool:
    """Check if SAP credentials are configured (via systems.json) and SAP_URL is set or host is configured."""
    if not _has_sap_config():
        return False
    return bool(os.environ.get("SAP_URL", "").strip()) or True  # host from systems.json is always available


# =============================================================================
# AUTOUSE FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_settings() -> Generator[None, None, None]:
    """Reset global settings before each test."""
    import sapguimcp.models.config

    sapguimcp.models.config._settings = None
    sapguimcp.models.config._sap_config = None
    yield
    sapguimcp.models.config._settings = None
    sapguimcp.models.config._sap_config = None


@pytest.fixture(autouse=True)
def clean_environment() -> Generator[None, None, None]:
    """Clean environment variables before each test."""
    env_vars_to_clear = [
        "SAP_URL",
        "BROWSER_MODE",
        "BROWSER_TYPE",
        "BROWSER_HEADLESS",
        "CDP_URL",
        "SAP_CONFIG_FILE",
        "CHROME_PATH",
        "CHROME_USER_DATA_DIR",
    ]

    original_values = {var: os.environ.get(var) for var in env_vars_to_clear}

    for var in env_vars_to_clear:
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original_values.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


# =============================================================================
# AUTOMATIC "integration" MARKER
# =============================================================================

_LIVE_SAP_FIXTURES_ANYWHERE = frozenset({"sap_mcp_client"})
_LIVE_SAP_FIXTURES_DESKTOP = frozenset({"backend"})  # defined in unittests/desktop/conftest.py
_DESKTOP_DIR = Path(__file__).parent / "desktop"


def is_live_sap_item(fixturenames: Iterable[str], path: Path | str) -> bool:
    """Return True if a test requests a fixture that drives a live SAP system.

    ``sap_mcp_client`` (WebGUI) counts anywhere; ``backend`` (desktop COM) only under ``unittests/desktop``,
    where it is defined.
    """
    names = set(fixturenames)
    if names & _LIVE_SAP_FIXTURES_ANYWHERE:
        return True
    if names & _LIVE_SAP_FIXTURES_DESKTOP:
        return Path(path).resolve().is_relative_to(_DESKTOP_DIR.resolve())
    return False


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test that uses a live SAP fixture with ``integration``.

    This makes ``-m "not integration"`` a reliable offline-only filter and ``-m integration`` a live-only one,
    independent of file or test names.
    """
    for item in items:
        if is_live_sap_item(item.fixturenames, item.path):
            item.add_marker(pytest.mark.integration)
