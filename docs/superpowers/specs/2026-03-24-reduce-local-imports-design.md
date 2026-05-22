# Reduce Local Imports

**Date:** 2026-03-24
**Status:** Approved
**Issue:** The codebase has ~63 local (lazy) imports scattered across `src/sapguimcp/`. Most exist to work around a circular dependency chain or because imports were never promoted to top-level. This spec describes how to reduce them to ~28, keeping only those justified by platform constraints or concrete-class access patterns.

## Problem

~63 lines with `# pylint: disable=import-outside-toplevel` across 22 files. The root causes are:

1. **One circular chain:** `desktop/__init__.py` → `tools/sap_list_connections_impl.py` → `backend/manager.py` → `desktop/__init__.py`. This forces `desktop/__init__.py` to lazily import landscape parsing helpers from `tools/`. As a side effect, `manager.py` also uses lazy imports for both backends (though the webgui lazy imports are not strictly forced by this cycle — they are historical).
2. **No protocol-level backend type check:** `_is_desktop_backend()` imports `DesktopBackend` at call time to do `isinstance()`.
3. **Imports that are local for no structural reason:** `time`, `asyncio`, `typing.Any`, `typing.cast`, `PlaywrightError`, sapsucker components, result models, `get_settings`, `get_backend` — all safe to import at module level.

## Design

### Part 1: Add `backend_type` property to SapUiBackend protocol

Add a read-only `backend_type` property returning `"desktop"` or `"webgui"` to `backend/protocol.py`. Implement in both backends. Rewrite `_is_desktop_backend()` as:

```python
def _is_desktop_backend(backend: SapUiBackend) -> bool:
    return backend.backend_type == "desktop"
```

**Eliminates:** 1 lazy import in `_backend_utils.py`.

### Part 2: Break the `desktop → tools` back-edge

Move `_find_landscape_path()` and `_parse_landscape_xml()` from `tools/sap_list_connections_impl.py` into a new `backend/desktop/_landscape.py`. These functions parse SAP Logon XML config — they belong in the backend layer, not tools. Update `desktop/__init__.py` and `tools/sap_list_connections_impl.py` to import from the new location.

This breaks the only `backend → tools` edge: `desktop/__init__.py` no longer imports from `tools/`. With the cycle gone:

- `manager.py` can import both backends at top-level. Desktop imports use a platform guard:
  ```python
  if sys.platform == "win32":
      from sapguimcp.backend.desktop import DesktopBackend, _current_session_id
      from sapguimcp.backend.desktop._com_thread import ComThread
  ```
  This is needed because `desktop/__init__.py` imports `sapsucker.login` at top-level, which only exists on Windows.
- `desktop/__init__.py` can import result models and `get_settings` at top-level since there is no longer a reverse path back to `tools/`.

**Eliminates:** 5 lazy imports in `manager.py`, 1 lazy import in `desktop/__init__.py` (the `sap_list_connections_impl` import).

### Part 3: Promote trivially-local imports to top-level

These imports have no circular dependency risk and are local for historical reasons only.

| Import | Files | Lines |
|--------|-------|-------|
| `time` | se09_tools.py, se11_tools.py, desktop/__init__.py | 4 |
| `asyncio` | spro_tools.py | 2 |
| `typing.Any`, `typing.cast` | se09_tools.py, se24_edit_tools.py | 4 |
| `PlaywrightError` | webgui/backend.py | 2 |
| `SapFieldType` | webgui/backend.py | 1 |
| `get_browser_manager` | webgui/backend.py | 1 |
| `get_settings` | desktop/__init__.py | 2 |
| `get_backend` | quick_report_tools.py | 1 |
| Result models (`FormFieldsResult`, `FillFormResult`, `DropdownFillResult`, `ClosePopupResult`, `CheckActivateResult`, `PopupButton`, `PopupType`) | desktop/__init__.py | 7 |

**Eliminates:** ~24 lazy imports.

### Part 4: Consolidate sapsucker/platform imports

In `desktop/__init__.py` and `_discovery.py`, replace multiple scattered lazy `from sapsucker.components.grid import GuiGridView` with a single top-level block:

```python
try:
    from sapsucker.components.grid import GuiGridView
except ImportError:
    GuiGridView = None  # type: ignore[misc,assignment]
```

Similarly for `_flatten` from `_element_finder` in `desktop/__init__.py` (already a sibling module, no circular risk).

Note: `_discovery.py` lines 128-130 (`sapsucker.login`, `SapGui`, `SapConnectionError`) and `wrap_com_object` in `desktop/__init__.py` stay local — they are inside rarely-called methods with heavy import chains.

**Eliminates:** ~5 lazy imports.

### What stays local (~28 imports)

These are justified and should remain:

| Import | File(s) | Count | Reason |
|--------|---------|-------|--------|
| `DesktopBackend` | 12 tool helper functions | 12 | Need concrete class for `._com`, `._require_session()` |
| `_flatten` | 5 tool files (co-located with DesktopBackend) | 5 | Same guard block as DesktopBackend |
| `pythoncom` | `_com_thread.py` | 2 | Runtime `if self._init_com` platform guard |
| `winreg` | `sap_list_connections_impl.py` | 1 | `sys.platform == "win32"` guard |
| `wrap_com_object` | `desktop/__init__.py` | 1 | COM thread callback |
| `sapsucker.login`, `SapGui`, `SapConnectionError` | `_discovery.py` | 3 | Heavy import chain, called rarely |
| `GuiVContainer` | `se93_tools.py` | 1 | sapsucker component in COM callback |
| `server` | `__init__.py` | 1 | `__getattr__` lazy module loading |
| `_sapguimcp_version` | `server.py` | 1 | Generated file, may not exist |
| `open_and_discover_clients` | `desktop/__init__.py` | 1 | Heavy import chain, called rarely |

**Total remaining: ~28**

## File changes

| Action | File |
|--------|------|
| **Edit** | `backend/protocol.py` — add `backend_type` property |
| **Edit** | `backend/desktop/__init__.py` — implement property, promote ~14 imports to top-level |
| **Edit** | `backend/webgui/backend.py` — implement property, promote 4 imports |
| **Create** | `backend/desktop/_landscape.py` — move landscape XML parsing here |
| **Edit** | `tools/sap_list_connections_impl.py` — import from `_landscape.py` |
| **Edit** | `backend/manager.py` — promote 5 backend imports with platform guard |
| **Edit** | `tools/_backend_utils.py` — use `backend_type` property |
| **Edit** | `tools/se09_tools.py` — promote `time`, `Any` |
| **Edit** | `tools/se11_tools.py` — promote `time` |
| **Edit** | `tools/se24_edit_tools.py` — promote `Any`, `cast` |
| **Edit** | `tools/spro_tools.py` — promote `asyncio` |
| **Edit** | `tools/quick_report_tools.py` — promote `get_backend` |
| **Edit** | `backend/desktop/_discovery.py` — consolidate top-level sapsucker imports |

## Verification

- `pylint src/sapguimcp` scores 10.00/10
- `mypy --strict src/sapguimcp` passes
- `isort --check` and `black --check` pass
- All unit tests pass
- Count of `import-outside-toplevel` disables drops from ~63 to ~28
- No new `cyclic-import` warnings from pylint
