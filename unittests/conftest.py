"""Pytest configuration and fixtures for SAP Web GUI MCP Server tests."""

import os
import socket
import sys
from collections.abc import AsyncGenerator, Generator
from typing import Literal

import pytest
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Load .env file if it exists (for local development and integration tests)
load_dotenv()


@pytest.fixture
def anyio_backend() -> Literal["asyncio"]:
    """Specify asyncio as the anyio backend for pytest."""
    return "asyncio"


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
async def sap_mcp_client(
    anyio_backend: Literal["asyncio"],
) -> AsyncGenerator[ClientSession, None]:
    """
    Fixture that provides an MCP client connected to a real SAP Web GUI server.

    This fixture:
    1. Skips if not running on an authorized machine (HF-KKLEIN3)
    2. Skips if SAP_URL environment variable is not set
    3. Starts the sapwebguimcp server as a subprocess
    4. Connects an MCP client via stdio
    5. Yields the client session for tests to call tools
    6. Cleans up on teardown

    Known Issue - Teardown Error (can be ignored):
    pytest-asyncio runs fixture teardown in a different task than setup, which
    causes anyio's cancel scope to fail with "Attempted to exit cancel scope in
    a different task". This is a known limitation when using anyio-based context
    managers (stdio_client) with pytest-asyncio async generator fixtures.

    The tests still PASS and cleanup completes correctly - the browser shuts down
    and the server terminates properly. The error only appears in the teardown
    phase and does not affect test results.

    See: https://github.com/agronholm/anyio/issues/648
    """
    _ = anyio_backend  # Required for anyio

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

    # Use sys.executable with -m to run the server module directly.
    # This works regardless of whether the entry point script is installed,
    # making tests runnable from any Python environment (PyCharm, tox, etc.)
    #
    # We explicitly pass SAP-related environment variables to the subprocess
    # because the clean_environment fixture clears them, and load_dotenv only
    # restores them in the test process, not in the subprocess environment.
    server_env = {
        **os.environ,  # Inherit current environment
        "SAP_URL": os.environ.get("SAP_URL", ""),
        "SAP_USER": os.environ.get("SAP_USER", ""),
        "SAP_PASSWORD": os.environ.get("SAP_PASSWORD", ""),
        "SAP_MANDANT": os.environ.get("SAP_MANDANT", ""),
        "SAP_LANGUAGE": os.environ.get("SAP_LANGUAGE", "EN"),
    }
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "sapwebguimcp.server"],
        env=server_env,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session
