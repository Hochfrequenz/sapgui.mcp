# SAP Web GUI HTML Snapshots

This directory contains HTML snapshots captured from real SAP Web GUI sessions.
These snapshots are used for unit testing CSS selectors and extraction logic
without requiring access to a live SAP system.

## Directory Structure

```
html_snapshots/
├── README.md              # This file
├── login_page.html        # SAP login form
├── easy_access.html       # SAP Easy Access menu with OK-Code field
├── se16_initial.html      # SE16 Data Browser - initial screen
├── se16_results.html      # SE16 with table results
├── su3_screen.html        # SU3 User Profile screen
├── sm37_initial.html      # SM37 Job Overview - initial screen
├── status_bar_error.html  # Page with error in status bar
├── status_bar_success.html # Page with success message
└── ...                    # Add more as needed
```

## How Snapshots Are Captured

Snapshots are automatically captured when running integration tests on an
authorized machine (HF-KKLEIN3). The `capture_html_snapshot` helper in
`conftest.py` saves the current page HTML to this directory.

## Adding New Snapshots Manually

1. Run your SAP Web GUI in a browser
2. Navigate to the screen you want to capture
3. Open browser DevTools (F12) → Elements tab
4. Right-click on `<html>` → Copy → Copy outerHTML
5. Save to a `.html` file in this directory
6. Add corresponding test cases in `test_selectors.py`

## Using Snapshots in Tests

```python
@pytest.fixture
def html_snapshot_path():
    return Path(__file__).parent / "testdata" / "html_snapshots"

def test_okcode_field_selector(html_snapshot_path):
    html = (html_snapshot_path / "easy_access.html").read_text()
    # Test selector against html...
```

## Important Notes

- HTML may contain sensitive data - review before committing
- SAP Web GUI generates dynamic IDs - selectors should be resilient
- Snapshots represent a point-in-time - SAP updates may change HTML structure
