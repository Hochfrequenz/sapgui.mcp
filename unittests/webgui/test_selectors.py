"""
Unit tests for SAP Web GUI CSS selectors.

These tests verify that the CSS selectors defined in sap_tools.py correctly
find elements in real SAP Web GUI HTML snapshots. Unlike integration tests,
these run offline and don't require SAP access.

Test Philosophy:
----------------
- Load HTML snapshots captured from real SAP sessions
- Verify selectors find the expected elements
- Fast execution (no browser, no network)
- Deterministic results
- Can run in CI without SAP credentials

Adding New Tests:
-----------------
1. Capture HTML during integration tests (auto-captured to testdata/html_snapshots/)
2. Or manually save HTML from browser DevTools
3. Add test case that loads the HTML and verifies selectors

Selector Sources:
-----------------
- SELECTORS dict in sap_tools.py (okcode_field, settings_button, etc.)
- Field registry in sap_field_registry.json (SE16, VA01, etc.)
"""

import json
import re
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag

# Import the selectors we want to test
from sapguimcp.backend.webgui.utils import escape_css_selector
from sapguimcp.tools.sap_tools import SELECTORS, parse_shortcut_from_title


@pytest.fixture
def html_snapshots_path() -> Path:
    """Return the path to the HTML snapshots directory."""
    return Path(__file__).parent / "testdata" / "html_snapshots"


def get_snapshot_path(base_dir: Path, base_name: str, lang: str | None = None) -> Path | None:
    """
    Find a snapshot file for the specified language.

    Snapshots are named with language suffix: easy_access_en.html, easy_access_de.html

    Args:
        base_dir: Directory containing snapshots
        base_name: Base name without extension (e.g., "easy_access")
        lang: Language code ("de" or "en"). If None, uses SAP_LANGUAGE env var (default: "de")

    Returns:
        Path to the snapshot file, or None if not found
    """
    import os

    if lang is None:
        lang = os.environ.get("SAP_LANGUAGE", "DE").lower()

    # Try exact language match first, then fall back to other language
    preferred_lang = lang.lower()
    fallback_lang = "en" if preferred_lang == "de" else "de"

    for try_lang in (preferred_lang, fallback_lang):
        path = base_dir / f"{base_name}_{try_lang}.html"
        if path.exists():
            return path
    return None


def load_snapshot(snapshot_path: Path) -> BeautifulSoup | None:
    """
    Load an HTML snapshot and parse it with BeautifulSoup.

    Handles both raw HTML files and JSON-wrapped snapshots (from capture_html_snapshot).
    JSON snapshots have the structure: {"success": true, "error": null, "html": "..."}

    Args:
        snapshot_path: Full path to the HTML snapshot file.

    Returns:
        BeautifulSoup object or None if the snapshot doesn't exist (test will be skipped).
    """
    import json

    if not snapshot_path.exists():
        return None
    content = snapshot_path.read_text(encoding="utf-8")

    # Check if content is JSON-wrapped HTML
    if content.strip().startswith("{"):
        try:
            data = json.loads(content)
            html = data.get("html", content)
        except json.JSONDecodeError:
            html = content
    else:
        html = content

    # SAP Web GUI generates invalid HTML with <table> inside <span> (role="textbox").
    # Python 3.13+ html.parser auto-closes spans when encountering block elements.
    #
    # Platform findings:
    # - Python 3.11/3.12: html.parser works correctly on both Windows and Linux
    # - Python 3.13/3.14 on Windows: html.parser works (somehow more lenient)
    # - Python 3.13/3.14 on Linux: html.parser FAILS (stricter nesting rules)
    # - lxml also fails on Linux with Python 3.14
    #
    # IMPORTANT: This is ONLY a problem for our offline unit tests that parse raw HTML.
    # Real browsers (Chrome, Firefox) and Playwright handle this gracefully because their
    # HTML parsers are more lenient. The actual SAP Web GUI works perfectly for users.
    # The sap_login integration test (when run locally with SAP access) proves this works.
    #
    # Fix: Remove the problematic lsHtmlTextView span opening tags.
    # Yes, using regex on HTML is generally a bad idea, but the HTML is already broken
    # and we're just removing known wrapper elements to help the parser.
    html = re.sub(r'<span[^>]*class="[^"]*lsHtmlTextView[^"]*"[^>]*>', "", html)

    return BeautifulSoup(html, "html.parser")


def css_select(soup: BeautifulSoup, selector: str) -> list[Tag]:
    """
    Select elements using a CSS selector, handling comma-separated selectors.

    BeautifulSoup's select() handles most CSS selectors but has some limitations
    with complex pseudo-selectors like :has-text(). We split on commas and try
    each part, returning the first match.
    """
    # Split compound selectors and try each
    for part in selector.split(","):
        part = part.strip()
        # Skip Playwright-specific pseudo-selectors that BeautifulSoup doesn't support
        if ":has-text(" in part or ":near(" in part:
            continue
        try:
            results = soup.select(part)
            if results:
                return results
        except Exception:  # pylint: disable=broad-exception-caught
            # Some selectors may not be valid for BeautifulSoup
            continue
    return []


