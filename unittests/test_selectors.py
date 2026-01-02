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

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

# Import the selectors we want to test
from sapwebguimcp.tools.sap_tools import SELECTORS


@pytest.fixture
def html_snapshots_path() -> Path:
    """Return the path to the HTML snapshots directory."""
    return Path(__file__).parent / "testdata" / "html_snapshots"


def load_snapshot(snapshots_path: Path, filename: str) -> BeautifulSoup | None:
    """
    Load an HTML snapshot and parse it with BeautifulSoup.

    Returns None if the snapshot doesn't exist (test will be skipped).
    """
    filepath = snapshots_path / filename
    if not filepath.exists():
        return None
    html = filepath.read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def css_select(soup: BeautifulSoup, selector: str) -> list:
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
        soup = load_snapshot(html_snapshots_path, "easy_access.html")
        if soup is None:
            pytest.skip("easy_access.html snapshot not available - run integration tests first")

        elements = css_select(soup, SELECTORS["okcode_field"])

        assert len(elements) >= 1, (
            f"OK-Code field selector should find at least one element. " f"Selector: {SELECTORS['okcode_field']}"
        )

        # Verify it's an input element
        okcode = elements[0]
        assert okcode.name == "input", f"OK-Code field should be an input element, got: {okcode.name}"

    def test_okcode_field_in_su3(self, html_snapshots_path: Path) -> None:
        """Verify OK-Code field is present in SU3 transaction screen."""
        soup = load_snapshot(html_snapshots_path, "su3_screen.html")
        if soup is None:
            pytest.skip("su3_screen.html snapshot not available - run integration tests first")

        elements = css_select(soup, SELECTORS["okcode_field"])

        assert len(elements) >= 1, (
            f"OK-Code field should be present in SU3 screen. " f"Selector: {SELECTORS['okcode_field']}"
        )

    def test_okcode_field_in_se16(self, html_snapshots_path: Path) -> None:
        """Verify OK-Code field is present in SE16 Data Browser screen."""
        soup = load_snapshot(html_snapshots_path, "se16_initial.html")
        if soup is None:
            pytest.skip("se16_initial.html snapshot not available - run integration tests first")

        elements = css_select(soup, SELECTORS["okcode_field"])

        assert len(elements) >= 1, (
            f"OK-Code field should be present in SE16 screen. " f"Selector: {SELECTORS['okcode_field']}"
        )


class TestStatusBarSelector:
    """Tests for status bar message detection."""

    def test_status_bar_error_detection(self, html_snapshots_path: Path) -> None:
        """Verify error message is detectable in status bar HTML."""
        soup = load_snapshot(html_snapshots_path, "status_bar_error.html")
        if soup is None:
            pytest.skip("status_bar_error.html snapshot not available - run integration tests first")

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


def find_sap_field_by_sid(soup: BeautifulSoup, sid_pattern: str) -> list:
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
    """Tests for transaction-specific field selectors."""

    def test_se16_table_name_field(self, html_snapshots_path: Path) -> None:
        """Verify SE16 table name input field can be found.

        SAP Web GUI generates dynamic IDs like 'M0:46:::2:21' but the stable
        identifier is in the lsdata attribute: "SID":"wnd[0]/usr/ctxtDATABROWSE-TABLENAME"
        """
        soup = load_snapshot(html_snapshots_path, "se16_initial.html")
        if soup is None:
            pytest.skip("se16_initial.html snapshot not available - run integration tests first")

        # Find by SID pattern in lsdata (most reliable for SAP Web GUI)
        elements = find_sap_field_by_sid(soup, "DATABROWSE-TABLENAME")

        assert len(elements) >= 1, (
            "SE16 table name field should be found via lsdata SID containing 'DATABROWSE-TABLENAME'. "
            "SAP Web GUI uses dynamic IDs but stores stable identifiers in lsdata."
        )

        # Verify it's a text input
        field = elements[0]
        assert field.get("type", "text") == "text", "Table name field should be a text input"

    def test_sm37_job_name_field(self, html_snapshots_path: Path) -> None:
        """Verify SM37 job name input field can be found.

        SM37 has multiple input fields. The job name field has 'JOBNAME' in its SID.
        """
        soup = load_snapshot(html_snapshots_path, "sm37_initial.html")
        if soup is None:
            pytest.skip("sm37_initial.html snapshot not available - run integration tests first")

        # Find by SID pattern in lsdata
        elements = find_sap_field_by_sid(soup, "JOBNAME")

        assert len(elements) >= 1, (
            "SM37 job name field should be found via lsdata SID containing 'JOBNAME'. "
            "SAP Web GUI uses dynamic IDs but stores stable identifiers in lsdata."
        )


class TestInputFieldDiscovery:
    """Tests for general input field discovery."""

    def test_discover_inputs_in_se16(self, html_snapshots_path: Path) -> None:
        """Verify we can discover input fields in SE16 screen."""
        soup = load_snapshot(html_snapshots_path, "se16_initial.html")
        if soup is None:
            pytest.skip("se16_initial.html snapshot not available - run integration tests first")

        # Find all visible input elements (excluding hidden and buttons)
        inputs = soup.find_all("input")
        visible_inputs = [inp for inp in inputs if inp.get("type", "text") not in ("hidden", "submit", "button")]

        assert len(visible_inputs) >= 1, "SE16 screen should have at least one visible input field"

    def test_discover_inputs_in_sm37(self, html_snapshots_path: Path) -> None:
        """Verify we can discover input fields in SM37 screen."""
        soup = load_snapshot(html_snapshots_path, "sm37_initial.html")
        if soup is None:
            pytest.skip("sm37_initial.html snapshot not available - run integration tests first")

        inputs = soup.find_all("input")
        visible_inputs = [inp for inp in inputs if inp.get("type", "text") not in ("hidden", "submit", "button")]

        assert len(visible_inputs) >= 1, "SM37 screen should have at least one visible input field"


class TestLoginPageSelectors:
    """Tests for login page element selectors."""

    def test_login_form_elements(self, html_snapshots_path: Path) -> None:
        """Verify login form elements can be found (if login page snapshot exists)."""
        soup = load_snapshot(html_snapshots_path, "login_page.html")
        if soup is None:
            pytest.skip("login_page.html snapshot not available")

        # Check for standard SAP login form elements
        client_field = soup.select("#sap-client, input[name='sap-client']")
        user_field = soup.select("#sap-user, input[name='sap-user']")
        password_field = soup.select("#sap-password, input[name='sap-password']")
        login_button = soup.select("#LOGON_BUTTON")

        assert client_field, "Login page should have client/mandant field"
        assert user_field, "Login page should have username field"
        assert password_field, "Login page should have password field"
        assert login_button, "Login page should have login button"
