"""abapGit and quick-report texts in both logon languages (#1044, phase 3, area 7)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp import lang
from sapguimcp.models.sap_results import StatusBarInfo
from sapguimcp.tools import abapgit_tools
from sapguimcp.tools.quick_report_tools import classify_result_screen


@pytest.mark.parametrize("code", ["DE", "EN"])
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Transport erforderlich", True),
        ("Transport required. Provide P_TRKORR= KS", True),
        ("Please provide P_TRKORR= for this operation", True),
        ("Repository not found", False),
    ],
)
def test_transport_required_detection_ignores_the_session_language(code: str, text: str, expected: bool) -> None:
    """Popup texts are matched in every language: a German popup in an English session still counts."""
    with lang.use(code):
        assert abapgit_tools._is_transport_required_error(text) is expected


@pytest.mark.parametrize("code", ["DE", "EN"])
@pytest.mark.parametrize(
    "text", ["Benutzer X hat keine modifizierbare Aufgabe", "User X has no modifiable task in <request>"]
)
def test_no_task_detection_ignores_the_session_language(code: str, text: str) -> None:
    with lang.use(code):
        assert abapgit_tools._is_no_task_error(text)


@pytest.mark.parametrize("code", ["DE", "EN"])
@pytest.mark.parametrize(
    ("title", "expected"),
    [("Inaktive Objekte", True), ("Inactive Objects", True), ("Something else", False)],
)
def test_inactive_objects_popup_in_either_language(code: str, title: str, expected: bool) -> None:
    with lang.use(code):
        assert abapgit_tools._is_inactive_objects_popup(SimpleNamespace(title=title, message="")) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        # Desktop: the message ID decides, whatever the logon language put into the text.
        ("EN", StatusBarInfo(type="S", message="anything", message_id="S#", message_number="343"), True),
        ("DE", StatusBarInfo(type="S", message="Transaktion Z_X existiert nicht", message_id=None), True),
        ("EN", StatusBarInfo(type="E", message="Transaction Z_X does not exist"), True),
        ("EN", StatusBarInfo(type="S", message="Pull successful", message_id="S#", message_number="000"), False),
    ],
)
def test_transaction_not_found(code: str, status: StatusBarInfo, expected: bool) -> None:
    with lang.use(code):
        assert abapgit_tools._is_transaction_not_found(status, lang.current()) is expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("code", "popup_text"),
    [
        ("DE", "Fehler beim Aktivieren\nAbbrechen\nOK"),
        ("EN", "Error while activating\nCancel\nOK"),
    ],
)
async def test_popup_error_drops_the_button_labels(code: str, popup_text: str) -> None:
    backend = MagicMock()
    backend.backend_type = "desktop"
    backend.check_popup = AsyncMock(return_value=SimpleNamespace(message=popup_text))
    with lang.use(code):
        error = await abapgit_tools._check_for_error_popup(backend)

    assert error is not None
    assert "OK" not in error.split()
    assert "Abbrechen" not in error
    assert "Cancel" not in error


@pytest.mark.anyio
async def test_pull_without_a_session_language_is_not_turned_into_a_failure_result() -> None:
    with lang.use(None), pytest.raises(lang.UnsupportedLanguageError):
        await abapgit_tools._abapgit_pull_via_api(MagicMock(), "R", None, None, None)


def _classifier_backend(status: StatusBarInfo) -> MagicMock:
    backend = MagicMock()
    backend.get_status_bar = AsyncMock(return_value=status)
    backend.get_page_title = AsyncMock(return_value="Report")
    backend.get_snapshot = AsyncMock(return_value="")
    return backend


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("DE", "Keine Belege gefunden"),
        ("DE", "No documents found"),  # a German session also reads English texts
        ("EN", "No documents found"),
        ("EN", "No data selected"),
    ],
)
async def test_empty_result_status_in_both_languages(code: str, message: str) -> None:
    backend = _classifier_backend(StatusBarInfo(type="S", message=message))
    with lang.use(code):
        classification, _ = await classify_result_screen(backend, lang.current())

    assert classification.value == "empty"


def _se38_backend(fill_result: SimpleNamespace) -> MagicMock:
    backend = MagicMock()
    backend.fill_element_by_locator = AsyncMock(return_value=False)
    backend.fill_form = AsyncMock(return_value=fill_result)
    return backend


@pytest.mark.anyio
async def test_se38_program_field_not_filled_is_an_error_in_an_english_session() -> None:
    """One label only (``Program``): not_found=["Program"] must not count as filled."""
    backend = _se38_backend(SimpleNamespace(filled=[], not_found=["Program"]))
    with lang.use("EN"):
        assert await abapgit_tools._fill_se38_program_field(backend, "ZPROG", lang.current()) is False


@pytest.mark.anyio
async def test_se38_read_stops_when_the_program_field_cannot_be_filled() -> None:
    backend = _se38_backend(SimpleNamespace(filled=[], not_found=["Program"]))
    backend.press_key = AsyncMock()
    backend.wait = AsyncMock()
    with lang.use("EN"), patch.object(abapgit_tools, "_navigate_to_se38", AsyncMock(return_value=None)):
        result = await abapgit_tools.read_se38_source(backend, "ZPROG", lang.current())

    assert result == {"success": False, "error": "Could not find program input field"}
    backend.press_key.assert_not_awaited()


@pytest.mark.anyio
async def test_se38_program_field_filled_by_the_second_label_in_a_german_session() -> None:
    backend = _se38_backend(SimpleNamespace(filled=["Program"], not_found=["Programm"]))
    with lang.use("DE"):
        assert await abapgit_tools._fill_se38_program_field(backend, "ZPROG", lang.current()) is True
