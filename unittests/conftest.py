"""Pytest configuration and fixtures for SAP Web GUI MCP Server tests."""

import base64
import json
import os
import socket
import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any, Literal, TypeVar

import pytest
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import BaseModel

# Load .env file if it exists (for local development and integration tests)
load_dotenv()

# =============================================================================
# LANGUAGE HANDLING
# =============================================================================

SapLanguage = Literal["DE", "EN"]


@pytest.fixture
def sap_language() -> SapLanguage:
    """Get current SAP language from environment (default: DE)."""
    lang = os.environ.get("SAP_LANGUAGE", "DE").upper()
    if lang not in ("DE", "EN"):
        return "DE"
    return lang  # type: ignore[return-value]


@pytest.fixture
def lang_strings(sap_language: SapLanguage) -> dict[str, str]:
    """
    Get language-specific test strings based on SAP_LANGUAGE.

    Usage in tests:
        def test_something(lang_strings):
            assert lang_strings["yes"] in button_text
    """
    from unittests.testdata.lang_test import (
        BP_GP_ROLE_DEFAULT_DE,
        BP_GP_ROLE_DEFAULT_EN,
        BP_GP_ROLE_LABEL_DE,
        BP_GP_ROLE_LABEL_EN,
        BP_GROUPING_LABEL_DE,
        BP_GROUPING_LABEL_EN,
        BP_NO_BUTTON_DE,
        BP_NO_BUTTON_EN,
        BP_POSTAL_CODE_DE,
        BP_POSTAL_CODE_EN,
        BP_YES_BUTTON_DE,
        BP_YES_BUTTON_EN,
        SE38_CONTINUE_BUTTON_DE,
        SE38_CONTINUE_BUTTON_EN,
        SE38_CREATE_BUTTON_DE,
        SE38_CREATE_BUTTON_EN,
        SE38_LONG_DOC_BUTTON_DE,
        SE38_LONG_DOC_BUTTON_EN,
        SM30_MAINTAIN_BUTTON_DE,
        SM30_MAINTAIN_BUTTON_EN,
    )

    if sap_language == "DE":
        return {
            "postal_code": BP_POSTAL_CODE_DE,
            "yes": BP_YES_BUTTON_DE,
            "no": BP_NO_BUTTON_DE,
            "gp_role_label": BP_GP_ROLE_LABEL_DE,
            "gp_role_default": BP_GP_ROLE_DEFAULT_DE,
            "grouping_label": BP_GROUPING_LABEL_DE,
            "create": SE38_CREATE_BUTTON_DE,
            "continue": SE38_CONTINUE_BUTTON_DE,
            "long_doc": SE38_LONG_DOC_BUTTON_DE,
            "maintain": SM30_MAINTAIN_BUTTON_DE,
        }
    return {
        "postal_code": BP_POSTAL_CODE_EN,
        "yes": BP_YES_BUTTON_EN,
        "no": BP_NO_BUTTON_EN,
        "gp_role_label": BP_GP_ROLE_LABEL_EN,
        "gp_role_default": BP_GP_ROLE_DEFAULT_EN,
        "grouping_label": BP_GROUPING_LABEL_EN,
        "create": SE38_CREATE_BUTTON_EN,
        "continue": SE38_CONTINUE_BUTTON_EN,
        "long_doc": SE38_LONG_DOC_BUTTON_EN,
        "maintain": SM30_MAINTAIN_BUTTON_EN,
    }


# Path to HTML snapshots directory for selector unit tests
HTML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "html_snapshots"


@pytest.fixture
def html_snapshots_path() -> Path:
    """Return the path to the HTML snapshots directory."""
    return HTML_SNAPSHOTS_DIR


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


# =============================================================================
# TYPED TEST HELPERS
# =============================================================================
#
# IMPORTANT: These helpers assume tools return JSON-serialized Pydantic models.
#
# DO NOT use call_tool_typed() for tools that may return non-JSON content:
#   - browser_get_html: Returns raw HTML as File when content > 80KB
#   - browser_screenshot: Returns binary image data
#   - Any tool returning File or binary content
#
# For browser_get_html, use get_html_content() instead which handles both
# JSON (HtmlResult) and File (raw HTML) response formats.
# =============================================================================

