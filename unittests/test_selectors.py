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

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag

# Import the selectors we want to test
from sapwebguimcp.tools.sap_tools import SELECTORS


@pytest.fixture
def html_snapshots_path() -> Path:
    """Return the path to the HTML snapshots directory."""
    return Path(__file__).parent / "testdata" / "html_snapshots"


def get_snapshot_path(base_dir: Path, base_name: str) -> Path | None:
    """
    Find a snapshot file, preferring English but falling back to German.

    Snapshots are named with language suffix: easy_access_en.html, easy_access_de.html

    Args:
        base_dir: Directory containing snapshots
        base_name: Base name without extension (e.g., "easy_access")

    Returns:
        Path to the snapshot file, or None if not found
    """
    # Prefer English, fall back to German
    for lang in ("en", "de"):
        path = base_dir / f"{base_name}_{lang}.html"
        if path.exists():
            return path
    return None


def load_snapshot(snapshot_path: Path) -> BeautifulSoup | None:
    """
    Load an HTML snapshot and parse it with BeautifulSoup.

    Args:
        snapshot_path: Full path to the HTML snapshot file.

    Returns:
        BeautifulSoup object or None if the snapshot doesn't exist (test will be skipped).
    """
    if not snapshot_path.exists():
        return None
    html = snapshot_path.read_text(encoding="utf-8")
    # Use html.parser instead of lxml for cross-platform compatibility
    # (lxml may behave differently on Linux vs Windows with minified HTML)
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
        snapshot = get_snapshot_path(html_snapshots_path, "settings_dialog")
        if snapshot is None:
            pytest.skip("settings_dialog snapshot not available - run integration tests first")
        soup = load_snapshot(snapshot)

        checkboxes = soup.find_all("input", {"type": "checkbox"})

        assert len(checkboxes) >= 1, (
            "Settings dialog should contain at least one checkbox. " "The OK-Code field setting is a checkbox."
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
            print(f"DEBUG: Snapshot path: {snapshot}")
            print(f"DEBUG: HTML length: {len(html_content)}")
            print(f"DEBUG: 'sap-client' in HTML: {'sap-client' in html_content}")
            print(f"DEBUG: 'id=\"sap-client\"' in HTML: {'id=\"sap-client\"' in html_content}")
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
