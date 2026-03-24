# SAP Web GUI HTML Snapshots

This directory contains HTML snapshots captured from real SAP Web GUI sessions.
These snapshots are used for unit testing CSS selectors and extraction logic
without requiring access to a live SAP system.

## Directory Structure

Snapshots are named with language suffixes (`_en.html`, `_de.html`):

```
html_snapshots/
├── README.md                    # This file
├── login_page_en.html           # SAP login form
├── easy_access_en.html          # SAP Easy Access menu with OK-Code field
├── easy_access_de.html          # German version
├── su3_screen_en.html           # SU3 User Profile screen
├── su3_screen_de.html           # German version
├── se16_initial_en.html         # SE16 Data Browser - initial screen
├── se16_t000_content_en.html    # SE16 T000 table content
├── se11_initial_en.html         # SE11 ABAP Dictionary - initial screen
├── se11_t000_content_en.html    # SE11 T000 table structure
├── sm37_initial_en.html         # SM37 Job Overview - initial screen
├── sm37_results_en.html         # SM37 job list results
├── status_bar_error_en.html     # Page with error in status bar
└── ...                          # Add more as needed
```

## How Snapshots Are Captured

Snapshots are automatically captured when running integration tests on a
machine with SAP WebGUI credentials configured. The `capture_html_snapshot` helper in
`test_sap_integration.py` saves the current page HTML with a language suffix
based on the `SAP_LANGUAGE` environment variable.

To recapture all snapshots in both languages:

```powershell
.\scripts\recapture-snapshots.ps1
```

To capture snapshots in a specific language only:

```bash
# Set language in .env file
SAP_LANGUAGE=EN  # or DE

# Run integration tests
tox -e integration_tests
```

## Adding New Snapshots Manually

1. Run your SAP Web GUI in a browser
2. Navigate to the screen you want to capture
3. Open browser DevTools (F12) -> Elements tab
4. Right-click on `<html>` -> Copy -> Copy outerHTML
5. Save to a `.html` file with language suffix (e.g., `screen_name_en.html`)
6. Add corresponding test cases in `test_selectors.py`

## Using Snapshots in Tests

```python
from pathlib import Path

def get_snapshot_path(base_dir: Path, base_name: str) -> Path | None:
    """Find a snapshot file, preferring English but falling back to German."""
    for lang in ("en", "de"):
        path = base_dir / f"{base_name}_{lang}.html"
        if path.exists():
            return path
    return None

def test_okcode_field_selector(html_snapshots_path: Path) -> None:
    snapshot = get_snapshot_path(html_snapshots_path, "easy_access")
    if snapshot is None:
        pytest.skip("easy_access snapshot not available")
    soup = load_snapshot(snapshot)
    # Test selector against soup...
```

## Important Notes

- HTML may contain sensitive data - review before committing
- SAP Web GUI generates dynamic IDs - use `lsdata` SID patterns for stability
- Snapshots represent a point-in-time - SAP updates may change HTML structure
- Multi-language support: capture both EN and DE variants for comprehensive testing
