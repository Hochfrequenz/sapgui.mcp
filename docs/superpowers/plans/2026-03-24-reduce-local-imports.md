# Reduce Local Imports — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `import-outside-toplevel` disables from ~63 to ~28 by breaking one circular dependency chain, adding a protocol-level backend type property, and promoting trivially-local imports to top-level.

**Architecture:** One new file (`_landscape.py`), one new protocol property, and mechanical import promotions across ~15 files. No behavioral changes.

**Tech Stack:** Python, Pydantic, pylint, mypy, isort, black

**Spec:** `docs/superpowers/specs/2026-03-24-reduce-local-imports-design.md`

---

### Task 1: Add `backend_type` property to protocol and backends

**Files:**
- Modify: `src/sapguimcp/backend/protocol.py`
- Modify: `src/sapguimcp/backend/desktop/__init__.py`
- Modify: `src/sapguimcp/backend/webgui/backend.py`
- Modify: `src/sapguimcp/tools/_backend_utils.py`
- Modify: `unittests/desktop/test_desktop_backend.py`

- [ ] **Step 1: Add `backend_type` to `SapNavigation` protocol**

In `src/sapguimcp/backend/protocol.py`, find the `SapNavigation` protocol class (the first sub-protocol that `SapUiBackend` composes). Add a `backend_type` property:

```python
@property
def backend_type(self) -> str:
    """Return backend identifier: 'desktop' or 'webgui'."""
    ...
```

- [ ] **Step 2: Implement in DesktopBackend**

In `src/sapguimcp/backend/desktop/__init__.py`, add to the `DesktopBackend` class:

```python
@property
def backend_type(self) -> str:
    return "desktop"
```

- [ ] **Step 3: Implement in WebGuiBackend**

In `src/sapguimcp/backend/webgui/backend.py`, add to the `WebGuiBackend` class:

```python
@property
def backend_type(self) -> str:
    return "webgui"
```

- [ ] **Step 4: Rewrite `_is_desktop_backend` without lazy import**

Replace `src/sapguimcp/tools/_backend_utils.py` contents with:

```python
"""Shared backend detection utilities for transaction tools."""

from sapguimcp.backend.protocol import SapUiBackend


def _is_desktop_backend(backend: SapUiBackend) -> bool:
    """Check if we're using the desktop (COM) backend."""
    return backend.backend_type == "desktop"
```

- [ ] **Step 5: Add unit test**

In `unittests/desktop/test_desktop_backend.py`, add a test to the existing `TestDesktopBackendEnterTransaction` class area:

```python
class TestDesktopBackendType:
    def test_backend_type_is_desktop(self):
        from sapguimcp.backend.desktop import DesktopBackend
        backend = DesktopBackend.__new__(DesktopBackend)
        assert backend.backend_type == "desktop"
```

- [ ] **Step 6: Run tests and lint**

```bash
python -m pytest unittests/desktop/test_desktop_backend.py -v
python -m pylint src/sapguimcp/tools/_backend_utils.py src/sapguimcp/backend/protocol.py
python -m mypy --strict src/sapguimcp/backend/protocol.py src/sapguimcp/tools/_backend_utils.py
```

- [ ] **Step 7: Format and commit**

```bash
python -m isort src/sapguimcp/backend/protocol.py src/sapguimcp/backend/desktop/__init__.py src/sapguimcp/backend/webgui/backend.py src/sapguimcp/tools/_backend_utils.py unittests/desktop/test_desktop_backend.py
python -m black src/sapguimcp/backend/protocol.py src/sapguimcp/backend/desktop/__init__.py src/sapguimcp/backend/webgui/backend.py src/sapguimcp/tools/_backend_utils.py unittests/desktop/test_desktop_backend.py
git add -u && git commit -m "refactor: add backend_type property, remove lazy import in _backend_utils"
```

---

### Task 2: Extract `_landscape.py` — break the circular chain

**Files:**
- Create: `src/sapguimcp/backend/desktop/_landscape.py`
- Modify: `src/sapguimcp/tools/sap_list_connections_impl.py`
- Modify: `src/sapguimcp/backend/desktop/__init__.py`
- Modify: `unittests/test_sap_list_connections.py` (if it imports from impl)

- [ ] **Step 1: Create `_landscape.py`**

Create `src/sapguimcp/backend/desktop/_landscape.py` with `_find_landscape_path()` and `_parse_landscape_xml()` moved from `tools/sap_list_connections_impl.py`. These are lines 22-60 of that file. Keep the exact same code and docstrings.

```python
"""SAP Logon landscape XML discovery and parsing."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def _find_landscape_path() -> Path | None:
    """Find SAPUILandscape.xml via registry or default location."""
    if sys.platform == "win32":
        try:
            import winreg  # pylint: disable=import-outside-toplevel,import-error

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SAP\SAPLogon\Options") as key:
                path, _ = winreg.QueryValueEx(key, "LandscapeFile")
                p = Path(path)
                if p.is_file():
                    return p
        except OSError:
            pass

    default = Path.home() / "AppData" / "Roaming" / "SAP" / "Common" / "SAPUILandscape.xml"
    if default.is_file():
        return default
    return None


def _parse_landscape_xml(xml_text: str) -> list[dict[str, Any]]:
    """Parse SAPUILandscape XML and return connection entries."""
    root = ET.fromstring(xml_text)
    services = root.find("Services")
    if services is None:
        return []

    result = []
    for svc in services.findall("Service"):
        entry: dict[str, Any] = {
            "name": svc.get("name", ""),
            "type": svc.get("type", ""),
            "systemid": svc.get("systemid", ""),
            "server": svc.get("server", ""),
            "client": svc.get("client", ""),
            "description": svc.get("description", ""),
        }
        result.append(entry)
    return result
```

- [ ] **Step 2: Update `sap_list_connections_impl.py`**

Remove `_find_landscape_path` and `_parse_landscape_xml` function bodies. Import them from the new location instead:

```python
from sapguimcp.backend.desktop._landscape import _find_landscape_path, _parse_landscape_xml
```

Keep the `__all__` export and `ConnectionListResult` class and `sap_list_connections_impl` function.

**Important:** Also remove the now-unused imports `import sys`, `import xml.etree.ElementTree as ET`, and `from pathlib import Path` — they were only used by the moved functions. Leaving them will cause pylint unused-import warnings.

- [ ] **Step 3: Update `desktop/__init__.py` lazy import**

In `desktop/__init__.py`, find the lazy import of `_find_landscape_path, _parse_landscape_xml` from `tools/sap_list_connections_impl` (inside `list_connections` method). Change it to import from the new sibling module:

```python
from sapguimcp.backend.desktop._landscape import _find_landscape_path, _parse_landscape_xml
```

Since this is now a sibling import (no circular risk), it can be promoted to top-level. Move it to the top-level imports section.

- [ ] **Step 4: Run existing tests**

```bash
python -m pytest unittests/test_sap_list_connections.py -v
python -m mypy --strict src/sapguimcp/backend/desktop/_landscape.py src/sapguimcp/tools/sap_list_connections_impl.py
```

- [ ] **Step 5: Format and commit**

```bash
python -m isort src/sapguimcp/backend/desktop/_landscape.py src/sapguimcp/tools/sap_list_connections_impl.py src/sapguimcp/backend/desktop/__init__.py
python -m black src/sapguimcp/backend/desktop/_landscape.py src/sapguimcp/tools/sap_list_connections_impl.py src/sapguimcp/backend/desktop/__init__.py
git add -u && git commit -m "refactor: extract _landscape.py to break desktop → tools circular chain"
```

---

### Task 3: Promote manager.py backend imports to top-level

**Files:**
- Modify: `src/sapguimcp/backend/manager.py`

- [ ] **Step 1: Move lazy imports to top-level with platform guard**

In `manager.py`, add top-level imports after the existing imports (around line 9):

