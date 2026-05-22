"""Tests for SE24 edit tool."""

import pytest
from pydantic import ValidationError


def test_se24_edit_result_success() -> None:
    """Test successful SE24EditResult creation."""
    from sapguimcp.models.se24_edit_models import SE24EditResult

    result = SE24EditResult(
        success=True,
        class_name="ZCL_TEST_MCP_EDIT",
        method_name="DO_SOMETHING",
        backup_source="  METHOD do_something.\n  ENDMETHOD.",
        check_messages=["No syntax errors found"],
        activated=True,
    )
    assert result.success is True
    assert result.class_name == "ZCL_TEST_MCP_EDIT"
    assert result.method_name == "DO_SOMETHING"
    assert result.backup_source == "  METHOD do_something.\n  ENDMETHOD."
    assert result.activated is True
    assert result.error is None


def test_se24_edit_result_failure() -> None:
    """Test failed SE24EditResult creation via factory."""
    from sapguimcp.models.se24_edit_models import SE24EditResult

    result = SE24EditResult.failure(
        error="Syntax error in line 3",
        class_name="ZCL_TEST_MCP_EDIT",
        method_name="DO_SOMETHING",
        backup_source="  METHOD do_something.\n  ENDMETHOD.",
        check_messages=["Syntax error: unexpected token"],
        activated=False,
    )
    assert result.success is False
    assert result.error == "Syntax error in line 3"
    assert result.activated is False


def test_se24_edit_result_validation_error() -> None:
    """Test that success=True with error raises ValidationError."""
    from sapguimcp.models.se24_edit_models import SE24EditResult

    with pytest.raises(ValidationError):
        SE24EditResult(
            success=True,
            error="This should not be set",
            class_name="ZCL_TEST",
            method_name="DO_SOMETHING",
            backup_source="",
            check_messages=[],
            activated=False,
        )


class TestParseStatusNote:
    """Tests for parsing status bar notes — shared with SE38/SE37 but verified for SE24 context."""

    def test_parse_check_success_de(self) -> None:
        from sapguimcp.backend.webgui.backend import _parse_toolbar_note as parse_toolbar_note

        snapshot = (
            '- note "Erfolgreich Meldungsleiste Es wurden keine Syntaxfehler in Klasse ZCL_TEST_MCP_EDIT gefunden"'
        )
        success, message = parse_toolbar_note(snapshot)
        assert success is True
        assert "keine Syntaxfehler" in message

    def test_parse_activate_success_de(self) -> None:
        from sapguimcp.backend.webgui.backend import _parse_toolbar_note as parse_toolbar_note

        snapshot = '- note "Erfolgreich Meldungsleiste Objekt wurde aktiviert"'
        success, message = parse_toolbar_note(snapshot)
        assert success is True

    def test_parse_check_failure_de(self) -> None:
        from sapguimcp.backend.webgui.backend import _parse_toolbar_note as parse_toolbar_note

        snapshot = '- note "Fehler Meldungsleiste Syntaxfehler in Zeile 3"'
        success, message = parse_toolbar_note(snapshot)
        assert success is False
        assert "Syntaxfehler" in message

    def test_parse_check_success_en(self) -> None:
        from sapguimcp.backend.webgui.backend import _parse_toolbar_note as parse_toolbar_note

        snapshot = '- note "Success Message Bar No syntax errors found in Class ZCL_TEST_MCP_EDIT"'
        success, message = parse_toolbar_note(snapshot)
        assert success is True
        assert "No syntax errors" in message

    def test_parse_activate_success_en(self) -> None:
        from sapguimcp.backend.webgui.backend import _parse_toolbar_note as parse_toolbar_note

        snapshot = '- note "Success Message Bar Object activated"'
        success, message = parse_toolbar_note(snapshot)
        assert success is True
        assert "Object activated" in message

    def test_parse_check_failure_en(self) -> None:
        from sapguimcp.backend.webgui.backend import _parse_toolbar_note as parse_toolbar_note

        snapshot = '- note "Error Message Bar Syntax error in line 3"'
        success, message = parse_toolbar_note(snapshot)
        assert success is False

    def test_parse_no_note(self) -> None:
        from sapguimcp.backend.webgui.backend import _parse_toolbar_note as parse_toolbar_note

        snapshot = "- button 'Aktivieren'"
        success, message = parse_toolbar_note(snapshot)
        assert success is False
        assert message


@pytest.mark.anyio
async def test_se24_edit_tool_is_registered() -> None:
    """Test that register_se24_edit_tools adds the tool to a FastMCP instance."""
    from fastmcp import FastMCP

    from sapguimcp.tools.se24_edit_tools import register_se24_edit_tools

    mcp = FastMCP("test")
    register_se24_edit_tools(mcp)

    tool = await mcp.get_tool("sap_se24_edit")
    assert tool is not None, "sap_se24_edit tool not found after registration"
