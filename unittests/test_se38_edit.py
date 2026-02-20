"""Tests for SE38 edit tool."""

import pytest
from pydantic import ValidationError


def test_se38_edit_result_success() -> None:
    """Test successful SE38EditResult creation."""
    from sapwebguimcp.models.se38_edit_models import SE38EditResult

    result = SE38EditResult(
        success=True,
        program_name="ZTEST_MCP_EDIT",
        backup_source="REPORT ZTEST_MCP_EDIT.\nWRITE 'OLD'.",
        check_messages=["No syntax errors found"],
        activated=True,
    )
    assert result.success is True
    assert result.program_name == "ZTEST_MCP_EDIT"
    assert result.backup_source == "REPORT ZTEST_MCP_EDIT.\nWRITE 'OLD'."
    assert result.activated is True
    assert result.error is None


def test_se38_edit_result_failure() -> None:
    """Test failed SE38EditResult creation via factory."""
    from sapwebguimcp.models.se38_edit_models import SE38EditResult

    result = SE38EditResult.failure(
        error="Syntax error in line 3",
        program_name="ZTEST_MCP_EDIT",
        backup_source="REPORT ZTEST_MCP_EDIT.\nWRITE 'OLD'.",
        check_messages=["Syntax error: unexpected token"],
        activated=False,
    )
    assert result.success is False
    assert result.error == "Syntax error in line 3"
    assert result.activated is False


def test_se38_edit_result_validation_error() -> None:
    """Test that success=True with error raises ValidationError."""
    from sapwebguimcp.models.se38_edit_models import SE38EditResult

    with pytest.raises(ValidationError):
        SE38EditResult(
            success=True,
            error="This should not be set",
            program_name="ZTEST",
            backup_source="",
            check_messages=[],
            activated=False,
        )


class TestParseStatusNote:
    """Tests for parsing status bar notes from ARIA snapshots."""

    def test_parse_check_success_de(self) -> None:
        from sapwebguimcp.tools.edit_helpers import parse_toolbar_note

        snapshot = '- note "Erfolgreich Meldungsleiste Es wurden keine Syntaxfehler in Report ZTEST_MCP_EDIT gefunden"'
        success, message = parse_toolbar_note(snapshot)
        assert success is True
        assert "keine Syntaxfehler" in message or "No syntax errors" in message

    def test_parse_activate_success_de(self) -> None:
        from sapwebguimcp.tools.edit_helpers import parse_toolbar_note

        snapshot = '- note "Erfolgreich Meldungsleiste Aktives Objekt wurde generiert"'
        success, message = parse_toolbar_note(snapshot)
        assert success is True
        assert "generiert" in message or "generated" in message

    def test_parse_check_failure_de(self) -> None:
        from sapwebguimcp.tools.edit_helpers import parse_toolbar_note

        snapshot = '- note "Fehler Meldungsleiste Syntaxfehler in Zeile 3"'
        success, message = parse_toolbar_note(snapshot)
        assert success is False
        assert "Syntaxfehler" in message

    def test_parse_no_note(self) -> None:
        from sapwebguimcp.tools.edit_helpers import parse_toolbar_note

        snapshot = "- button 'Aktivieren'"
        success, message = parse_toolbar_note(snapshot)
        assert success is False
        assert message  # should have a default message