```python
from sapguimcp.backend.webgui.backend import WebGuiBackend
from sapguimcp.backend.webgui.browser import close_browser_manager, get_browser_manager

if sys.platform == "win32":
    from sapguimcp.backend.desktop import DesktopBackend, _current_session_id
    from sapguimcp.backend.desktop._com_thread import ComThread
elif TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend, _current_session_id
    from sapguimcp.backend.desktop._com_thread import ComThread
```

The `elif TYPE_CHECKING` branch ensures mypy on Linux CI can still resolve the names. At runtime on non-Windows, the existing check `if backend_type == "desktop" and sys.platform != "win32": raise RuntimeError(...)` in `__init__` prevents any code path from reaching them.

Remove the 5 lazy imports inside `get_or_create()` and `close()` methods. Remove their `# pylint: disable=import-outside-toplevel` comments.

- [ ] **Step 2: Run tests**

```bash
python -m pytest unittests/ -v -k "not integration" --ignore=unittests/webgui 2>&1 | tail -5
python -m mypy --strict src/sapguimcp/backend/manager.py
```

- [ ] **Step 3: Format and commit**

```bash
python -m isort src/sapguimcp/backend/manager.py && python -m black src/sapguimcp/backend/manager.py
git add -u && git commit -m "refactor: promote manager.py backend imports to top-level"
```

---

### Task 4: Promote trivial imports in `desktop/__init__.py`

**Files:**
- Modify: `src/sapguimcp/backend/desktop/__init__.py`

- [ ] **Step 1: Move result models from TYPE_CHECKING to runtime imports**

In `desktop/__init__.py`, the TYPE_CHECKING block (lines 59-68) has:
```python
if TYPE_CHECKING:
    from sapsucker.components.session import GuiSession
    from sapguimcp.backend.protocol import CheckActivateResult
    from sapguimcp.models.sap_results import (
        ClosePopupResult, DropdownFillResult, FillFormResult, FormFieldsResult,
    )
```

Move `CheckActivateResult`, `ClosePopupResult`, `DropdownFillResult`, `FillFormResult`, `FormFieldsResult` to the top-level runtime import section (add to existing `from sapguimcp.models.sap_results import (...)` block). Keep only `GuiSession` in TYPE_CHECKING (sapsucker, platform-dependent).

Add `from sapguimcp.backend.protocol import CheckActivateResult` as a new top-level import.

Then remove the 5 corresponding lazy imports inside methods (lines ~574, ~882, ~1017, ~1231, ~1371) and their `# pylint: disable=import-outside-toplevel` comments.

- [ ] **Step 2: Promote `get_settings`, `time`, `PopupButton`, `PopupType`**

Move these lazy imports to top-level:
- `from sapguimcp.models.config import get_settings` — add to top-level imports
- `import time` — add to stdlib imports at top
- `from sapguimcp.models.base import PopupButton, PopupType` — add `PopupButton, PopupType` to the existing `from sapguimcp.models.base import PopupInfo, ToolResult` line

Remove the corresponding lazy imports inside methods and their disable comments.

- [ ] **Step 3: Consolidate `GuiGridView` with try/except**

Add near the top-level imports (after sapsucker.login):

```python
try:
    from sapsucker.components.grid import GuiGridView
except ImportError:
    GuiGridView = None  # type: ignore[misc,assignment]
```

Remove the lazy `from sapsucker.components.grid import GuiGridView` imports inside `_read()`, `_click()`, and `fill_grid_cell()` methods.

- [ ] **Step 4: Run tests and type check**

```bash
python -m pytest unittests/desktop/test_desktop_backend.py -v
python -m mypy --strict src/sapguimcp/backend/desktop/__init__.py
python -m pylint src/sapguimcp/backend/desktop/__init__.py
```

- [ ] **Step 5: Format and commit**

```bash
python -m isort src/sapguimcp/backend/desktop/__init__.py && python -m black src/sapguimcp/backend/desktop/__init__.py
git add -u && git commit -m "refactor: promote ~14 lazy imports to top-level in desktop backend"
```

---

### Task 5: Promote trivial imports in webgui and tool files

