"""Unit tests for classify_result_screen()."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp.models import ScreenText, StatusBarInfo
from sapguimcp.models.quick_report_models import ScreenClassification
from sapguimcp.tools.quick_report_tools import classify_result_screen


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

    async def test_easy_access_classified_as_error(self) -> None:
        """Easy Access page (invalid tcode bounce-back) → ERROR, not TABLE."""
        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot="- document 'SAP'\n  - grid 'SAP Menu'",
            screen_title="SAP Easy Access",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR

    async def test_easy_access_takes_priority_over_grid(self) -> None:
        """Easy Access detection runs before grid detection."""
        backend = _make_backend(
            status_type="S",
            status_message="",
            snapshot="- document 'SAP'\n  - grid 'Tree'",
            screen_title="SAP Easy Access S4U (100)",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR

    async def test_empty_kein_job(self) -> None:
        """SM37 'Kein Job entspricht den Selektionsbedingungen' → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="Kein Job entspricht den Selektionsbedingungen",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_empty_no_documents(self) -> None:
        """'No documents found' → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="No documents found for the selection",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_list_screen_detected(self) -> None:
        """Classic SAP list (not ALV grid) should classify as LIST."""
        backend = _make_backend(
            status_type="S",
            status_message="100 Einträge gelesen",
            snapshot="- document 'SAP'\n  - list 'Report Output'\n    - listitem 'Row 1'",
            screen_title="Materialbelegliste",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.LIST

    async def test_grid_takes_priority_over_list(self) -> None:
        """Snapshot with both grid and list → TABLE (grid check runs first)."""
        backend = _make_backend(
            status_type="S",
            status_message="10 Einträge gelesen",
            snapshot="- document 'SAP'\n  - grid 'ALV Grid'\n  - list 'Navigation'",
            screen_title="Report Output",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.TABLE

    async def test_warning_classified_as_error(self) -> None:
        """Status bar type 'W' without empty pattern → ERROR."""
        backend = _make_backend(
            status_type="W",
            status_message="Selektion wurde nicht eingeschränkt",
        )
        classification, status_bar = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR
        assert status_bar.type == "W"

    async def test_warning_with_empty_pattern_still_empty(self) -> None:
        """Warning with empty-data message → EMPTY (empty check runs first)."""
        backend = _make_backend(
            status_type="W",
            status_message="Es wurden keine Werte selektiert",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_selection_screen_with_execute_detected_as_error(self) -> None:
        """Still on selection screen (textbox + Ausführen) → ERROR."""
        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot=(
                "- main 'Materialbelegliste':\n"
                "  - textbox 'Werk'\n"
                "  - textbox 'Material'\n"
                '  - button "Ausführen Hervorgehoben"\n'
            ),
            screen_title="Materialbelegliste",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR

    async def test_selection_screen_without_execute_detected_as_error(self) -> None:
        """Selection screen without Ausführen (e.g. VF05) → ERROR."""
        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot=(
                "- main 'Liste Fakturen':\n"
                "  - textbox 'Regulierer'\n"
                "  - textbox 'Material'\n"
                "  - button 'Anzeigevarianten'\n"
            ),
            screen_title="Liste Fakturen",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR
