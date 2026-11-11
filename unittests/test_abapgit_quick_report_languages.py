"""abapGit and quick-report texts in both logon languages (#1044, phase 3, area 7)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp import lang
from sapguimcp.models.sap_results import StatusBarInfo
from sapguimcp.tools import abapgit_tools
from sapguimcp.tools.quick_report_tools import classify_result_screen


@pytest.mark.parametrize(
    ("code", "text", "expected"),
    [
        ("DE", "Transport erforderlich", True),
        ("EN", "Transport required. Provide P_TRKORR= KS", True),
        ("EN", "Please provide P_TRKORR= for this operation", True),
        ("EN", "Transport erforderlich", False),
        ("DE", "Repository not found", False),
    ],
)
def test_transport_required_detection(code: str, text: str, expected: bool) -> None:
    with lang.use(code):
        assert abapgit_tools._is_transport_required_error(text, lang.current()) is expected


@pytest.mark.parametrize(
    ("code", "text"),
    [("DE", "Benutzer X hat keine modifizierbare Aufgabe"), ("EN", "User X has no modifiable task in <request>")],
)
def test_no_task_detection(code: str, text: str) -> None:
    with lang.use(code):
        assert abapgit_tools._is_no_task_error(text, lang.current())


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
        error = await abapgit_tools._check_for_error_popup(backend, lang.current())

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
