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

> **Note**: The ABAP editor exists in two flavours, selected per user in
> _SE38 → Hilfsmittel/Utilities → Einstellungen/Settings → ABAP Editor → Editor_:
> "Quellcode-basierter Editor" drives the `GuiAbapEditor` control, "Text-basierter Editor"
> the `GuiTextedit` control. The backend takes a different code path for each
> (see `src/sapguimcp/backend/desktop/_abap_editor.py`), so the edit tests only cover the
> flavour the test user has configured. Issue #859 only affected `GuiAbapEditor`. To cover
> both, run the desktop edit tests once per setting.

> **Note**: Test object names are centralized in `unittests/desktop/conftest.py` (`TEST_REPORT`, `TEST_CLASS`, `TEST_METHOD`). If you use different names, update them there.

### abapGit test repositories

Two public GitHub repositories (`Hochfrequenz/...`) back the abapGit and edit tests. They must be registered in abapGit on the SAP system as follows:

| Repository                         | Must be registered in abapGit on                                                                        | Used by                                     | Branches                     |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ---------------------------- |
| `Z_PUBLIC_ABAPGIT_TEST_REPOSITORY` | S/4HANA systems (required). ERP 6.0 systems: optional, the dependent desktop tests skip if it is absent | abapGit integration tests (desktop, WebGUI) | `main`, `test/branch-switch` |
| `Z_MCP_TEST_EDITABLE_WB_OBJECTS`   | all system types (provides `ZTEST_MCP_EDIT`, `ZCL_TEST_MCP_EDIT`)                                       | edit / SE09 tests                           | `main`, `test/branch-switch` |

- Desktop tests that need `Z_PUBLIC_ABAPGIT_TEST_REPOSITORY` (`test_abapgit_pull_public_repo`, `test_abapgit_pull_returns_status_message`, `test_abapgit_pull_without_trkorr_returns_transport_guidance`, `test_abapgit_list_repos`) first list the registered repositories and skip with a reason naming the repository if it is missing. They skip only when the listing succeeded and returned at least one repository; a failed or empty listing never causes a skip, so a broken listing still fails visibly. The repository name is matched exactly.
- `test/branch-switch` is a copy of `main` with a changed `WRITE` text. It is reserved for the upcoming live tests of an abapGit branch parameter: do not delete it and do not merge it into `main`.
- Those branch-switch tests will also need the optional `P_BRANCH` parameter of the report `Z_ABAPGIT_PULL_MCP_SHORTCUT` (open PR #12 in that repository).

### Optional Environment Variables

Some live tests need values that are specific to your SAP system. They have no defaults; tests that need an unset variable are skipped.

| Variable                     | Used by                                         | Meaning                                                                         |
| ---------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------- |
| `SAP_TEST_TRANSPORT`         | abapGit pull/e2e tests (WebGUI and desktop)     | A modifiable workbench transport request on which the test user has a task      |
| `SAP_TEST_TRANSPORT_NO_TASK` | `test_abapgit_pull_transport_without_user_task` | A modifiable workbench transport request on which the test user has **no** task |

The SE09 and ST22 live tests use the user returned by `sap_login`, so no user variable is needed.

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

The desktop integration fixture only closes the SAP GUI connections it (or the tools under test) opened itself.
Connections that were already open before the run, such as your own SAP GUI windows, are left untouched.

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
