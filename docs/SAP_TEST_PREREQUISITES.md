# SAP Test Prerequisites

This document describes everything needed to run the desktop integration tests on a fresh SAP system.

## SAP System Configuration

### Server Side

- **SAP GUI Scripting**: Transaction `RZ11` -> parameter `sapgui/user_scripting` -> set to `TRUE`
  - Dynamic parameter, no server restart needed
  - Users must re-login after the change (close and reopen SAP GUI)

### Client Side (Developer PC)

- **SAP GUI for Windows** installed
- **SAP GUI Scripting enabled**: Options -> Accessibility & Scripting -> Scripting
  - Check "Enable Scripting"
  - Uncheck "Notify when a script attaches to SAP GUI"
  - Uncheck "Notify when a script opens a connection"
- **R/3 only**: Switch ABAP editor to "text-based editor" (SE38 -> Hilfsmittel -> Einstellungen -> ABAP Editor -> "Text-basierter Editor"). The source-code-based editor does not fully expose content via COM scripting. See [#442](https://github.com/Hochfrequenz/sapwebgui.mcp/issues/442).

### User Permissions

The test user needs access to the following transactions:

| Transaction | Purpose |
|---|---|
| SE16 | Data Browser (table queries) |
| SE24 | Class Builder (class editor tests) |
| SE37 | Function Builder (function module tests) |
| SE38 | ABAP Editor (report editor tests) |
| SE09 | Transport Organizer (transport request tests) |
| SE93 | Transaction Maintenance (tcode lookup tests) |
| SM37 | Job Overview (background job tests) |
| SLG1 | Application Log (log reader tests) |
| SM30 | Table Maintenance (view maintenance tests) |
| SPRO | Customizing (IMG tree search tests) |
| ST22 | ABAP Dumps (dump analysis tests) |
| BP | Business Partner (BDT screen tests) |

## Test Objects

The required test objects are maintained in an abapGit repository:

**https://github.com/Hochfrequenz/Z_MCP_TEST_EDITABLE_WB_OBJECTS**

Install via abapGit pull, or create manually:

| Object | Transaction | Details |
|---|---|---|
| Report `ZTEST_MCP_EDIT` | SE38 | Must contain `REPORT ZTEST_MCP_EDIT.` + `WRITE 'MCP test report'.` |
| Class `ZCL_TEST_MCP_EDIT` | SE24 | Public class with method `DO_SOMETHING` |
| Function module `Z_MCP_TEST_FM` | SE37 | In function group `ZMCP_TEST` |

Creating these objects will also generate **transport requests** owned by the test user, which are needed for the SE09 tests.

> **Note**: The test object names are centralized in `unittests/desktop/conftest.py` (`TEST_REPORT`, `TEST_CLASS`, `TEST_METHOD`). If you use different names, update them there.

## .env Configuration

Create a `.env` file in the project root:

```env
# Desktop backend
BACKEND_TYPE=desktop
SAP_CONNECTION_NAME=Your SAP Logon Entry
SAP_USER=your_username
SAP_PASSWORD=your_password
SAP_MANDANT=100
SAP_LANGUAGE=DE

# WebGUI backend (alternative)
# BACKEND_TYPE=webgui
# SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui
# BROWSER_MODE=connect
# CDP_URL=http://localhost:9222
```

`SAP_CONNECTION_NAME` is the **description text** shown in SAP Logon (the bold text in the list), not the system ID or server address.

## Running Tests

```bash
# All desktop integration tests (requires SAP connection)
python -m pytest unittests/desktop/ -v

# Specific test module
python -m pytest unittests/desktop/test_bp_integration.py -v

# Unit tests only (no SAP needed)
python -m pytest unittests/desktop/test_com_evaluate_unit.py unittests/desktop/test_dump_tree_unit.py unittests/desktop/test_element_finder.py -v
```

Tests auto-skip when SAP is not available (`skip_not_sap`) or credentials are missing (`skip_no_creds`).

## Troubleshooting

| Problem | Solution |
|---|---|
| "Scripting is disabled on the server" | RZ11: set `sapgui/user_scripting = TRUE`, then re-login |
| "SAP Logon connection entry not found" | Check `SAP_CONNECTION_NAME` matches the exact description in SAP Logon |
| SE38 edit tests read only 1 line | Switch to "text-based editor" in SE38 settings (R/3 only) |
| SE09 tests fail — no transport requests | Create the test objects above (generates transports automatically) |
| "The 'Sapgui Component' could not be instantiated" | SAP server may be down or unreachable. Check VPN. |
| Ghost connections block login | Restart SAP Logon or close stale connections manually |
