"""Unit tests for classify_result_screen()."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from sapwebguimcp.models import ScreenText, StatusBarInfo
from sapwebguimcp.models.quick_report_models import ScreenClassification
from sapwebguimcp.tools.quick_report_tools import classify_result_screen


def _make_backend(
    *,
    status_type: str = "none",
    status_message: str = "",
    snapshot: str = "- document 'SAP'",
    screen_title: str = "SAP",
) -> AsyncMock:
    """Create a mock backend with configurable responses."""
    backend = AsyncMock()
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type=status_type, message=status_message))
    backend.get_snapshot = AsyncMock(return_value=snapshot)
    backend.get_screen_text = AsyncMock(return_value=ScreenText(title=screen_title))
    backend.get_page_title = AsyncMock(return_value=screen_title)
    return backend


@pytest.mark.anyio
class TestClassifyResultScreen:
    """Tests for classify_result_screen()."""

    async def test_error_status_bar(self) -> None:
        """Status bar type 'E' → ERROR."""
        backend = _make_backend(
            status_type="E",
            status_message="Werk XXXX existiert nicht",
        )
        classification, status_bar = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR
        assert status_bar.type == "E"

    async def test_empty_keine_daten(self) -> None:
        """Status bar message 'Keine Daten gefunden' → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="Keine Daten gefunden",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_empty_no_data_english(self) -> None:
        """Status bar message 'No data found' → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="No data was found for the specified selection criteria",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_empty_keine_werte(self) -> None:
        """Status bar message 'keine Werte' → EMPTY."""
        backend = _make_backend(
            status_type="W",
            status_message="Es wurden keine Werte selektiert",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_empty_no_entries(self) -> None:
        """Status bar message 'no entries' → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="No entries found",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_table_grid_detected(self) -> None:
        """ARIA snapshot with '- grid' line → TABLE."""
        backend = _make_backend(
            status_type="S",
            status_message="5 Einträge gelesen",
            snapshot="- document 'SAP'\n  - grid 'ALV Grid'\n    - row 'Header'",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.TABLE

    async def test_unknown_no_grid_no_error(self) -> None:
        """No grid, no error, no empty message → UNKNOWN."""
        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot="- document 'SAP'\n  - dialog 'Variantenauswahl'",
            screen_title="Variantenauswahl",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.UNKNOWN

    async def test_error_takes_priority_over_grid(self) -> None:
        """Error status bar takes priority even if grid is present."""
        backend = _make_backend(
            status_type="E",
            status_message="Fehler aufgetreten",
            snapshot="- document 'SAP'\n  - grid 'ALV Grid'",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR

    async def test_empty_takes_priority_over_grid(self) -> None:
        """Empty message takes priority even if grid is present."""
        backend = _make_backend(
            status_type="I",
            status_message="Keine Daten gefunden",
            snapshot="- document 'SAP'\n  - grid 'Empty Grid'",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY
