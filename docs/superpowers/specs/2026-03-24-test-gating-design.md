# Replace Hostname-Based Test Gating with Credential Detection

**Date:** 2026-03-24
**Status:** Approved

## Problem

Integration tests are gated by `is_sap_integration_test_machine()` which checks `socket.gethostname()` against 3 hardcoded Hochfrequenz machine names (`HF-KKLEIN3`, `HF-MeiskeJ`, `HFDACHNERMR`). This means:

- New developers with SAP access can't run integration tests without editing source code
- The mechanism is undocumented and surprising
- Two separate skip markers (`skip_not_sap` + `skip_no_creds`) are redundant — credentials already imply SAP access

## Design

### Replace hostname check with credential detection

Remove `_AUTHORIZED_SAP_TEST_MACHINES` and `is_sap_integration_test_machine()` entirely. Replace with two credential-check functions:

- `has_sap_desktop_creds()` → True if `SAP_USER` + `SAP_PASSWORD` + `SAP_MANDANT` + `SAP_CONNECTION_NAME` are all non-empty
- `has_sap_webgui_creds()` → True if `SAP_USER` + `SAP_PASSWORD` + `SAP_MANDANT` + `SAP_URL` are all non-empty

### Merge skip markers

Desktop tests currently use two markers: `@skip_not_sap` (hostname) + `@skip_no_creds` (credentials). Replace both with a single `skip_no_sap` marker that uses `has_sap_desktop_creds()`.

WebGUI's `sap_mcp_client` fixture already checks `SAP_URL` — just remove the hostname check from it and add a credential check.

### Expand `tox -e unit_tests`

Currently runs only 3 parser test files. Expand to include all offline tests: root-level `unittests/test_*.py` and desktop mock tests `unittests/desktop/test_desktop_backend.py`, `test_com_thread.py`, etc.

### Update ARCHITECTURE.md

Update the test section to document credential-based gating instead of hostname-based.

## Files

| File | Change |
|------|--------|
| `unittests/conftest.py` | Remove hostname set + function, add `has_sap_desktop_creds()` and `has_sap_webgui_creds()` |
| `unittests/desktop/conftest.py` | Replace `skip_not_sap` + `skip_no_creds` with single `skip_no_sap` |
| `unittests/webgui/conftest.py` | Remove hostname check from `sap_mcp_client`, use credential check |
| ~20 desktop integration test files | Replace `@skip_not_sap` / `@skip_no_creds` with `@skip_no_sap` |
| ~15 webgui integration test files | Remove hostname references if any |
| `tox.ini` | Expand `unit_tests` env to run all offline tests |
| `ARCHITECTURE.md` | Update test gating docs |