T = TypeVar("T", bound=BaseModel)
E = TypeVar("E", bound=BaseModel)


def _extract_content_text(content_item: Any) -> str:
    """Extract text from MCP content item (TextContent or EmbeddedResource)."""
    if hasattr(content_item, "text"):
        return content_item.text
    elif hasattr(content_item, "resource") and hasattr(content_item.resource, "blob"):
        return base64.b64decode(content_item.resource.blob).decode("utf-8")
    return str(content_item)


def _is_json_content(text: str) -> bool:
    """Check if text looks like JSON (starts with { or [)."""
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


async def call_tool_typed(
    client: ClientSession,
    tool_name: str,
    args: dict[str, Any],
    result_type: type[T],
    error_type: type[E] | None = None,
) -> T | E:
    """
    Call an MCP tool and return a typed Pydantic model.

    IMPORTANT: Only use for tools that ALWAYS return JSON. For tools that may
    return File/binary content (browser_get_html, browser_screenshot), use
    the specialized helpers instead.

    Discriminates using:
    - success=False -> parse as error_type (if provided)
    - presence of 'error' field with non-None value -> parse as error_type
    - otherwise -> parse as result_type

    Args:
        client: MCP ClientSession
        tool_name: Name of the tool to call
        args: Arguments to pass to the tool
        result_type: Pydantic model type for success responses
        error_type: Optional Pydantic model type for error responses

    Returns:
        Parsed and validated Pydantic model instance

    Raises:
        json.JSONDecodeError: If the response is not valid JSON (e.g., raw HTML)
    """
    result = await client.call_tool(tool_name, args)
    assert result.content, f"{tool_name} returned no content"

    text = _extract_content_text(result.content[0])
    data = json.loads(text)

    # Discriminate between success/error
    if error_type is not None:
        is_error = data.get("success") is False or data.get("error") is not None
        if is_error:
            return error_type.model_validate(data)

    return result_type.model_validate(data)


async def get_html_content(
    client: ClientSession,
    selector: str | None = None,
    outer: bool = True,
) -> str:
    """
    Get HTML content from the browser, handling both JSON and File responses.

    browser_get_html returns HtmlResult (JSON) for small pages but returns
    the HTML as a File (binary) when content exceeds ~80KB. This helper
    handles both cases transparently.

    Args:
        client: MCP ClientSession
        selector: Optional CSS selector to scope the HTML
        outer: True for outerHTML, False for innerHTML

    Returns:
        HTML content as string
    """
    args: dict[str, Any] = {"outer": outer}
    if selector:
        args["selector"] = selector

    result = await client.call_tool("browser_get_html", args)
    assert result.content, "browser_get_html returned no content"

    # Extract text from first content item
    text = _extract_content_text(result.content[0])

    # Check if it's JSON (HtmlResult) or raw HTML (from File)
    if _is_json_content(text):
        data = json.loads(text)
        if data.get("success") is False:
            raise RuntimeError(f"browser_get_html failed: {data.get('error')}")
        return data.get("html", "")
    else:
        # Raw HTML content from File response
        return text


async def assert_tool_success_untyped(
    client: ClientSession,
    tool_name: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call tool, assert success=True, return raw dict. For simple cases."""
    result = await client.call_tool(tool_name, args or {})
    assert result.content, f"{tool_name} returned no content"
    text = _extract_content_text(result.content[0])
    data = json.loads(text)
    assert data.get("success", True), f"{tool_name} failed: {data.get('error')}"
    return data


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

    Note: We use pytest-anyio (bundled with anyio) instead of pytest-asyncio
    because MCP's stdio_client uses anyio task groups internally. pytest-anyio
    runs fixture setup and teardown in the same task, which is required for
    proper cancel scope handling.
    """
    current_host = socket.gethostname()
    if not is_sap_integration_test_machine():
        pytest.skip(
            f"SAP integration tests only run on authorized machines "
            f"(current: '{current_host}', required: '{_AUTHORIZED_SAP_TEST_MACHINE}')"
        )

    # Reload .env after clean_environment fixture has cleared env vars
    # Use override=False so command-line env vars (like SAP_LANGUAGE=EN) take precedence
    load_dotenv(override=False)

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
