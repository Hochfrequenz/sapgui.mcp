"""Pytest configuration and fixtures for SAP Web GUI MCP Server tests."""

import os
import socket
from collections.abc import AsyncGenerator, Generator

import pytest
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Load .env file if it exists (for local development and integration tests)
load_dotenv()

_AUTHORIZED_SAP_TEST_MACHINE = "HF-KKLEIN3"


def is_sap_integration_test_machine() -> bool:
    """
    Check if the current machine is authorized to run SAP integration tests.

    SAP integration tests require access to a real SAP Web GUI system,
    which is only available on specific developer machines. This function
    checks the hostname to determine if the current machine has SAP access.

    Returns:
        True if running on a machine with SAP access (HF-KKLEIN3),
        False otherwise (CI environments, other dev machines).
    """
    return socket.gethostname() == _AUTHORIZED_SAP_TEST_MACHINE


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


@pytest.fixture
async def sap_mcp_client() -> AsyncGenerator[ClientSession, None]:
    """
    Fixture that provides an MCP client connected to a real SAP Web GUI server.

    This fixture:
    1. Skips if not running on an authorized machine (HF-KKLEIN3)
    2. Skips if SAP_URL environment variable is not set
    3. Starts the sapwebguimcp server as a subprocess
    4. Connects an MCP client via stdio
    5. Yields the client session for tests to call tools
    6. Cleans up on teardown
    """
    current_host = socket.gethostname()
    if not is_sap_integration_test_machine():
        pytest.skip(
            f"SAP integration tests only run on authorized machines "
            f"(current: '{current_host}', required: '{_AUTHORIZED_SAP_TEST_MACHINE}')"
        )

    # Reload .env after clean_environment fixture has cleared env vars
    load_dotenv(override=True)

    sap_url = os.environ.get("SAP_URL")
    if not sap_url:
        pytest.skip("SAP_URL environment variable not set")

    server_params = StdioServerParameters(
        command="run-sapwebgui-mcp-server",
        env=None,  # Inherits SAP_URL from environment
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session
