# SAP Test Prerequisites

This document describes everything needed to run integration tests on a fresh SAP system. The integration tests drive SAP GUI for Windows, so you need a Windows machine with SAP GUI.

## SAP System Configuration

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

| Object                              | Transaction | Details                                                                                                                                                              |
| ----------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Report `ZTEST_MCP_EDIT`             | SE38        | Must contain `REPORT ZTEST_MCP_EDIT.` + `WRITE 'MCP test report'.`                                                                                                   |
| Function module `Z_MCP_TEST_FM`     | SE37        | In function group `Z_MCP_TEST_FUNKTIONSGRUPPE`; must contain `FUNCTION Z_MCP_TEST_FM.` + `WRITE 'MCP test FM'.` + `ENDFUNCTION.` (SE37 edit tests)                   |
| Class `ZCL_TEST_MCP_EDIT`           | SE24        | Public class with method `DO_SOMETHING`                                                                                                                              |
| Class `ZCL_SAPGUIMCP_ORIGLANG_TEST` | SE24        | Local (`$TMP`) class with original language **EN**, i.e. different from the DE logon language of the test user (optional: the language dialog test skips without it) |

The `sap_modify_cell` live tests (`unittests/desktop/test_modify_cell_integration.py`) use SAP's demo report
`BCALV_EDIT_01` (an editable ALV grid over table `SFLIGHT`, no save function). It needs flight demo data in `SFLIGHT`;
an empty table can be filled with SAP's report `SAPBC_DATA_GENERATOR`.

Creating these objects generates **transport requests** owned by the test user (needed for SE09 tests).