**Files:**
- Modify: `src/sapguimcp/backend/webgui/backend.py`
- Modify: `src/sapguimcp/tools/se09_tools.py`
- Modify: `src/sapguimcp/tools/se11_tools.py`
- Modify: `src/sapguimcp/tools/se24_edit_tools.py`
- Modify: `src/sapguimcp/tools/spro_tools.py`
- Modify: `src/sapguimcp/tools/quick_report_tools.py`
- Modify: `src/sapguimcp/backend/desktop/_discovery.py`

- [ ] **Step 1: Promote imports in `webgui/backend.py`**

Move to top-level:
- `from playwright.async_api import Error as PlaywrightError` (used at lines ~1262, ~1275)
- `from sapguimcp.models.sap_results import SapFieldType` (used at line ~1059)
- `from sapguimcp.backend.webgui.browser import get_browser_manager` (used at line ~1416)

Remove the lazy imports and their disable comments inside the methods.

- [ ] **Step 2: Promote imports in tool files**

For each file, move the import to the top-level imports section and remove the lazy import + disable comment inside the function:

- `se09_tools.py`: promote `import time` and `from typing import Any` (2 lazy `time` + 2 lazy `Any`)
- `se11_tools.py`: promote `import time` (1 lazy import)
- `se24_edit_tools.py`: promote `from typing import Any` and `from typing import cast` (2 lazy imports)
- `spro_tools.py`: promote `import asyncio` (2 lazy imports)
- `quick_report_tools.py`: promote `from sapguimcp.backend.manager import get_backend` (1 lazy import)

Check if the imports already exist at top-level first — if `time`, `asyncio`, `Any`, `cast` are already imported, just remove the lazy duplicate.

- [ ] **Step 3: Consolidate `GuiGridView` and `_flatten` in `_discovery.py`**

In `backend/desktop/_discovery.py`, find the lazy `from sapsucker.components.grid import GuiGridView` and `from sapguimcp.backend.desktop._element_finder import _flatten` imports. Move both to top-level: `_flatten` as a normal import, `GuiGridView` via `try/except ImportError` block.

**Caution for se09_tools.py and se11_tools.py:** The `time` and `Any` lazy imports share the same function scope as `DesktopBackend` lazy imports that must stay local. Only promote `time` and `Any` — leave the adjacent `DesktopBackend` and `_flatten` imports untouched.

- [ ] **Step 4: Run full test suite and lint**

```bash
python -m pytest unittests/ -v -k "not integration" --ignore=unittests/webgui 2>&1 | tail -10
python -m pylint src/sapguimcp
python -m mypy --strict src/sapguimcp
```

- [ ] **Step 5: Format and commit**

```bash
python -m isort src/sapguimcp && python -m black src/sapguimcp
git add -u && git commit -m "refactor: promote trivial lazy imports in webgui and tool files"
```

---

### Task 6: Final verification and count

**Files:** None (verification only)

- [ ] **Step 1: Count remaining lazy imports**

```bash
grep -rn "pylint: disable=import-outside-toplevel" src/sapguimcp/ | wc -l
```

Expected: ~28 (down from ~63).

- [ ] **Step 2: Run full verification suite**

```bash
python -m pylint src/sapguimcp
python -m mypy --strict src/sapguimcp
python -m isort --check src/sapguimcp unittests
python -m black --check src/sapguimcp unittests
python -m pytest unittests/ -v -k "not integration" --ignore=unittests/webgui 2>&1 | tail -5
```

All must pass. Pylint must be 10.00/10.

- [ ] **Step 3: List remaining lazy imports for documentation**

```bash
grep -rn "pylint: disable=import-outside-toplevel" src/sapguimcp/ | sed 's/:.*//' | sort | uniq -c | sort -rn
```

Verify each remaining import is in the "stays local" list from the spec.

- [ ] **Step 4: Final commit if any formatting changes**

```bash
git add -u && git commit -m "refactor: final formatting after import cleanup" || echo "Nothing to commit"
```
