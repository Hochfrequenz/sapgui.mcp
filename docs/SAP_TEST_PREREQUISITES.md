# SAP Test Prerequisites

This document describes everything needed to run integration tests on a fresh SAP system. The test suite supports two backends — set up whichever you'll be developing against (or both).

## SAP System Configuration (both backends)

### User Permissions

The test user needs access to the following transactions:

| Transaction | Purpose                                       |
| ----------- | --------------------------------------------- |
| SE16        | Data Browser (table queries)                  |
| SE24        | Class Builder (class editor tests)            |
| SE37        | Function Builder (function module tests)      |
| SE38        | ABAP Editor (report editor tests)             |
| SE09        | Transport Organizer (transport request tests) |
| SE93        | Transaction Maintenance (tcode lookup tests)  |
| SM37        | Job Overview (background job tests)           |
| SLG1        | Application Log (log reader tests)            |
| SM30        | Table Maintenance (view maintenance tests)    |
| SPRO        | Customizing (IMG tree search tests)           |
| ST22        | ABAP Dumps (dump analysis tests)              |
| BP          | Business Partner (BDT screen tests)           |

### Test Objects

The required test objects are maintained in an abapGit repository:

**https://github.com/Hochfrequenz/Z_MCP_TEST_EDITABLE_WB_OBJECTS**

Install via abapGit pull, or create manually:

| Object                    | Transaction | Details                                                            |
| ------------------------- | ----------- | ------------------------------------------------------------------ |
| Report `ZTEST_MCP_EDIT`   | SE38        | Must contain `REPORT ZTEST_MCP_EDIT.` + `WRITE 'MCP test report'.` |
| Class `ZCL_TEST_MCP_EDIT` | SE24        | Public class with method `DO_SOMETHING`                            |

Creating these objects generates **transport requests** owned by the test user (needed for SE09 tests).

> **Note**: Test object names are centralized in `unittests/desktop/conftest.py` (`TEST_REPORT`, `TEST_CLASS`, `TEST_METHOD`). If you use different names, update them there.

## Desktop Backend Setup

### Server Side

- **SAP GUI Scripting**: Transaction `RZ11` → parameter `sapgui/user_scripting` → set to `TRUE`
    - Dynamic parameter, no server restart needed
    - Users must re-login after the change (close and reopen SAP GUI)

### Client Side

- **SAP GUI for Windows** installed
- **SAP GUI Scripting enabled**: Options → Accessibility & Scripting → Scripting
    - Check "Enable Scripting"
    - Uncheck "Notify when a script attaches to SAP GUI"
    - Uncheck "Notify when a script opens a connection"
- **R/3 only**: Switch ABAP editor to "text-based editor" (SE38 → Hilfsmittel → Einstellungen → ABAP Editor → "Text-basierter Editor"). The source-code-based editor does not fully expose content via COM scripting. See [#442](https://github.com/Hochfrequenz/sapgui.mcp/issues/442).

### Credentials Configuration

SAP credentials are configured in `~/.config/sap-mcp/systems.json` (see [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config)).

`.env` only needs the backend type and language:

```env
BACKEND_TYPE=desktop
SAP_LANGUAGE=DE
```

The connection name, user, password, and mandant are read from `systems.json`.

### Running Desktop Tests

```bash
# All desktop integration tests
python -m pytest unittests/desktop/ -v

# Specific module
python -m pytest unittests/desktop/test_bp_integration.py -v

# Unit tests only (no SAP needed)
python -m pytest unittests/desktop/test_com_evaluate_unit.py unittests/desktop/test_dump_tree_unit.py unittests/desktop/test_element_finder.py -v
```

### Troubleshooting (Desktop)

| Problem                                            | Solution                                                                            |
| -------------------------------------------------- | ----------------------------------------------------------------------------------- |
| "Scripting is disabled on the server"              | RZ11: set `sapgui/user_scripting = TRUE`, then re-login                             |
| "SAP Logon connection entry not found"             | Check `default_system` in `systems.json` matches the exact description in SAP Logon |
| SE38 edit tests read only 1 line                   | Switch to "text-based editor" in SE38 settings (R/3 only)                           |
| SE09 tests fail — no transport requests            | Create the test objects above (generates transports automatically)                  |
| "The 'Sapgui Component' could not be instantiated" | SAP server may be down or unreachable. Check VPN.                                   |
| Ghost connections block login                      | Restart SAP Logon or close stale connections manually                               |

## WebGUI Backend Setup

### Client Side

- **Chrome browser** installed
- **VPN** connected (if SAP system is on an internal network)

### Start Chrome with Remote Debugging

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
```

Verify it's working:

```powershell
Invoke-WebRequest -Uri 'http://localhost:9222/json/version' -UseBasicParsing
```

### Credentials Configuration

SAP credentials are configured in `~/.config/sap-mcp/systems.json` (see [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config)).

`.env` only needs the backend type, URL, and browser settings:

```env
BACKEND_TYPE=webgui
SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui
SAP_LANGUAGE=DE
BROWSER_MODE=connect
CDP_URL=http://localhost:9222
```

### Running WebGUI Tests

```bash
# All WebGUI integration tests
python -m pytest unittests/webgui/ -v

# Specific module
python -m pytest unittests/webgui/test_se16_integration.py -v

# Unit tests only (no SAP/Chrome needed — uses HTML snapshots)
python -m pytest unittests/webgui/test_selectors.py -v
```

### HTML Snapshots

WebGUI unit tests validate CSS selectors against captured HTML snapshots stored in `unittests/webgui/testdata/html_snapshots/`. These are system-specific — transport numbers, usernames, and other data in the snapshots come from the system they were captured on. If you switch to a new SAP system, re-capture snapshots by running integration tests with `SAP_LANGUAGE=DE` and `SAP_LANGUAGE=EN`.

### Troubleshooting (WebGUI)

| Problem                          | Solution                                                                   |
| -------------------------------- | -------------------------------------------------------------------------- |
| Chrome connection errors         | Ensure `--remote-debugging-port=9222` and `--user-data-dir` flags are set  |
| "Cannot connect to CDP"          | Check Chrome is running, verify with `http://localhost:9222/json/version`  |
| SAP login fails                  | Check `SAP_URL` is accessible in browser, verify credentials               |
| OK-Code field not visible        | Enable in SAP Web GUI settings (gear icon → Settings → Show OK-Code Field) |
| Tools timeout                    | SAP Web GUI can be slow; check Chrome window for SAP response              |
| Snapshot tests fail after system | Re-capture HTML snapshots: run integration tests, then run unit tests      |
