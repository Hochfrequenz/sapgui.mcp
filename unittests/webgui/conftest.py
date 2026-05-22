"""Pytest configuration and fixtures for WebGUI-specific tests."""

import base64
import json
import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Literal, TypeVar

import pytest
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import BaseModel

from unittests.conftest import has_sap_webgui_creds

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
    from unittests.webgui.testdata.lang_test import (
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
        SE38_CREATE_BUTTON_DE,
        SE38_CREATE_BUTTON_EN,
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
        "maintain": SM30_MAINTAIN_BUTTON_EN,
    }


# Path to HTML snapshots directory for selector unit tests
HTML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "html_snapshots"


@pytest.fixture
def html_snapshots_path() -> Path:
    """Return the path to the HTML snapshots directory."""
    return HTML_SNAPSHOTS_DIR


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


async def call_tool_raw(
    client: ClientSession,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """
    Call an MCP tool and return raw dict result.

    Use this for tools that return dict/JSON but don't have a Pydantic model.

    Args:
        client: MCP ClientSession
        tool_name: Name of the tool to call
        args: Arguments to pass to the tool

    Returns:
        Parsed JSON as dict

    Raises:
        json.JSONDecodeError: If the response is not valid JSON
    """
    result = await client.call_tool(tool_name, args)
    assert result.content, f"{tool_name} returned no content"

    text = _extract_content_text(result.content[0])
    return json.loads(text)


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
    3. Starts the sapguimcp server as a subprocess
    4. Connects an MCP client via stdio
    5. Yields the client session for tests to call tools
    6. Cleans up on teardown

    Note: We use pytest-anyio (bundled with anyio) instead of pytest-asyncio
    because MCP's stdio_client uses anyio task groups internally. pytest-anyio
    runs fixture setup and teardown in the same task, which is required for
    proper cancel scope handling.
    """
    # Reload .env after clean_environment fixture has cleared env vars
    # Use override=False so command-line env vars (like SAP_LANGUAGE=EN) take precedence
    load_dotenv(override=False)

    if not has_sap_webgui_creds():
        pytest.skip("SAP WebGUI credentials not configured (need systems.json and SAP_URL)")

    # Use sys.executable with -m to run the server module directly.
    # This works regardless of whether the entry point script is installed,
    # making tests runnable from any Python environment (PyCharm, tox, etc.)
    #
    # We pass SAP_CONFIG_FILE so the subprocess can find the shared
    # sap-mcp-config systems.json even after clean_environment clears env vars.
    config_file = os.environ.get("SAP_CONFIG_FILE", "")
    server_env = {
        **os.environ,  # Inherit current environment
        "SAP_URL": os.environ.get("SAP_URL", ""),
        "SAP_LANGUAGE": os.environ.get("SAP_LANGUAGE", "EN"),
        **({"SAP_CONFIG_FILE": config_file} if config_file else {}),
    }
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "sapguimcp.server"],
        env=server_env,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session

            # Teardown: navigate back to Easy Access (main menu) to prevent
            # SAP session state from bleeding into subsequent tests.
            # All integration tests share the same Chrome browser via CDP,
            # so leftover popups or sub-screens can cause cascade failures.
            try:
                # Dismiss any open popups
                for _ in range(3):
                    await session.call_tool("sap_press_key", {"key": "Escape"})
                # Press Back (F3) multiple times to return to main menu
                for _ in range(5):
                    await session.call_tool("sap_press_key", {"key": "F3"})
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # Best effort — don't fail teardown