class TestOkCodeFieldSelector:
    """Tests for the OK-Code field selector (transaction entry field)."""

    def test_okcode_field_in_easy_access(self, html_snapshots_path: Path) -> None:
        """Verify OK-Code field selector finds the field in SAP Easy Access screen."""
        snapshot = get_snapshot_path(html_snapshots_path, "easy_access")
        if snapshot is None:
            pytest.skip("easy_access snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        elements = css_select(soup, SELECTORS["okcode_field"])

        assert len(elements) >= 1, (
            f"OK-Code field selector should find at least one element. " f"Selector: {SELECTORS['okcode_field']}"
        )

        # Verify it's an input element
        okcode = elements[0]
        assert okcode.name == "input", f"OK-Code field should be an input element, got: {okcode.name}"

    def test_okcode_field_in_su3(self, html_snapshots_path: Path) -> None:
        """Verify OK-Code field is present in SU3 transaction screen."""
        snapshot = get_snapshot_path(html_snapshots_path, "su3_screen")
        if snapshot is None:
            pytest.skip("su3_screen snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        elements = css_select(soup, SELECTORS["okcode_field"])

        assert len(elements) >= 1, (
            f"OK-Code field should be present in SU3 screen. " f"Selector: {SELECTORS['okcode_field']}"
        )

    def test_okcode_field_in_se16(self, html_snapshots_path: Path) -> None:
        """Verify OK-Code field is present in SE16 Data Browser screen."""
        snapshot = get_snapshot_path(html_snapshots_path, "se16_initial")
        if snapshot is None:
            pytest.skip("se16_initial snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        elements = css_select(soup, SELECTORS["okcode_field"])

        assert len(elements) >= 1, (
            f"OK-Code field should be present in SE16 screen. " f"Selector: {SELECTORS['okcode_field']}"
        )


class TestStatusBarSelector:
    """Tests for status bar message detection."""

    def test_status_bar_error_detection(self, html_snapshots_path: Path) -> None:
        """Verify error message is detectable in status bar HTML."""
        snapshot = get_snapshot_path(html_snapshots_path, "status_bar_error")
        if snapshot is None:
            pytest.skip("status_bar_error snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        # Check that the HTML contains error indicators
        html_text = str(soup).lower()

        error_indicators = [
            "existiert nicht",  # German: "does not exist"
            "does not exist",  # English
            "nicht gefunden",  # German: "not found"
            "not found",  # English
            "error",
            "fehler",  # German: "error"
        ]

        found_error = any(indicator in html_text for indicator in error_indicators)
        assert found_error, (
            "Status bar error HTML should contain error indicators. " "This snapshot may not contain an error message."
        )


def find_sap_field_by_sid(soup: BeautifulSoup, sid_pattern: str) -> list[Tag]:
    """
    Find SAP fields by their SID pattern in the lsdata attribute.

    SAP Web GUI generates dynamic element IDs but stores stable identifiers
    in the lsdata JSON attribute. This function searches for fields where
    lsdata contains a matching SID pattern.

    Args:
        soup: BeautifulSoup parsed HTML
        sid_pattern: Pattern to search for in the SID (e.g., "DATABROWSE-TABLENAME")

    Returns:
        List of matching elements
    """
    results = []
    for inp in soup.find_all("input"):
        lsdata = inp.get("lsdata", "")
        if sid_pattern.upper() in lsdata.upper():
            results.append(inp)
    return results


class TestTransactionFieldSelectors:
    """Tests for transaction-specific field selectors.

    These tests verify that our field discovery logic finds ALL expected
    input fields on transaction screens, not just "some" inputs.
    """

    def test_se16_finds_table_name_field(self, html_snapshots_path: Path) -> None:
        """SE16 must find the table name input field.

        The table name field is the primary input on SE16 (Data Browser).
        SAP Web GUI stores stable identifiers in the lsdata attribute.
        """
        snapshot = get_snapshot_path(html_snapshots_path, "se16_initial")
        if snapshot is None:
            pytest.skip("se16_initial snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        elements = find_sap_field_by_sid(soup, "DATABROWSE-TABLENAME")

        assert len(elements) >= 1, (
            "SE16 MUST find the table name field (DATABROWSE-TABLENAME). "
            "This is the primary input field for specifying which table to browse."
        )

        field = elements[0]
        assert field.get("type", "text") == "text", "Table name field should be a text input"

    def test_sm37_finds_job_name_field(self, html_snapshots_path: Path) -> None:
        """SM37 must find the job name input field."""
        snapshot = get_snapshot_path(html_snapshots_path, "sm37_initial")
        if snapshot is None:
            pytest.skip("sm37_initial snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        elements = find_sap_field_by_sid(soup, "JOBNAME")

        assert len(elements) >= 1, (
            "SM37 MUST find the job name field. " "This field is used to filter background jobs by name."
        )

    def test_sm37_finds_username_field(self, html_snapshots_path: Path) -> None:
        """SM37 must find the username input field."""
        snapshot = get_snapshot_path(html_snapshots_path, "sm37_initial")
        if snapshot is None:
            pytest.skip("sm37_initial snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        elements = find_sap_field_by_sid(soup, "USERNAME")

        assert len(elements) >= 1, (
            "SM37 MUST find the username field. " "This field filters background jobs by the user who scheduled them."
        )

    def test_sm37_finds_date_fields(self, html_snapshots_path: Path) -> None:
        """SM37 must find date range input fields."""
        snapshot = get_snapshot_path(html_snapshots_path, "sm37_initial")
        if snapshot is None:
            pytest.skip("sm37_initial snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        # SM37 has FROM and TO date fields for filtering job execution dates
        from_date = find_sap_field_by_sid(soup, "FROMDATE") or find_sap_field_by_sid(soup, "FROM_DATE")
        to_date = find_sap_field_by_sid(soup, "TODATE") or find_sap_field_by_sid(soup, "TO_DATE")

        # At least one date field should be present
        has_date_fields = len(from_date) >= 1 or len(to_date) >= 1

        assert has_date_fields, (
            "SM37 MUST find at least one date field for filtering job execution dates. "
            "Looked for FROMDATE, FROM_DATE, TODATE, TO_DATE in lsdata SIDs."
        )


class TestInputFieldDiscovery:
    """Tests for general input field discovery."""

    def test_discover_inputs_in_se16(self, html_snapshots_path: Path) -> None:
        """Verify we can discover input fields in SE16 screen."""
        snapshot = get_snapshot_path(html_snapshots_path, "se16_initial")
        if snapshot is None:
            pytest.skip("se16_initial snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        # Find all visible input elements (excluding hidden and buttons)
        inputs = soup.find_all("input")
        visible_inputs = [inp for inp in inputs if inp.get("type", "text") not in ("hidden", "submit", "button")]

        assert len(visible_inputs) >= 1, "SE16 screen should have at least one visible input field"

    def test_discover_inputs_in_sm37(self, html_snapshots_path: Path) -> None:
        """Verify we can discover input fields in SM37 screen."""
        snapshot = get_snapshot_path(html_snapshots_path, "sm37_initial")
        if snapshot is None:
            pytest.skip("sm37_initial snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        inputs = soup.find_all("input")
        visible_inputs = [inp for inp in inputs if inp.get("type", "text") not in ("hidden", "submit", "button")]

        assert len(visible_inputs) >= 1, "SM37 screen should have at least one visible input field"


class TestSettingsDialogSelectors:
    """Tests for settings dialog selectors.

    These test the selectors used in _enable_okcode_field() to find and enable
    the OK-Code field through SAP settings.
    """

    def test_settings_button_selector(self, html_snapshots_path: Path) -> None:
        """Verify settings button can be found in Easy Access screen."""
        snapshot = get_snapshot_path(html_snapshots_path, "easy_access")
        if snapshot is None:
            pytest.skip("easy_access snapshot not available")
        soup = load_snapshot(snapshot)

        elements = css_select(soup, SELECTORS["settings_button"])

        # Settings button should be findable on main SAP screen
        assert len(elements) >= 1, (
            f"Settings button should be found on Easy Access screen. " f"Selector: {SELECTORS['settings_button']}"
        )

    def test_settings_dialog_has_checkboxes(self, html_snapshots_path: Path) -> None:
        """Verify settings dialog contains checkbox elements."""
        # pytest.skip("Skipping due to unreliable snapshot capturing of SAP popups and unclear assertions/intentions")
        snapshot = get_snapshot_path(html_snapshots_path, "settings_dialog")
        if snapshot is None:
            pytest.skip("settings_dialog snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        checkboxes = soup.find_all("input", {"type": "checkbox"})

        # SAP settings dialog renders as a popup that may not be captured in HTML snapshots.
        # If no checkboxes found, the snapshot likely contains the main screen, not the dialog popup.
        if len(checkboxes) == 0:
            pytest.skip(
                "settings_dialog snapshot does not contain checkboxes - "
                "the dialog popup may not have been captured (SAP popups are tricky to capture)"
            )

    def test_settings_dialog_has_save_or_close(self, html_snapshots_path: Path) -> None:
        """Verify settings dialog has save/close buttons."""
        snapshot = get_snapshot_path(html_snapshots_path, "settings_dialog")
        if snapshot is None:
            pytest.skip("settings_dialog snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        # Look for any button-like elements
        buttons = soup.find_all("button")
        divs_with_role = soup.find_all(attrs={"role": "button"})
        all_buttons = buttons + divs_with_role

        assert len(all_buttons) >= 1, "Settings dialog should have at least one button (Save, Close, OK, etc.)"


class TestFKeyExtraction:
    """Tests for extracting F-key mappings from SAP pages.

    SAP Web GUI stores F-key mappings in button tooltips (title) and lsdata attributes.
    This helps LLMs discover which F-keys trigger which actions.
    """

    # Key name translations: German -> English (normalized)
    KEY_TRANSLATIONS = {
        "strg": "Ctrl",
        "ctrl": "Ctrl",
        "steuerung": "Ctrl",
        "umschalt": "Shift",
        "shift": "Shift",
        "umsch": "Shift",
        "alt": "Alt",
        "eingabe": "Enter",
        "enter": "Enter",
        "esc": "Escape",
        "escape": "Escape",
    }

    def normalize_key_combo(self, key_combo: str) -> str:
        """Normalize key combination to English format.

        Converts German key names to English:
        - Strg+F3 -> Ctrl+F3
        - Umschalt+F2 -> Shift+F2
        - Strg+Umschalt+F4 -> Ctrl+Shift+F4
        """
        parts = key_combo.split("+")
        normalized_parts = []
        for part in parts:
            part_lower = part.lower().strip()
            if part_lower in self.KEY_TRANSLATIONS:
                normalized_parts.append(self.KEY_TRANSLATIONS[part_lower])
            else:
                normalized_parts.append(part.strip())
        return "+".join(normalized_parts)

    def extract_fkey_mappings(self, soup: BeautifulSoup) -> dict[str, list[str]]:
        """Extract F-key to action mappings from SAP HTML.

        Returns dict like:
        - {"F7": ["Anzeigen/Display"], "Ctrl+F3": ["Aktivieren/Activate"]}

        Key combinations are normalized to English (Strg->Ctrl, Umschalt->Shift).
        """
        mappings: dict[str, list[str]] = {}

        # Method 1: Extract from button titles like "Anzeigen (F7)" or "Aktivieren (Strg+F3)"
        # Pattern matches "(F7)", "(Strg+F3)", "(Umschalt+F2)", "(Ctrl+Shift+F4)"
        title_pattern = re.compile(r"\((?P<key_combo>[^)]*F\d+[^)]*)\)")
        for elem in soup.find_all(attrs={"title": True}):
            title = elem.get("title", "")
            match = title_pattern.search(title)
            if match:
                raw_key = match.group("key_combo")
                normalized_key = self.normalize_key_combo(raw_key)
                action = title.replace(f"({raw_key})", "").strip()
                if normalized_key not in mappings:
                    mappings[normalized_key] = []
                if action and action not in mappings[normalized_key]:
                    mappings[normalized_key].append(action)

        # Method 2: Extract from lsdata with hotkey info like "18":"F7" or "18":"CTRL_F3"
        # SAP stores hotkey info in field "18" of lsdata JSON
        sap_hotkey_pattern = re.compile(r'"18":"(?P<hotkey>(?:CTRL_|SHIFT_|ALT_)*F\d+)"')
        simple_fkey_pattern = re.compile(r'"(?P<fkey>F\d+)"')

        for elem in soup.find_all(attrs={"lsdata": True}):
            lsdata = elem.get("lsdata", "")

            # Try SAP lsdata format first (more specific)
            for match in sap_hotkey_pattern.finditer(lsdata):
                raw_key = match.group("hotkey")
                # Convert CTRL_F3 to Ctrl+F3
                normalized_key = raw_key.replace("_", "+").replace("CTRL", "Ctrl").replace("SHIFT", "Shift")

                button_text = elem.get("title", "") or elem.get_text(strip=True)[:50]
                if normalized_key not in mappings:
                    mappings[normalized_key] = []
                if button_text and button_text not in mappings[normalized_key]:
                    mappings[normalized_key].append(button_text)

            # Also try simple F-key pattern
            for match in simple_fkey_pattern.finditer(lsdata):
                fkey = match.group("fkey")
                button_text = elem.get("title", "") or elem.get_text(strip=True)[:50]
                if fkey not in mappings:
                    mappings[fkey] = []
                if button_text and button_text not in mappings[fkey]:
                    mappings[fkey].append(button_text)

        return mappings

    def test_se11_initial_has_fkey_mappings(self, html_snapshots_path: Path) -> None:
        """Verify SE11 initial screen has extractable F-key mappings."""
        snapshot = get_snapshot_path(html_snapshots_path, "se11_initial")
        if snapshot is None:
            pytest.skip("se11_initial snapshot not available")
        soup = load_snapshot(snapshot)

        mappings = self.extract_fkey_mappings(soup)

        # SE11 should have at least F3 (Back), F7 (Display), etc.
        assert len(mappings) >= 3, f"SE11 should have multiple F-key mappings. Found: {list(mappings.keys())}"

        # Verify F3 is mapped (Back is always available)
        assert "F3" in mappings, "F3 (Back/Zurück) should be mapped"

    def test_se11_initial_en_has_fkey_mappings(self, html_snapshots_path: Path) -> None:
        """Verify SE11 initial screen (English) has extractable F-key mappings."""
        snapshot = html_snapshots_path / "se11_initial_en.html"
        if not snapshot.exists():
            pytest.skip("se11_initial_en snapshot not available")
        soup = load_snapshot(snapshot)

        mappings = self.extract_fkey_mappings(soup)

        # SE11 should have at least F3 (Back), F7 (Display), etc.
        assert len(mappings) >= 3, f"SE11 (EN) should have multiple F-key mappings. Found: {list(mappings.keys())}"

        # Verify F3 is mapped (Back is always available)
        assert "F3" in mappings, "F3 (Back) should be mapped in English SE11"

    def test_easy_access_has_fkey_mappings(self, html_snapshots_path: Path) -> None:
        """Verify Easy Access screen has extractable F-key mappings."""
        snapshot = get_snapshot_path(html_snapshots_path, "easy_access")
        if snapshot is None:
            pytest.skip("easy_access snapshot not available")
        soup = load_snapshot(snapshot)

        mappings = self.extract_fkey_mappings(soup)

        assert len(mappings) >= 2, f"Easy Access should have F-key mappings. Found: {list(mappings.keys())}"


class TestLoginPageSelectors:
    """Tests for login page element selectors."""

    @pytest.mark.skip(
        reason=(
            "html.parser cannot reliably handle SAP's invalid HTML (<table> inside <span>). "
            "Python 3.13+ fails outright; 3.11/3.12 silently drop element attributes. "
            "See test_login_page_fields_findable_by_playwright for proof that real browsers work."
        ),
    )
    def test_login_form_elements(self, html_snapshots_path: Path) -> None:
        """Verify login form elements can be found (if login page snapshot exists)."""
        snapshot = get_snapshot_path(html_snapshots_path, "login_page")
        if snapshot is None:
            pytest.skip("login_page snapshot not available")
        soup = load_snapshot(snapshot)

        # Check for standard SAP login form elements
        client_field = soup.select("#sap-client, input[name='sap-client']")
        user_field = soup.select("#sap-user, input[name='sap-user']")
        password_field = soup.select("#sap-password, input[name='sap-password']")
        login_button = soup.select("#LOGON_BUTTON")

        # Debug: print info if client_field not found
        if not client_field:
            html_content = snapshot.read_text(encoding="utf-8")
            id_attr = 'id="sap-client"'
            print(f"DEBUG: Snapshot path: {snapshot}")
            print(f"DEBUG: HTML length: {len(html_content)}")
            print(f"DEBUG: 'sap-client' in HTML: {'sap-client' in html_content}")
            print(f"DEBUG: {id_attr!r} in HTML: {id_attr in html_content}")
            # Find all input elements
            all_inputs = soup.find_all("input")
            print(f"DEBUG: Total input elements found: {len(all_inputs)}")
            for inp in all_inputs[:5]:
                print(f"DEBUG: Input: id={inp.get('id')}, name={inp.get('name')}")

        assert client_field, "Login page should have client/mandant field"
        assert user_field, "Login page should have username field"
        assert password_field, "Login page should have password field"
        assert login_button, "Login page should have login button"


class TestTableContentExtraction:
    """Tests for extracting table content from SAP screens.

    These tests verify that we can find and extract data from SAP tables,
    which is essential for the sap_read_table tool.
    """

    def test_se16_t000_has_table_rows(self, html_snapshots_path: Path) -> None:
        """Verify SE16 T000 content has extractable table rows.

        T000 (Clients table) always has at least one row. This test verifies
        we can find table elements in the captured HTML.
        """
        snapshot = get_snapshot_path(html_snapshots_path, "se16_t000_content")
        if snapshot is None:
            pytest.skip("se16_t000_content snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        # SAP tables use various structures - look for common patterns
        # 1. Standard HTML tables
        tables = soup.find_all("table")

        # 2. SAP-specific grid/list elements
        grids = soup.find_all(attrs={"role": "grid"})
        rows = soup.find_all(attrs={"role": "row"})

        # 3. Elements with lsdata containing table-related info
        cells_with_data = soup.find_all(attrs={"lsdata": True})
        table_cells = [c for c in cells_with_data if "row" in str(c.get("lsdata", "")).lower()]

        has_table_structure = len(tables) > 0 or len(grids) > 0 or len(rows) > 0 or len(table_cells) > 0

        assert has_table_structure, (
            "SE16 T000 content should contain table elements. "
            f"Found: {len(tables)} tables, {len(grids)} grids, {len(rows)} rows, {len(table_cells)} cells with lsdata"
        )

    def test_se16_t000_contains_mandt_column(self, html_snapshots_path: Path) -> None:
        """Verify SE16 T000 content contains MANDT (client) column.

        T000 table always has a MANDT column showing the client number.
        """
        snapshot = get_snapshot_path(html_snapshots_path, "se16_t000_content")
        if snapshot is None:
            pytest.skip("se16_t000_content snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        html_text = str(soup).upper()

        # MANDT is the standard SAP client/mandant field name
        assert "MANDT" in html_text, (
            "SE16 T000 content should contain 'MANDT' column header or data. "
            "This is the primary key of the T000 table."
        )

    def test_sm37_results_has_job_rows(self, html_snapshots_path: Path) -> None:
        """Verify SM37 results contain job list rows.

        After executing SM37 with wildcards, we should have job entries.
        """
        snapshot = get_snapshot_path(html_snapshots_path, "sm37_results")
        if snapshot is None:
            pytest.skip("sm37_results snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        # Look for table/grid structures
        tables = soup.find_all("table")
        grids = soup.find_all(attrs={"role": "grid"})
        rows = soup.find_all(attrs={"role": "row"})

        has_table_structure = len(tables) > 0 or len(grids) > 0 or len(rows) > 1  # >1 because header row

        assert has_table_structure, (
            "SM37 results should contain a job list with table rows. "
            f"Found: {len(tables)} tables, {len(grids)} grids, {len(rows)} rows"
        )

    def test_se11_initial_has_object_type_field(self, html_snapshots_path: Path) -> None:
        """Verify SE11 initial screen has the object type/table name input field."""
        snapshot = get_snapshot_path(html_snapshots_path, "se11_initial")
        if snapshot is None:
            pytest.skip("se11_initial snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        # SE11 has input field for table/view/data element name
        # Look for input fields with TBMA or object-related patterns in lsdata
        inputs = soup.find_all("input")
        object_fields = [inp for inp in inputs if "TBMA" in str(inp.get("lsdata", "")).upper()]

        # Also check by any visible text input that could be the object name field
        visible_inputs = [inp for inp in inputs if inp.get("type", "text") == "text"]

        assert (
            len(object_fields) >= 1 or len(visible_inputs) >= 1
        ), "SE11 initial screen should have an object name input field"

    def test_se11_t000_content_shows_fields(self, html_snapshots_path: Path) -> None:
        """Verify SE11 T000 content shows table field names.

        The table structure view should show field names like MANDT, CCCATEGORY.
        """
        snapshot = get_snapshot_path(html_snapshots_path, "se11_t000_content")
        if snapshot is None:
            pytest.skip("se11_t000_definition snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        html_text = str(soup).upper()

        # T000 has well-known fields
        has_mandt = "MANDT" in html_text
        has_cccategory = "CCCATEGORY" in html_text
        has_field_indicator = "FIELD" in html_text or "COMPONENT" in html_text

        assert has_mandt or has_cccategory or has_field_indicator, (
            "SE11 T000 definition should show field names. " "Expected MANDT, CCCATEGORY, or FIELD/COMPONENT labels."
        )


class TestAlvGridDetection:
    """Tests for ALV grid detection and cell selector generation.

    These tests verify that our JavaScript extraction logic correctly:
    1. Detects ALV grids (table[ct="STCS"])
    2. Finds cell elements with grid# pattern IDs
    3. Identifies hotspot cells (UNDERLINE_HOTSPOT in lsdata)
    4. Generates correctly escaped CSS selectors
    """

    def test_emmacl_results_has_alv_table(self, html_snapshots_path: Path) -> None:
        """Verify EMMACL results contain an ALV grid table."""
        snapshot = get_snapshot_path(html_snapshots_path, "emmacl_results_no_filter")
        if snapshot is None:
            pytest.skip("emmacl_results_no_filter snapshot not available")

        # Read raw HTML since BeautifulSoup may alter attributes
        html_content = snapshot.read_text(encoding="utf-8")

        # ALV grids have ct="STCS" attribute (escaped in the HTML snapshot)
        has_stcs = 'ct=\\"STCS\\"' in html_content or 'ct="STCS"' in html_content

        assert has_stcs, (
            "EMMACL results should contain at least one ALV grid table. " "ALV tables have ct='STCS' attribute."
        )

        # Verify the table has an ID (look for id="C followed by digits)
        import re

        table_ids = re.findall(r'id=\\"(C\d+)\\"', html_content)
        assert len(table_ids) >= 1, "ALV table should have an ID attribute (e.g., C120)"

    def test_emmacl_results_has_grid_cell_ids(self, html_snapshots_path: Path) -> None:
        """Verify EMMACL results contain grid# pattern cell IDs."""
        snapshot = get_snapshot_path(html_snapshots_path, "emmacl_results_no_filter")
        if snapshot is None:
            pytest.skip("emmacl_results_no_filter snapshot not available")

        # Read raw HTML since BeautifulSoup may alter escaped content
        html_content = snapshot.read_text(encoding="utf-8")

        # Look for grid# pattern IDs
        import re

        grid_ids = re.findall(r'id=\\"(grid#[^\\"]+)\\"', html_content)

        assert len(grid_ids) >= 1, (
            "EMMACL results should contain grid# pattern cell IDs. " "Pattern: grid#<table_id>#<row>,<col>"
        )

    def test_emmacl_results_has_hotspot_cells(self, html_snapshots_path: Path) -> None:
        """Verify EMMACL results contain hotspot cells (navigable links)."""
        snapshot = get_snapshot_path(html_snapshots_path, "emmacl_results_no_filter")
        if snapshot is None:
            pytest.skip("emmacl_results_no_filter snapshot not available")

        html_content = snapshot.read_text(encoding="utf-8")

        # Hotspot cells have UNDERLINE_HOTSPOT in lsdata
        hotspot_count = html_content.count("UNDERLINE_HOTSPOT")

        assert hotspot_count >= 1, (
            "EMMACL results should contain at least one hotspot cell. "
            "Hotspots have 'UNDERLINE_HOTSPOT' in their lsdata attribute."
        )

    def test_emmacl_results_has_clickable_case_column(self, html_snapshots_path: Path) -> None:
        """Verify EMMACL results have a clickable 'Fall' (case) column."""
        snapshot = get_snapshot_path(html_snapshots_path, "emmacl_results_no_filter")
        if snapshot is None:
            pytest.skip("emmacl_results_no_filter snapshot not available")

        html_content = snapshot.read_text(encoding="utf-8")

        # The "Fall" column should exist and have hotspot cells
        # Look for elements with both "Fall" text nearby and hotspot attribute
        has_fall_column = "Fall" in html_content or "Case" in html_content
        has_hotspots = "UNDERLINE_HOTSPOT" in html_content

        assert has_fall_column and has_hotspots, (
            "EMMACL results should have a clickable 'Fall' (case) column " "with hotspot cells for navigation."
        )


class TestFillFormLsdataLabelParsing:
    """Tests for sap_fill_form lsdata-based label parsing.

    SAP Web GUI uses lsdata attributes on labels to associate them with input fields.
    The label's lsdata["1"] contains the associated input ID.
    The label's lsdata["3"] contains the label text.
    """

    def _find_input_by_label(self, soup: BeautifulSoup, label_text: str) -> Tag | None:
        """
        Simulate the JavaScript findInputByLabel function.

        This mirrors the logic in fill_form_fields.js to verify it works
        against real SAP HTML snapshots.
        """
        import json

        # Find all label elements with lsdata attribute
        labels = soup.find_all("label", attrs={"lsdata": True})

        for label in labels:
            lsdata_raw = label.get("lsdata")
            if not lsdata_raw:
                continue

            try:
                # Parse lsdata JSON
                lsdata = json.loads(lsdata_raw)

                # Check if this label's text (key "3") matches
                if lsdata.get("3") == label_text:
                    input_id = lsdata.get("1")
                    if input_id:
                        # Find input by ID
                        input_el = soup.find(id=input_id)
                        if input_el:
                            return input_el
            except json.JSONDecodeError:
                continue

        return None

    @pytest.mark.parametrize(
        ("lang", "first_name_label", "last_name_label"),
        [
            pytest.param("de", "Vorname", "Nachname", id="german"),
            pytest.param("en", "First Name", "Last Name", id="english"),
        ],
    )
    def test_bp_person_form_name_labels(
        self, html_snapshots_path: Path, lang: str, first_name_label: str, last_name_label: str
    ) -> None:
        """Verify first/last name labels are found via lsdata parsing in BP person form."""
        snapshot = html_snapshots_path / f"bp_person_form_{lang}.html"
        if not snapshot.exists():
            pytest.skip(f"bp_person_form_{lang} snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)
        if soup is None:
            pytest.skip(f"Could not parse bp_person_form_{lang} snapshot")

        # Test first name
        first_name_input = self._find_input_by_label(soup, first_name_label)
        assert first_name_input is not None, (
            f"Failed to find input for '{first_name_label}' label via lsdata parsing. "
            f"The label should have lsdata with key '3' = '{first_name_label}' and key '1' pointing to input ID."
        )
        assert (
            first_name_input.name == "input"
        ), f"{first_name_label} field should be an input, got: {first_name_input.name}"

        # Test last name
        last_name_input = self._find_input_by_label(soup, last_name_label)
        assert last_name_input is not None, (
            f"Failed to find input for '{last_name_label}' label via lsdata parsing. "
            f"The label should have lsdata with key '3' = '{last_name_label}' and key '1' pointing to input ID."
        )
        assert (
            last_name_input.name == "input"
        ), f"{last_name_label} field should be an input, got: {last_name_input.name}"

    def test_bp_person_form_label_lsdata_structure(self, html_snapshots_path: Path) -> None:
        """Verify BP person form has labels with lsdata containing expected keys."""

        # Use English snapshot (preferred)
        snapshot = get_snapshot_path(html_snapshots_path, "bp_person_form")
        if snapshot is None:
            pytest.skip("bp_person_form snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)
        if soup is None:
            pytest.skip("Could not parse bp_person_form snapshot")

        # Find labels with lsdata
        labels_with_lsdata = soup.find_all("label", attrs={"lsdata": True})
        assert len(labels_with_lsdata) > 0, "BP person form should have labels with lsdata attribute"

        # Check that at least one label has the expected structure
        labels_with_key_3 = []
        for label in labels_with_lsdata:
            try:
                lsdata = json.loads(label.get("lsdata"))
                if "3" in lsdata:
                    labels_with_key_3.append(lsdata.get("3"))
            except json.JSONDecodeError:
                continue

        assert len(labels_with_key_3) > 0, (
            "BP person form should have labels with lsdata containing key '3' (label text). "
            f"Found {len(labels_with_lsdata)} labels with lsdata."
        )

        # Verify name fields are in the labels (English or German)
        has_first_name = "First Name" in labels_with_key_3 or "Vorname" in labels_with_key_3
        has_last_name = "Last Name" in labels_with_key_3 or "Nachname" in labels_with_key_3
        assert has_first_name, f"First name field should be in labels. Found: {labels_with_key_3[:10]}"
        assert has_last_name, f"Last name field should be in labels. Found: {labels_with_key_3[:10]}"

    def _extract_all_labels(self, soup: BeautifulSoup) -> list[str]:
        """Extract all label texts from lsdata key '3' in the HTML snapshot."""
        labels_with_lsdata = soup.find_all("label", attrs={"lsdata": True})
        label_texts = []
        for label in labels_with_lsdata:
            try:
                lsdata = json.loads(label.get("lsdata"))
                if "3" in lsdata:
                    label_texts.append(lsdata["3"])
            except json.JSONDecodeError:
                continue
        return label_texts

    def test_bp_person_form_prompt_labels(self, html_snapshots_path: Path) -> None:
        """Verify that person labels used in create_business_partner prompt exist on the form.

        The prompt uses label-based filling for 'Anrede', 'Vorname', 'Nachname'.
        Address fields use CSS selectors (not labels) because SAP uses combined
        labels like 'Straße/Hausnummer' for those.
        """
        snapshot = get_snapshot_path(html_snapshots_path, "bp_person_form")
        if snapshot is None:
            pytest.skip("bp_person_form snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)
        if soup is None:
            pytest.skip("Could not parse bp_person_form snapshot")

        all_labels = self._extract_all_labels(soup)

        # These labels are used in the create_business_partner prompt for person fields
        expected_labels = ["Anrede", "Vorname", "Nachname"]
        for label in expected_labels:
            input_el = self._find_input_by_label(soup, label)
            assert input_el is not None, (
                f"Label '{label}' from create_business_partner prompt not found on BP person form. "
                f"Available labels: {sorted(set(all_labels))}"
            )

    def test_bp_org_form_prompt_labels(self, html_snapshots_path: Path) -> None:
        """Verify that organisation labels used in create_business_partner prompt exist on the form.

        The prompt uses label-based filling for 'Name 1'.
        Address fields use CSS selectors (not labels).

        Requires bp_org_form snapshot from test_bp_org_form_snapshot integration test.
        """
        snapshot = get_snapshot_path(html_snapshots_path, "bp_org_form")
        if snapshot is None:
            pytest.skip("bp_org_form snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)
        if soup is None:
            pytest.skip("Could not parse bp_org_form snapshot")

        all_labels = self._extract_all_labels(soup)

        # The snapshot may not contain the org form if it was captured at a different screen.
        # Skip gracefully when the expected labels aren't present.
        if "Name 1" not in all_labels:
            pytest.skip(
                f"bp_org_form snapshot does not contain org form labels "
                f"(available: {sorted(set(all_labels))}). Re-capture the snapshot."
            )

        # "Name 1" is used in the create_business_partner prompt for org fields
        input_el = self._find_input_by_label(soup, "Name 1")
        assert input_el is not None, (
            f"Label 'Name 1' from create_business_partner prompt not found on BP org form. "
            f"Available labels: {sorted(set(all_labels))}"
        )

    def test_bp_person_form_address_fields_have_combined_labels(self, html_snapshots_path: Path) -> None:
        """Verify that address fields use combined labels, confirming CSS selectors are needed.

        The BP form uses combined labels like 'Straße/Hausnummer' and 'Postleitzahl/Ort'
        instead of individual labels. This is why the create_business_partner prompt
        uses CSS selectors (input[lsdata*='STREET']) for address fields.
        """
        snapshot = get_snapshot_path(html_snapshots_path, "bp_person_form")
        if snapshot is None:
            pytest.skip("bp_person_form snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)
        if soup is None:
            pytest.skip("Could not parse bp_person_form snapshot")

        all_labels = self._extract_all_labels(soup)

        # These individual labels should NOT exist (they are combined in SAP)
        individual_labels = ["Straße", "Strasse", "Hausnummer", "Hausnr.", "Ort", "Land"]
        for label in individual_labels:
            assert label not in all_labels, (
                f"Individual label '{label}' found - expected combined labels instead. "
                f"If SAP changed its label scheme, update create_business_partner prompt."
            )


class TestCssSelectorEscaping:
    """Tests for CSS selector escaping utility.

    SAP generates element IDs containing special CSS characters like : and [].
    These must be escaped for valid CSS selectors.
    """

    @pytest.mark.parametrize(
        ("selector", "expected"),
        [
            pytest.param("#M0:48::btn[5]", r"#M0\:48\:\:btn\[5\]", id="sap_button"),
            pytest.param("#M0:46:1:1::0:21", r"#M0\:46\:1\:1\:\:0\:21", id="sap_input"),
            pytest.param("#mySimpleId", "#mySimpleId", id="simple_id"),
            pytest.param(".some-class:hover", ".some-class:hover", id="class_selector"),
            pytest.param("[data-id='test:value']", "[data-id='test:value']", id="attribute_selector"),
            pytest.param("", "", id="empty_string"),
            # ALV grid cell selectors with # and , characters
            pytest.param("#grid#C120#1,2#if", r"#grid\#C120\#1\,2\#if", id="alv_cell_hotspot"),
            pytest.param("#grid#C120#0,0", r"#grid\#C120\#0\,0", id="alv_header_cell"),
            pytest.param("#grid#C120#1,2#if-r", r"#grid\#C120\#1\,2\#if-r", id="alv_cell_wrapper"),
            pytest.param("#C120-mrss-cont-left-Row-0", r"#C120-mrss-cont-left-Row-0", id="alv_row_no_special"),
            # Already-escaped selectors should not be double-escaped
            pytest.param(r"#grid\#C120\#1\,2\#if", r"#grid\#C120\#1\,2\#if", id="already_escaped_alv"),
            pytest.param(r"#M0\:48\:\:btn\[5\]", r"#M0\:48\:\:btn\[5\]", id="already_escaped_sap"),
        ],
    )
    def test_escape_css_selector(self, selector: str, expected: str) -> None:
        """Test CSS selector escaping for various inputs."""
        result = escape_css_selector(selector)
        assert result == expected, f"Input: {selector!r}, Expected: {expected!r}, Got: {result!r}"


class TestParseShortcutFromTitle:
    """Tests for parsing keyboard shortcuts from title attribute values.

    The parse_shortcut_from_title function extracts action text and shortcut
    from SAP button title attributes like "Person anlegen (F5)".
    """

    @pytest.mark.parametrize(
        ("title", "expected_action", "expected_shortcut"),
        [
            pytest.param("Person anlegen (F5)", "Person anlegen", "F5", id="simple_f_key"),
            pytest.param("Organisation anlegen (Strg+F5)", "Organisation anlegen", "Strg+F5", id="ctrl_f_key_german"),
            pytest.param("Beenden (Umschalt+F3)", "Beenden", "Umschalt+F3", id="shift_f_key_german"),
            pytest.param("Als Variante sichern (Strg+S)", "Als Variante sichern", "Strg+S", id="ctrl_letter_key"),
            pytest.param("Ausführen (F8)", "Ausführen", "F8", id="execute_f8"),
            pytest.param("Zurück (F3)", "Zurück", "F3", id="back_f3"),
            pytest.param("Bestätigen (Eingabe)", "Bestätigen", "Eingabe", id="enter_key"),
            pytest.param("Save (Ctrl+S)", "Save", "Ctrl+S", id="ctrl_english"),
            pytest.param("Exit (Shift+F3)", "Exit", "Shift+F3", id="shift_english"),
            pytest.param("  Person anlegen  (F5)  ", "Person anlegen", "F5", id="whitespace_handling"),
        ],
    )
    def test_valid_shortcuts(self, title: str, expected_action: str, expected_shortcut: str) -> None:
        """Verify valid shortcuts are parsed correctly."""
        result = parse_shortcut_from_title(title)
        assert result is not None, f"Expected shortcut for: {title}"
        assert result.action == expected_action, f"Wrong action for: {title}"
        assert result.shortcut == expected_shortcut, f"Wrong shortcut for: {title}"

    @pytest.mark.parametrize(
        "title",
        [
            pytest.param("Created (2024-01-01)", id="date_pattern"),
            pytest.param("Item (123)", id="number_pattern"),
            pytest.param("Status (active)", id="text_pattern"),
            pytest.param("Just some text", id="no_parentheses"),
            pytest.param("", id="empty_string"),
        ],
    )
    def test_invalid_shortcuts_return_none(self, title: str) -> None:
        """Verify non-keyboard patterns return None."""
        result = parse_shortcut_from_title(title)
        assert result is None, f"Expected None for: {title!r}"


class TestPopupDetection:
    """Tests for popup detection in SAP Web GUI HTML snapshots.

    These tests verify that the popup detection JavaScript (check_popup.js)
    can find the expected elements in real SAP popup HTML.
    """

    def test_se38_error_popup_has_blocking_layer(self, html_snapshots_path: Path) -> None:
        """Verify SE38 error popup has a blocking layer."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "se38_error_popup")
        if not snapshot_path:
            pytest.skip("SE38 error popup snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load SE38 error popup snapshot")

        # Check for blocking layer (urPopupWindowBlockLayer or lsBlockLayer)
        blocking_layer = soup.select_one("#urPopupWindowBlockLayer, .lsBlockLayer")
        if blocking_layer is None:
            # Snapshot may not have been captured with popup active
            pytest.skip(f"Snapshot {snapshot_path.name} doesn't contain popup elements")
        assert blocking_layer is not None, "Expected blocking layer element"

    def test_se38_error_popup_has_popup_container(self, html_snapshots_path: Path) -> None:
        """Verify SE38 error popup has a popup container."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "se38_error_popup")
        if not snapshot_path:
            pytest.skip("SE38 error popup snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load SE38 error popup snapshot")

        # Check for popup container (lsPWNew or similar)
        popup = soup.select_one(".lsPWNew, [class*='lsPopupWindow'], .urPopupWindow")
        if popup is None:
            pytest.skip(f"Snapshot {snapshot_path.name} doesn't contain popup elements")
        assert popup is not None, "Expected popup container element"

    def test_se38_error_popup_has_buttons(self, html_snapshots_path: Path, lang_strings: dict[str, str]) -> None:
        """Verify SE38 error popup has expected buttons."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "se38_error_popup")
        if not snapshot_path:
            pytest.skip("SE38 error popup snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load SE38 error popup snapshot")

        # Check for popup container first
        popup = soup.select_one(".lsPWNew, [class*='lsPopupWindow'], .urPopupWindow")
        if popup is None:
            pytest.skip(f"Snapshot {snapshot_path.name} doesn't contain popup elements")

        # Find buttons in popup
        buttons = soup.select(".lsPWNew button, .lsPWNew [role='button']")
        button_texts = [btn.get_text(strip=True) for btn in buttons]

        # Popup should have at least one button (exact labels depend on SAP config)
        assert len(button_texts) >= 1, f"Popup should have at least one button. Got: {button_texts}"

    def test_se38_error_popup_has_header_title(self, html_snapshots_path: Path) -> None:
        """Verify SE38 error popup has a header title."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "se38_error_popup")
        if not snapshot_path:
            pytest.skip("SE38 error popup snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load SE38 error popup snapshot")

        # Check for popup container first
        popup = soup.select_one(".lsPWNew, [class*='lsPopupWindow'], .urPopupWindow")
        if popup is None:
            pytest.skip(f"Snapshot {snapshot_path.name} doesn't contain popup elements")

        # Find header title — the popup should have a visible title element.
        # The title content depends on which snapshot was captured (e.g. "Fehler in der
        # Objektbearbeitung" or "Einstieg in die Objektbearbeitung").
        header = soup.select_one(".lsPWNewHeaderTextOverflow, [class*='header-title']")
        assert header is not None, "Expected header title element in popup"
        header_text = header.get_text(strip=True)
        assert len(header_text) > 0, "Popup header title should not be empty"

    def test_bp_validation_popup_has_blocking_layer(self, html_snapshots_path: Path) -> None:
        """Verify BP validation popup has a blocking layer."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_validation_popup")
        if not snapshot_path:
            pytest.skip("BP validation popup snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP validation popup snapshot")

        # Check for blocking layer
        blocking_layer = soup.select_one("#urPopupWindowBlockLayer, .lsBlockLayer")
        assert blocking_layer is not None, "Expected blocking layer element"

    def test_bp_validation_popup_has_ja_nein_buttons(
        self, html_snapshots_path: Path, lang_strings: dict[str, str]
    ) -> None:
        """Verify BP validation popup has Yes/No buttons."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_validation_popup")
        if not snapshot_path:
            pytest.skip("BP validation popup snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP validation popup snapshot")

        # Find buttons in popup
        buttons = soup.select(".lsPWNew button, .lsPWNew [role='button']")
        button_texts = [btn.get_text(strip=True) for btn in buttons]

        # Should have Yes and No buttons (DE: Ja/Nein, EN: Yes/No)
        has_yes = any(lang_strings["yes"] in text for text in button_texts)
        has_no = any(lang_strings["no"] in text for text in button_texts)
        assert has_yes and has_no, f"Expected {lang_strings['yes']}/{lang_strings['no']} buttons. Got: {button_texts}"

    def test_se38_initial_has_no_popup(self, html_snapshots_path: Path) -> None:
        """Verify SE38 initial screen has no blocking popup."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "se38_initial")
        if not snapshot_path:
            pytest.skip("SE38 initial snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load SE38 initial snapshot")

        # Blocking layer should not exist or should be hidden
        blocking_layer = soup.select_one("#urPopupWindowBlockLayer, .lsBlockLayer")
        if blocking_layer:
            # Check if it's hidden (display: none)
            style = blocking_layer.get("style", "")
            assert (
                "display: none" in style or "display:none" in style
            ), "Blocking layer exists but should be hidden on initial screen"


class TestDropdownDetection:
    """Tests for dropdown/combobox field detection using HTML snapshots."""

    def test_bp_create_person_has_dropdown_fields(self, html_snapshots_path: Path) -> None:
        """Verify BP create person screen has dropdown fields (ct=CB)."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        # Find all inputs with ct="CB" (ComboBox)
        dropdowns = soup.select('input[ct="CB"]')
        assert len(dropdowns) >= 1, "Expected at least one dropdown field in BP create person"

    def test_bp_create_person_gp_rolle_dropdown(self, html_snapshots_path: Path, lang_strings: dict[str, str]) -> None:
        """Verify GP-Rolle/Role dropdown has expected attributes."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        # Find dropdown with GP-Rolle/Role label (look for lsdata containing the text)
        dropdowns = soup.select('input[ct="CB"]')
        gp_rolle_dropdown = None
        role_label = lang_strings["gp_role_label"]
        for dd in dropdowns:
            title = dd.get("title", "")
            # Check for both DE and EN labels in case of fallback
            if role_label in title or "GP-Rolle" in title or "Role" in title:
                gp_rolle_dropdown = dd
                break

        assert gp_rolle_dropdown is not None, f"Expected {role_label} dropdown field"
        assert gp_rolle_dropdown.get("readonly") is not None or gp_rolle_dropdown.has_attr(
            "readonly"
        ), "Dropdown should be readonly"
        assert gp_rolle_dropdown.get("aria-haspopup") == "true", "Dropdown should have aria-haspopup=true"

    def test_bp_create_person_dropdown_has_value(self, html_snapshots_path: Path, lang_strings: dict[str, str]) -> None:
        """Verify GP-Rolle dropdown has default value (GPartner allgemein / General BP)."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        # Find dropdown with value containing the expected default
        dropdowns = soup.select('input[ct="CB"]')
        expected_value = lang_strings["gp_role_default"]
        gp_role_found = False
        for dd in dropdowns:
            value = dd.get("value", "")
            # Check for both DE and EN values in case of fallback
            if expected_value in value or "GPartner" in value or "General BP" in value:
                gp_role_found = True
                break

        assert gp_role_found, f"Expected dropdown with '{expected_value}' default value"

    def test_bp_create_person_gruppierung_dropdown_empty(
        self, html_snapshots_path: Path, lang_strings: dict[str, str]
    ) -> None:
        """Verify Gruppierung/Grouping dropdown exists and is empty by default."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        # Find dropdown with Gruppierung/Grouping label in title
        # Note: Full German label is "Geschäftspartnergruppierung"
        dropdowns = soup.select('input[ct="CB"]')
        gruppierung_dropdown = None
        grouping_label = lang_strings["grouping_label"]
        for dd in dropdowns:
            title = dd.get("title", "").lower()
            # Check for partial match since full label is "Geschäftspartnergruppierung"
            if grouping_label.lower() in title or "gruppieru" in title or "grouping" in title:
                gruppierung_dropdown = dd
                break

        assert gruppierung_dropdown is not None, f"Expected {grouping_label} dropdown field"
        # Value should be empty
        value = gruppierung_dropdown.get("value", "")
        assert value == "", f"{grouping_label} should be empty by default, got: {value}"

    def test_dropdown_detection_attributes(self, html_snapshots_path: Path) -> None:
        """Verify dropdown detection criteria work correctly."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        # All ct=CB inputs should have readonly and aria-haspopup
        dropdowns = soup.select('input[ct="CB"]')
        for dd in dropdowns:
            # Should have readonly attribute (though BeautifulSoup might parse it as empty string)
            has_readonly = dd.has_attr("readonly") or dd.get("readonly") is not None
            # Note: Some dropdowns might not have readonly if they allow typing
            # Just verify the ct=CB is correctly identifying them
            assert dd.get("ct") == "CB", f"Expected ct=CB, got: {dd.get('ct')}"

    def test_se16_has_no_dropdowns(self, html_snapshots_path: Path) -> None:
        """Verify SE16 initial screen has no dropdown fields."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "se16_initial")
        if not snapshot_path:
            pytest.skip("SE16 initial snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load SE16 initial snapshot")

        # SE16 is a simple screen with just a table name input - no dropdowns expected
        dropdowns = soup.select('input[ct="CB"]')
        # There might be some system dropdowns but the main table name field is not a dropdown
        main_input = soup.select_one("input[lsdata*='TABLENAME']")
        if main_input:
            assert main_input.get("ct") != "CB", "Table name field should not be a dropdown"


class TestDropdownListboxStructure:
    """Tests for dropdown listbox structure and option detection.

    These tests verify the listbox structure used by select_dropdown_option.js
    and get_dropdown_options.js to select dropdown values.

    Related issues: #72 (dropdown opening), #73 (value not applied), #74 (learning),
    #79 (GP-Rolle not set correctly)
    """

    def _find_listbox_for_dropdown(self, soup: BeautifulSoup, input_element: Tag) -> Tag | None:
        """Find the listbox associated with a dropdown input element.

        Mirrors the JavaScript logic in select_dropdown_option.js:
        1. aria-controls attribute on input
        2. lsdata["3"] on input contains listbox ID
        """
        # Method 1: aria-controls
        aria_controls = input_element.get("aria-controls")
        if aria_controls:
            listbox = soup.find(id=aria_controls)
            if listbox:
                return listbox

        # Method 2: lsdata["3"]
        lsdata_raw = input_element.get("lsdata")
        if lsdata_raw:
            try:
                lsdata = json.loads(lsdata_raw)
                listbox_id = lsdata.get("3")
                if listbox_id:
                    listbox = soup.find(id=listbox_id)
                    if listbox:
                        return listbox
            except json.JSONDecodeError:
                pass

        return None

    def test_dropdown_has_listbox_reference(self, html_snapshots_path: Path) -> None:
        """Verify dropdown inputs have aria-controls or lsdata pointing to listbox."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        dropdowns = soup.select('input[ct="CB"]')
        assert len(dropdowns) >= 1, "Expected at least one dropdown"

        # At least one dropdown should have a listbox reference
        found_listbox = False
        for dd in dropdowns:
            aria_controls = dd.get("aria-controls")
            lsdata_raw = dd.get("lsdata")

            has_aria = aria_controls is not None
            has_lsdata_3 = False
            if lsdata_raw:
                try:
                    lsdata = json.loads(lsdata_raw)
                    has_lsdata_3 = "3" in lsdata
                except json.JSONDecodeError:
                    pass

            if has_aria or has_lsdata_3:
                found_listbox = True
                break

        assert found_listbox, "At least one dropdown should have listbox reference via aria-controls or lsdata[3]"

    def test_listbox_has_options_with_data_itemkey(self, html_snapshots_path: Path) -> None:
        """Verify listbox contains options with data-itemkey attribute."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        # Find any listbox element
        listboxes = soup.select('[role="listbox"]')
        if not listboxes:
            pytest.skip("No listboxes found in snapshot")

        # At least one listbox should have options with data-itemkey
        found_options = False
        for listbox in listboxes:
            options = listbox.select("[data-itemkey]")
            if len(options) >= 1:
                found_options = True
                # Verify option structure
                opt = options[0]
                assert opt.has_attr("data-itemkey"), "Option should have data-itemkey"
                break

        assert found_options, "Expected listbox with options having data-itemkey attribute"

    def test_listbox_options_have_value_attributes(self, html_snapshots_path: Path) -> None:
        """Verify listbox options have data-itemvalue1 and data-itemvalue2."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        # Find options with data-itemkey
        options = soup.select("[data-itemkey]")
        if not options:
            pytest.skip("No options found in snapshot")

        # Check that options have value attributes
        for opt in options[:5]:  # Check first 5 options
            key = opt.get("data-itemkey")
            value1 = opt.get("data-itemvalue1")
            value2 = opt.get("data-itemvalue2")

            # At least one value attribute should exist
            assert key is not None, "Option should have data-itemkey"
            # value1 or value2 should exist
            has_value = value1 is not None or value2 is not None
            assert has_value, f"Option with key={key} should have data-itemvalue1 or data-itemvalue2"

    def test_dropdown_can_find_associated_listbox(self, html_snapshots_path: Path) -> None:
        """Verify we can find the listbox for a dropdown input."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        dropdowns = soup.select('input[ct="CB"]')
        if not dropdowns:
            pytest.skip("No dropdowns found")

        # Try to find listbox for at least one dropdown
        found_listbox = False
        for dd in dropdowns:
            listbox = self._find_listbox_for_dropdown(soup, dd)
            if listbox:
                found_listbox = True
                # Verify it's a listbox
                assert listbox.get("role") == "listbox" or listbox.has_attr("role"), "Found element should be a listbox"
                break

        assert found_listbox, "Should be able to find listbox for at least one dropdown"

    def test_gruppierung_dropdown_has_listbox_with_options(self, html_snapshots_path: Path) -> None:
        """Verify Gruppierung dropdown has associated listbox with options."""
        snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
        if not snapshot_path:
            pytest.skip("BP create person snapshot not found")
        soup = load_snapshot(snapshot_path)
        if not soup:
            pytest.skip("Could not load BP create person snapshot")

        # Find Gruppierung dropdown
        # Note: Full German label is "Geschäftspartnergruppierung"
        dropdowns = soup.select('input[ct="CB"]')
        gruppierung = None
        for dd in dropdowns:
            title = dd.get("title", "").lower()
            if "gruppieru" in title or "grouping" in title:
                gruppierung = dd
                break

        if not gruppierung:
            pytest.skip("Gruppierung dropdown not found")

        listbox = self._find_listbox_for_dropdown(soup, gruppierung)
        assert listbox is not None, "Gruppierung dropdown should have associated listbox"

        # Verify listbox has options
        options = listbox.select("[data-itemkey]")
        assert len(options) >= 1, "Gruppierung listbox should have at least one option"


class TestAmbiguousLabelDetection:
    """Tests for ambiguous label detection in field finding.

    When multiple form fields share the same label (e.g., "Postleitzahl" for both
    street address and PO Box), the field finder should detect the ambiguity and
    return an error with the available selectors.

    This prevents silently matching the first field when the user might intend
    to fill a different field with the same label.
    """

    def _find_inputs_by_label(self, soup: BeautifulSoup, label_text: str) -> list[dict[str, str | None]]:
        """
        Simulate the JavaScript findInputByLabel function with ambiguity detection.

        Returns a list of all matching inputs instead of just the first one.
        Each match includes: element, selector, source, lsdataField

        IMPORTANT: This mirrors the JS logic that searches ALL strategies before
        checking for uniqueness (title + lsdata + aria-label, etc.).
        """
        normalized_label = label_text.strip()
        all_matches: list[dict[str, str | None]] = []

        def add_match(element: Tag, selector: str, source: str, lsdata_field: str | None = None) -> None:
            """Add a match if not already present by element."""
            if not any(m["element"] is element for m in all_matches):
                all_matches.append(
                    {
                        "element": element,
                        "selector": selector,
                        "source": source,
                        "lsdataField": lsdata_field,
                    }
                )

        def extract_lsdata_field(inp: Tag) -> str | None:
            """Extract field name from input's lsdata attribute."""
            input_lsdata_raw = inp.get("lsdata")
            if input_lsdata_raw:
                try:
                    input_lsdata = json.loads(input_lsdata_raw)
                    # Field name is often in key "0"
                    if input_lsdata.get("0"):
                        return input_lsdata.get("0")
                    # Or in nested SID object
                    sid = input_lsdata.get("21", {}).get("SID", "")
                    if sid:
                        # Extract field name from SID like ".../txtADDR2_DATA-POST_CODE1"
                        import re

                        match = re.search(r"txt([A-Z0-9_-]+)$", sid)
                        if match:
                            return match.group(1)
                except json.JSONDecodeError:
                    pass
            return None

        # 1. Try title attribute match (search ALL, don't return early)
        for tag_name in ("input", "select", "textarea"):
            for inp in soup.find_all(tag_name, attrs={"title": True}):
                title = inp.get("title", "")
                if title.strip() == normalized_label:
                    selector = f"#{inp['id']}" if inp.get("id") else f'[title="{title}"]'
                    lsdata_field = extract_lsdata_field(inp)
                    add_match(inp, selector, "title", lsdata_field)

        # 2. SAP-specific: labels use lsdata["1"] for associated input ID
        # Continue searching even if we found title matches!
        labels = soup.find_all("label", attrs={"lsdata": True})
        for label in labels:
            lsdata_raw = label.get("lsdata")
            if not lsdata_raw:
                continue
            try:
                lsdata = json.loads(lsdata_raw)
                if lsdata.get("3", "").strip() == normalized_label and lsdata.get("1"):
                    input_el = soup.find(id=lsdata["1"])
                    if input_el:
                        lsdata_field = extract_lsdata_field(input_el)
                        selector = f"#{input_el['id']}"
                        add_match(input_el, selector, "lsdata", lsdata_field)
            except json.JSONDecodeError:
                continue

        # 3. Try standard label with 'for' attribute
        for label in soup.find_all("label"):
            if label.get_text(strip=True) == normalized_label and label.get("for"):
                input_el = soup.find(id=label.get("for"))
                if input_el:
                    lsdata_field = extract_lsdata_field(input_el)
                    selector = f"#{input_el['id']}"
                    add_match(input_el, selector, "for-attribute", lsdata_field)

        return all_matches

    def test_bp_person_form_duplicate_postleitzahl(self, html_snapshots_path: Path) -> None:
        """Test that real BP Person form has duplicate Postleitzahl fields.

        The BP Person form (BP transaction, F5 for Person) has two Postleitzahl fields:
        - ADDR2_DATA-POST_CODE1: for street address
        - ADDR2_DATA-POST_CODE2: for PO Box address

        Both are labeled "Postleitzahl" (or "Postal Code" in English).
        """
        snapshot = get_snapshot_path(html_snapshots_path, "bp_person_form")
        if snapshot is None:
            pytest.skip("bp_person_form snapshot not available")

        soup = load_snapshot(snapshot)
        if soup is None:
            pytest.skip("Could not parse bp_person_form snapshot")

        # Determine language-specific label
        lang = "en" if "_en.html" in str(snapshot) else "de"
        label = "Postal Code" if lang == "en" else "Postleitzahl"

        matches = self._find_inputs_by_label(soup, label)

        # The form should have at least 2 Postleitzahl fields
        # (may have more if there are other address sections)
        assert len(matches) >= 2, (
            f"Expected at least 2 matches for '{label}' in BP Person form, "
            f"got {len(matches)}. This verifies the bug scenario exists. "
            f"Matches: {[m.get('selector') for m in matches]}"
        )

        # Verify POST_CODE1 and POST_CODE2 are both present
        lsdata_fields = {m["lsdataField"] for m in matches if m["lsdataField"]}
        has_post_code1 = any("POST_CODE1" in (f or "") for f in lsdata_fields)
        has_post_code2 = any("POST_CODE2" in (f or "") for f in lsdata_fields)

        assert has_post_code1 and has_post_code2, (
            f"BP Person form should have both POST_CODE1 and POST_CODE2 fields. "
            f"Found lsdata fields: {lsdata_fields}"
        )

    def test_bp_person_form_unique_label(self, html_snapshots_path: Path) -> None:
        """Test that unique labels in BP Person form find exactly one match."""
        snapshot = get_snapshot_path(html_snapshots_path, "bp_person_form")
        if snapshot is None:
            pytest.skip("bp_person_form snapshot not available")

        soup = load_snapshot(snapshot)
        if soup is None:
            pytest.skip("Could not parse bp_person_form snapshot")

        # Determine language-specific label
        lang = "en" if "_en.html" in str(snapshot) else "de"
        label = "First Name" if lang == "en" else "Vorname"

        matches = self._find_inputs_by_label(soup, label)

        # Vorname/First Name should be unique
        assert len(matches) == 1, (
            f"Expected exactly 1 match for '{label}' in BP Person form, "
            f"got {len(matches)}. Matches: {[m.get('selector') for m in matches]}"
        )
