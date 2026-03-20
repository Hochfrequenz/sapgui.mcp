"""Pytest configuration and shared fixtures for all tests."""

import os
import socket
from collections.abc import Generator

import pytest
from dotenv import load_dotenv

# Load .env file if it exists (for local development and integration tests)
load_dotenv()

# =============================================================================
# SAP INTEGRATION TEST MACHINE CHECK
# =============================================================================

_AUTHORIZED_SAP_TEST_MACHINES = {"HF-KKLEIN3", "HF-MeiskeJ"}


def is_sap_integration_test_machine() -> bool:
    """
    Check if the current machine is authorized to run SAP integration tests.

    SAP integration tests require access to a real SAP Web GUI system,
    which is only available on specific developer machines. This function
    checks the hostname to determine if the current machine has SAP access.

    Returns:
        True if running on a machine with SAP access,
        False otherwise (CI environments, other dev machines).
    """
    return socket.gethostname() in _AUTHORIZED_SAP_TEST_MACHINES


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
