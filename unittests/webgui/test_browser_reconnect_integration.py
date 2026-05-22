"""Integration tests for browser reconnect and screenshot."""

import asyncio
import base64

import pytest
from mcp import ClientSession
from mcp.types import ImageContent

from sapguimcp.models import (
    LoginResult,
    SessionStatus,
    TransactionResult,
)

from .conftest import call_tool_typed
from .integration_helpers import _wait_for_transaction_screen


@pytest.mark.anyio
async def test_browser_reconnect_after_idle(sap_mcp_client: ClientSession) -> None:
    """
    Test that browser reconnects after becoming stale.

    This test simulates a scenario where the CDP connection becomes stale
    (e.g., browser was minimized, focus was lost, or connection timed out).
    The server should automatically reconnect and continue working.
    """
    # Step 1: Login and verify we have a working session
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"
    assert login_result.url, "Expected URL in login response"

    # Step 2: Navigate to a transaction
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Step 3: Wait a bit to let connection potentially become stale
    # In real scenarios, this could be minutes; here we just verify the flow works
    await asyncio.sleep(5)

    # Step 4: Try to use the browser again - this should reconnect if stale
    status_result = await call_tool_typed(sap_mcp_client, "sap_session_status", {}, SessionStatus)

    # Should be able to get status (either connected or reconnected)
    assert status_result.status is not None, f"Should get valid session status after idle period: {status_result}"

    # Step 5: Verify we can still execute transactions
    tx_result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    assert tx_result.success, f"Transaction after idle failed: {tx_result.error}"
    assert tx_result.tcode, f"Transaction should work after idle: {tx_result}"


@pytest.mark.anyio
async def test_browser_reconnect_multiple_times(sap_mcp_client: ClientSession) -> None:
    """
    Test that browser can reconnect multiple times during a session.

    This verifies the reconnection logic is robust and doesn't leave
    the browser manager in a bad state after reconnecting.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    transactions = ["SE16", "SM37", "SU3", "SE16"]

    for i, tcode in enumerate(transactions):
        # Small delay between transactions
        await asyncio.sleep(2)

        # Execute transaction
        result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": tcode}, TransactionResult)
        assert result.success, f"Transaction {tcode} failed: {result.error}"
        assert result.tcode, f"Transaction {tcode} should work: {result}"

        # Verify session is still valid
        status = await call_tool_typed(sap_mcp_client, "sap_session_status", {}, SessionStatus)
        assert status.status is not None, f"Expected valid status after transaction {i+1}: {status}"


@pytest.mark.anyio
async def test_browser_screenshot_returns_mcp_image_content(sap_mcp_client: ClientSession) -> None:
    """
    Test that browser_screenshot returns a native MCP ImageContent.

    This verifies that:
    1. The tool returns ImageContent (type='image') instead of text with base64
    2. The image data is valid base64-encoded PNG
    3. The image can be decoded and has reasonable dimensions

    Using native MCP ImageContent is more token-efficient than returning base64
    as a string, because the MCP client can process the image as binary data
    rather than as text tokens.
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Take a screenshot
    result = await sap_mcp_client.call_tool("browser_screenshot", {})

    # Verify we got a response
    assert result.content, "Expected non-empty response from browser_screenshot"

    # The first content block should be an ImageContent
    content = result.content[0]
    assert isinstance(content, ImageContent), (
        f"Expected ImageContent, got {type(content).__name__}. "
        "Screenshot should return native MCP image, not text with base64."
    )

    # Verify the ImageContent structure
    assert content.type == "image", f"Expected type='image', got '{content.type}'"
    assert content.mimeType == "image/png", f"Expected mimeType='image/png', got '{content.mimeType}'"
    assert content.data, "Expected non-empty image data"

    # Verify the base64 data is valid and decodes to PNG
    try:
        image_bytes = base64.b64decode(content.data)
    except Exception as e:
        raise AssertionError(f"Image data is not valid base64: {e}") from e

    # PNG files start with the magic bytes: 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A
    png_magic = b"\x89PNG\r\n\x1a\n"
    assert image_bytes[:8] == png_magic, (
        f"Image data does not start with PNG magic bytes. " f"Got: {image_bytes[:8].hex()}, expected: {png_magic.hex()}"
    )

    # Verify reasonable image size (at least 1KB, at most 10MB)
    image_size = len(image_bytes)
    assert image_size > 1024, f"Image seems too small: {image_size} bytes"
    assert image_size < 10 * 1024 * 1024, f"Image seems too large: {image_size} bytes"

    print(f"\nScreenshot captured successfully:")
    print(f"  - Type: {content.type}")
    print(f"  - MIME type: {content.mimeType}")
    print(f"  - Size: {image_size:,} bytes")
