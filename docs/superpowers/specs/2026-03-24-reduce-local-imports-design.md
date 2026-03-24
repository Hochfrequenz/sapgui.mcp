# Reduce Local Imports

**Date:** 2026-03-24
**Status:** Approved
**Issue:** The codebase has 64 local (lazy) imports scattered across `src/sapwebguimcp/`. Most exist to work around circular dependency chains or because imports were never promoted to top-level. This spec describes how to reduce them to ~20, keeping only those justified by platform constraints or concrete-class access patterns.

## Problem

61 lines with `# pylint: disable=import-outside-toplevel` across 22 files. The root causes are:

1. **One circular chain:** `desktop/__init__.py` → `tools/sap_list_connections_impl.py` → `backend/manager.py` → `desktop/__init__.py`. This forces `manager.py` to lazily import both backend implementations, and `desktop/__init__.py` to lazily import result models and config.
2. **No protocol-level backend type check:** `_is_desktop_backend()` imports `DesktopBackend` at call time to do `isinstance()`.
3. **Imports that are local for no structural reason:** `time`, `asyncio`, `PlaywrightError`, sapsucker components, result models — all safe to import at module level.

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

This breaks the only circular chain: `desktop/__init__.py` no longer imports from `tools/`. With the cycle gone, `manager.py` can import both backends at top-level (conditionally on `sys.platform` for desktop), and `desktop/__init__.py` can import result models and `get_settings` at top-level.

**Eliminates:** ~5 lazy imports in `manager.py`, ~8 lazy imports in `desktop/__init__.py`.

### Part 3: Promote trivially-local imports to top-level

| Import | Files | Count |
|--------|-------|-------|
| `time` | se09_tools.py, se11_tools.py | 4 |
| `asyncio` | spro_tools.py | 2 |
| `PlaywrightError` | webgui/backend.py | 2 |
| `SapFieldType` | webgui/backend.py | 1 |
| `get_browser_manager` | webgui/backend.py | 1 |
| `get_settings` | desktop/__init__.py | 2 |

**Eliminates:** ~12 lazy imports.

### Part 4: Consolidate sapsucker/platform imports

In `desktop/__init__.py` and `_discovery.py`, replace multiple scattered lazy `from sapsucker.components.grid import GuiGridView` with a single top-level block:

```python
try:
    from sapsucker.components.grid import GuiGridView
except ImportError:
    GuiGridView = None  # type: ignore[misc,assignment]
```

Similarly for `_flatten` from `_element_finder` (already a sibling module, no circular risk).

**Eliminates:** ~6 lazy imports.

### What stays local (~20 imports)

These are justified and should remain:

| Import | File(s) | Reason |
|--------|---------|--------|
| `DesktopBackend` | 12 tool helper functions | Need concrete class for `._com`, `._require_session()` private API access |
| `pythoncom` | `_com_thread.py` | Runtime `if self._init_com` platform guard |
| `winreg` | `sap_list_connections_impl.py` | `sys.platform == "win32"` guard |
| `wrap_com_object` | `desktop/__init__.py` | COM thread callback, sapsucker internal |
| `server` | `__init__.py` | `__getattr__` lazy module loading |
| `_sapwebguimcp_version` | `server.py` | Generated file, may not exist |
| `open_and_discover_clients` | `desktop/__init__.py` | Heavy import chain, called rarely |

## File changes

| Action | File |
|--------|------|
| **Edit** | `backend/protocol.py` — add `backend_type` property |
| **Edit** | `backend/desktop/__init__.py` — implement property, promote imports |
| **Edit** | `backend/webgui/backend.py` — implement property, promote imports |
| **Create** | `backend/desktop/_landscape.py` — move landscape XML parsing here |
| **Edit** | `tools/sap_list_connections_impl.py` — import from `_landscape.py` |
| **Edit** | `backend/manager.py` — promote backend imports to top-level |
| **Edit** | `tools/_backend_utils.py` — use `backend_type` property |
| **Edit** | `tools/se09_tools.py`, `se11_tools.py` — promote `time` |
| **Edit** | `tools/spro_tools.py` — promote `asyncio` |
| **Edit** | `backend/desktop/_discovery.py` — consolidate sapsucker imports |

## Verification

- `pylint src/sapwebguimcp` scores 10.00/10
- `mypy --strict src/sapwebguimcp` passes
- `isort --check` and `black --check` pass
- All unit tests pass
- Count of `import-outside-toplevel` disables drops from 64 to ~20
- No new `cyclic-import` warnings from pylint