Create `ZCL_SAPGUIMCP_ORIGLANG_TEST` **logged on in EN** (SE24, Create, Local Object, activate), because SAP takes the original language from the logon language. Creating it through ADT does not work: ADT uses the configured DE logon language, so `TADIR-MASTERLANG` would be `D`. Verify with `SELECT MASTERLANG FROM TADIR WHERE PGMID = 'R3TR' AND OBJECT = 'CLAS' AND OBJ_NAME = 'ZCL_SAPGUIMCP_ORIGLANG_TEST'` (expected `E`). Switching it to change mode in a DE session shows the dialog `SAPLSETX` 0100 ("Abweichende Original- und Anmeldesprache", #1087).

> **Note**: The ABAP editor exists in two flavours, selected per user in
> _SE38 → Hilfsmittel/Utilities → Einstellungen/Settings → ABAP Editor → Editor_:
> "Quellcode-basierter Editor" drives the `GuiAbapEditor` control, "Text-basierter Editor"
> the `GuiTextedit` control. The backend takes a different code path for each
> (see `src/sapguimcp/backend/desktop/_abap_editor.py`), so the edit tests only cover the
> flavour the test user has configured. Issue #859 only affected `GuiAbapEditor`. To cover
> both, run the desktop edit tests once per setting.

> **Note**: Test object names are centralized in `unittests/desktop/conftest.py` (`TEST_REPORT`, `TEST_FUNCTION_MODULE`, `TEST_CLASS`, `TEST_METHOD`). If you use different names, update them there.

### abapGit test repositories

Two public GitHub repositories (`Hochfrequenz/...`) back the abapGit and edit tests. They must be registered in abapGit on the SAP system as follows:

| Repository                         | Must be registered in abapGit on                                                                        | Used by                   | Branches                     |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------- | ---------------------------- |
| `Z_PUBLIC_ABAPGIT_TEST_REPOSITORY` | S/4HANA systems (required). ERP 6.0 systems: optional, the dependent desktop tests skip if it is absent | abapGit integration tests | `main`, `test/branch-switch` |
| `Z_MCP_TEST_EDITABLE_WB_OBJECTS`   | all system types (provides `ZTEST_MCP_EDIT`, `Z_MCP_TEST_FM`, `ZCL_TEST_MCP_EDIT`)                      | edit / SE09 tests         | `main`, `test/branch-switch` |

- Desktop tests that need `Z_PUBLIC_ABAPGIT_TEST_REPOSITORY` (`test_abapgit_pull_public_repo`, `test_abapgit_pull_returns_status_message`, `test_abapgit_pull_without_trkorr_returns_transport_guidance`, `test_abapgit_list_repos`) first list the registered repositories and skip with a reason naming the repository if it is missing. They skip only when the listing succeeded and returned at least one repository; a failed or empty listing never causes a skip, so a broken listing still fails visibly. The repository name is matched exactly.
- `test/branch-switch` is a copy of `main` with a changed `WRITE` text. It is used by the live tests of the `branch` parameter of `sap_abapgit_pull` (`test_abapgit_pull_unknown_branch_leaves_branch_unchanged`, `test_abapgit_pull_branch_failure_restores_previous_branch`, `test_abapgit_pull_branch_switch_and_back`): do not delete it and do not merge it into `main`.
- Those tests need the optional `P_BRANCH` parameter of the report `Z_ABAPGIT_PULL_MCP_SHORTCUT` (merged; the report must be installed in a version that has it). Without it the branch pull is reported as not confirmed.
- The pull-by-key tests (`test_abapgit_pull_by_key`, `test_abapgit_pull_by_key_with_branch`, `test_abapgit_pull_by_key_updates_last_pull`, `test_abapgit_pull_by_unknown_key`) need the `P_KEY` parameter of the report: install `Z_ABAPGIT_PULL_MCP_SHORTCUT` at main commit 4cab3b7 or later on every test system. The first three need `Z_PUBLIC_ABAPGIT_TEST_REPOSITORY` registered as an **online** repository on a client that allows repository changes; the unknown-key test needs neither.
- `Z_PUBLIC_ABAPGIT_TEST_REPOSITORY` must not be pinned to a commit: a successful pull with a branch clears the pin, and the client can neither read nor restore it. The branch tests always leave the repository on its original branch.

### Optional Environment Variables

Some live tests need values that are specific to your SAP system. They have no defaults; tests that need an unset variable are skipped.

| Variable                     | Used by                                         | Meaning                                                                         |
| ---------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------- |
| `SAP_TEST_TRANSPORT`         | abapGit pull/e2e tests                          | A modifiable workbench transport request on which the test user has a task      |
| `SAP_TEST_TRANSPORT_NO_TASK` | `test_abapgit_pull_transport_without_user_task` | A modifiable workbench transport request on which the test user has **no** task |

The SE09 and ST22 live tests use the user returned by `sap_login`, so no user variable is needed.

## SAP GUI Setup

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

`.env` only needs the logon language the tests use:

```env
SAP_LANGUAGE=DE
```

The connection name, user, password, and mandant are read from `systems.json`.

`test_parallel_multi_client_integration.py` logs on to a second client in parallel. It uses any `systems.json` entry that has the same `connection_name` as the default system and a different client, and skips when there is none.

### Running the Tests

Every test that requests the `backend` or `sap_mcp_client` fixture is marked `integration` automatically (see `unittests/conftest.py`). Use `-m integration` to run only live tests and `-m "not integration"` to exclude them. Marked tests generally still skip when SAP is not configured (some desktop files only gate on the Windows platform).

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

### Troubleshooting

| Problem                                            | Solution                                                                            |
| -------------------------------------------------- | ----------------------------------------------------------------------------------- |
| "Scripting is disabled on the server"              | RZ11: set `sapgui/user_scripting = TRUE`, then re-login                             |
| "SAP Logon connection entry not found"             | Check `default_system` in `systems.json` matches the exact description in SAP Logon |
| SE38 edit tests read only 1 line                   | Switch to "text-based editor" in SE38 settings (R/3 only)                           |
| SE09 tests fail — no transport requests            | Create the test objects above (generates transports automatically)                  |
| "The 'Sapgui Component' could not be instantiated" | SAP server may be down or unreachable. Check VPN.                                   |
| Ghost connections block login                      | Restart SAP Logon or close stale connections manually                               |
