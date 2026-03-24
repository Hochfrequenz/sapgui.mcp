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


def _env_non_empty(*keys: str) -> bool:
    """Return True if all named env vars are set and non-empty."""
    return all(os.environ.get(k, "").strip() for k in keys)


def has_sap_desktop_creds() -> bool:
    """Check if SAP desktop integration credentials are configured.

    Returns True when SAP_USER, SAP_PASSWORD, SAP_MANDANT, and
    SAP_CONNECTION_NAME are all set to non-empty values.
    """
    return _env_non_empty("SAP_USER", "SAP_PASSWORD", "SAP_MANDANT", "SAP_CONNECTION_NAME")


def has_sap_webgui_creds() -> bool:
    """Check if SAP WebGUI integration credentials are configured.

    Returns True when SAP_USER, SAP_PASSWORD, SAP_MANDANT, and
    SAP_URL are all set to non-empty values.
    """
    return _env_non_empty("SAP_USER", "SAP_PASSWORD", "SAP_MANDANT", "SAP_URL")


# =============================================================================
# AUTOUSE FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_settings() -> Generator[None, None, None]:
    """Reset global settings before each test."""
    import sapwebguimcp.models.config

    sapwebguimcp.models.config._settings = None
    yield
    sapwebguimcp.models.config._settings = None


@pytest.fixture(autouse=True)
def clean_environment() -> Generator[None, None, None]:
    """Clean environment variables before each test."""
    env_vars_to_clear = [
        "SAP_URL",
        "BROWSER_MODE",
        "BROWSER_TYPE",
        "BROWSER_HEADLESS",
        "CDP_URL",
        "SAP_CONNECTION_NAME",
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
