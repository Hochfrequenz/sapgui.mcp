# abapGit Pull via API - Design & Implementation Plan

## Background

### Problem

The abapGit web UI automation is fragile:

- Multiple dialogs (object selection, transport request) require complex DOM manipulation
- Custom checkbox elements, popups, and timing issues make automation unreliable
- Each abapGit version may change the UI structure

### Solution

Use the abapGit ABAP API directly via a custom report:

- Stable API that won't change with UI updates
- Direct control over authentication and transport handling
- Clear error messages via SAP status bar (readable by MCP tools)

### References

- abapGit API docs: https://docs.abapgit.org/development-guide/api/api.html
- Key classes: `zcl_abapgit_repo_srv`, `zcl_abapgit_repo_online`, `zcl_abapgit_login_manager`

---

## ABAP Report: Z_ABAPGIT_PULL

### Source Code

```abap
*&---------------------------------------------------------------------*
*& Report Z_ABAPGIT_PULL
*&---------------------------------------------------------------------*
*& Pull changes from an abapGit repository using the abapGit API.
*& Designed to be called via transaction for MCP automation.
*&
*& Parameters:
*&   P_REPO   - Repository name (pattern match against registered repos)
*&   P_USER   - GitHub username (optional for public repos)
*&   P_TOKEN  - GitHub PAT token (optional for public repos)
*&   P_TRKORR - Transport request (optional, error if required but missing)
*&
*& Status bar messages:
*&   Success: "Pull successful: <repo_name>"
*&   Error:   "Repository not found: <pattern>"
*&   Error:   "Transport required. Provide P_TRKORR=<type>"
*&   Error:   "<exception message>"
*&---------------------------------------------------------------------*
REPORT z_abapgit_pull.

PARAMETERS:
  p_repo   TYPE string LOWER CASE OBLIGATORY,
  p_user   TYPE string LOWER CASE,
  p_token  TYPE string LOWER CASE,
  p_trkorr TYPE trkorr.

START-OF-SELECTION.
  TRY.
      " 1. Find repository by name pattern
      DATA lo_repo TYPE REF TO zcl_abapgit_repo_online.

      LOOP AT zcl_abapgit_repo_srv=>get_instance( )->list( iv_offline = abap_false ) INTO DATA(li_repo).
        IF li_repo->get_name( ) CS p_repo.
          lo_repo ?= li_repo.
          EXIT.
        ENDIF.
      ENDLOOP.

      IF lo_repo IS NOT BOUND.
        MESSAGE e398(00) WITH 'Repository not found:' p_repo '' ''.
        RETURN.
      ENDIF.

      " 2. Set credentials if provided (required for private repos)
      IF p_user IS NOT INITIAL AND p_token IS NOT INITIAL.
        zcl_abapgit_login_manager=>set(
          iv_uri      = lo_repo->get_url( )
          iv_username = p_user
          iv_password = p_token ).
      ENDIF.

      " 3. Run pre-pull checks
      DATA(ls_checks) = lo_repo->deserialize_checks( ).

      " 4. Handle transport request
      IF ls_checks-transport-required = abap_true AND p_trkorr IS INITIAL.
        MESSAGE e398(00) WITH 'Transport required. Provide P_TRKORR=' ls_checks-transport-type '' ''.
        RETURN.
      ENDIF.
      ls_checks-transport-transport = p_trkorr.

      " 5. Execute pull (deserialize from remote to local)
      lo_repo->deserialize(
        is_checks = ls_checks
        ii_log    = NEW zcl_abapgit_log( ) ).

      MESSAGE s398(00) WITH 'Pull successful:' lo_repo->get_name( ) '' ''.

    CATCH cx_root INTO DATA(lx_error).
      MESSAGE e398(00) WITH lx_error->get_text( ) '' '' ''.
  ENDTRY.
```

---

## Manual Steps in SAP

### Step 1: Create the Report (SE38)

1. **Go to SE38** (ABAP Editor)
2. **Enter program name:** `Z_ABAPGIT_PULL`
3. **Click Create**
4. **Fill attributes:**
    - Title: `abapGit Pull via API`
    - Type: `Executable program`
    - Status: `Test program` (or Customer production)
5. **Paste the source code** from above
6. **Save** (assign to package or $TMP for testing)
7. **Activate** (Ctrl+F3)

### Step 2: Test the Report (SE38)

1. **Execute** the report (F8)
2. **Enter test values:**
    - P_REPO: `Z_PUBLIC_ABAPGIT_TEST_REPOSITORY` (or part of name)
    - P_USER: (leave empty for public repo)
    - P_TOKEN: (leave empty for public repo)
    - P_TRKORR: (leave empty first, add if error says required)
3. **Run** and check status bar for result

### Step 3: Create Transaction (SE93)

1. **Go to SE93** (Transaction Maintenance)
2. **Enter transaction code:** `ZABAPGIT_PULL`
3. **Click Create**
4. **Select:** `Program and selection screen (report transaction)`
5. **Fill details:**
    - Short text: `abapGit Pull via API`
    - Program: `Z_ABAPGIT_PULL`
    - Selection screen: (leave empty for default)
6. **Save** (assign to package or $TMP)

### Step 4: Test Transaction

1. **Enter** `/nZABAPGIT_PULL` in command field
2. **Verify** the selection screen appears with parameters
3. **Test** with same values as Step 2

---

## MCP Tool Integration

Once the transaction works, the MCP tool can call it like this:

```python
# 1. Navigate to transaction
await sap_transaction("ZABAPGIT_PULL")

# 2. Fill the selection screen
await sap_fill_form({
    "P_REPO": "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
    "P_USER": "",  # optional
    "P_TOKEN": "",  # optional
    "P_TRKORR": "",  # optional
})

# 3. Execute (F8)
await page.keyboard.press("F8")

# 4. Read status bar for result
status = await sap_read_status_bar()
# status.message contains "Pull successful: ..." or error
```

---

## Verification (unchanged)

After pull, verify in SE38:

1. Navigate to SE38
2. Enter report name (e.g., `Z_REPORT_IN_PUBLIC_GIT_REPO`)
3. Press F7 (Display)
4. Read source code and check for expected changes

---

## Implementation Notes

### Transaction Name

The transaction was created as `Z_ABAPGIT_PULL` (same name as the report), not `ZABAPGIT_PULL`.

### Parameter Passing

Instead of using `sap_fill_form` (which requires label matching), parameters are passed directly via the OK-Code field:

```
/nZ_ABAPGIT_PULL P_REPO=value; P_TRKORR=value; P_USER=value; P_TOKEN=value;
```

### Overwrite Decisions

The abapGit API requires explicit overwrite decisions. The report auto-confirms all overwrites:

```abap
LOOP AT ls_checks-overwrite ASSIGNING FIELD-SYMBOL(<ls_overwrite>).
  <ls_overwrite>-decision = 'Y'.
ENDLOOP.
```

### Source Code Location

The ABAP report source is maintained in a git submodule:

- `unittests/abapgit_repos/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY/src/z_abapgit_pull.prog.abap`

---

## Checklist

- [x] Report Z_ABAPGIT_PULL created and activated in SE38
- [x] Report tested successfully with public repo
- [x] Report tested with private repo (PAT authentication)
- [x] Transaction Z_ABAPGIT_PULL created in SE93
- [x] Transaction tested from command line
- [x] MCP tool updated to use new transaction
- [x] E2E test for public repo passing
- [x] E2E test for private repo passing
