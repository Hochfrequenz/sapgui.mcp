"""Pytest configuration and shared fixtures for all tests."""

import os
from collections.abc import Generator

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
