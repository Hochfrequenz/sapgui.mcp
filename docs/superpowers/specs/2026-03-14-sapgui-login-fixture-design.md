# SAP GUI Desktop Login Fixture — Design Spec

## Goal

A reusable login/logoff helper for the pysapgui library, plus a pytest fixture for desktop integration tests. Handles the full lifecycle: launch SAP GUI if needed → open connection → fill login screen → handle "multiple logon" popup → yield session → logoff on teardown.

## Non-Goals

- Desktop backend adapter (separate spec)
- Transaction navigation or screen interaction beyond login/logoff
- Multi-connection management (one connection at a time)

## New Environment Variable

```
SAP_CONNECTION_NAME=HF S/4
```

Added to `SapGuiSettings` in `models/config.py` and `.env.example`. Also added to `clean_environment` in `unittests/conftest.py`. This is the SAP Logon entry name passed to `app.open_connection(name)`.

## Package Location

```
src/sapguimcp/sapgui/
  _login.py              # login(), logoff(), _handle_multiple_logon_popup()

unittests/sapgui/
  test_login.py          # unit tests (mocked COM)
  test_integration.py    # updated with login/logoff integration tests
```

## Login Flow

```
login(connection_name, client, user, password, language, saplogon_exe_path?) -> GuiSession
```

### Step 1: Ensure SAP GUI is running

```python
try:
    app = SapGui.connect()
except SapConnectionError:
    app = SapGui.launch(exe_path=saplogon_exe_path or _default_saplogon_path())
```

`_default_saplogon_path()` returns `C:\Program Files\SAP\FrontEnd\SAPGUI\saplogon.exe` (the standard install path). Can be overridden via parameter.

Note: `SapGui.launch()` raises `SapGuiTimeoutError` (not `SapConnectionError`) if SAP GUI doesn't become available within the timeout.

### Step 2: Open connection

```python
conn = app.open_connection(connection_name, sync=True)
# open_connection returns GuiComponent via wrap_com_object; in practice it's a GuiConnection (type 11)
```

This opens a new SAP GUI window. The connection appears as `con[N]` in the COM tree.

Wait for the first session to become available (the login screen), using the wrapped Python API:

```python
# Poll until len(conn.children) > 0, following the same time.monotonic() pattern as _wait_for_sap_gui
session = _wait_for_session(conn, timeout=30)  # raises SapGuiTimeoutError on timeout
```

### Step 3: Detect and fill login screen

The login screen is program `SAPMSYST`, screen `20` (sometimes `500` for newer systems). Detected via `session.info.program == "SAPMSYST"`.

Field IDs (standard on ALL SAP systems):
| Field | ID | Type |
|-------|----|------|
| Client | `wnd[0]/usr/txtRSYST-MANDT` | GuiTextField |
| User | `wnd[0]/usr/txtRSYST-BNAME` | GuiTextField |
| Password | `wnd[0]/usr/pwdRSYST-BCODE` | GuiPasswordField |
| Language | `wnd[0]/usr/txtRSYST-LANGU` | GuiTextField |

```python
session.find_by_id("wnd[0]/usr/txtRSYST-MANDT").text = client
session.find_by_id("wnd[0]/usr/txtRSYST-BNAME").text = user
session.find_by_id("wnd[0]/usr/pwdRSYST-BCODE").text = password
session.find_by_id("wnd[0]/usr/txtRSYST-LANGU").text = language
session.find_by_id("wnd[0]").send_v_key(0)  # Enter
```

### Step 4: Handle "multiple logon" popup

After pressing Enter on the login screen, SAP may show the "Lizenzinformation bei Mehrfachanmeldung" popup (GuiModalWindow at `wnd[1]`).

Detection: check if `wnd[1]` exists and contains `radMULTI_LOGON_OPT2`.

**Always explicitly select OPT2** ("continue without ending other sessions") — the default selection is not stable across SAP versions/states.

```python
popup = session.find_by_id("wnd[1]", raise_error=False)
if popup is not None:
    opt2 = session.find_by_id("wnd[1]/usr/radMULTI_LOGON_OPT2", raise_error=False)
    if opt2 is not None:
        opt2.selected = True
        session.find_by_id("wnd[1]").send_v_key(0)  # Enter
```

Popup field IDs (captured from live HF S/4, S4U client 100):
| Element | ID |
|---------|----|
| Option 1 (end all others — destructive) | `radMULTI_LOGON_OPT1` |
| Option 2 (continue, keep others) | `radMULTI_LOGON_OPT2` |
| Option 3 (cancel login) | `radMULTI_LOGON_OPT3` |

### Step 5: Verify login succeeded

After login (and optional popup dismissal), verify we're past the login screen:

```python
if session.info.program == "SAPMSYST":
    sbar = session.find_by_id("wnd[0]/sbar")
    raise SapConnectionError(f"Login failed: {sbar.text}")
```

Check statusbar for error messages:

```python
sbar = session.find_by_id("wnd[0]/sbar")
if sbar.message_type == "E":
    raise SapConnectionError(f"Login failed: {sbar.text}")
```

Return the session.

## Logoff Flow

```
logoff(session) -> None
```

Use `send_command` for a clean logoff:

```python
session.send_command("/nEX")
```

If SAP shows an "unsaved data" popup, dismiss it:

```python
try:
    popup = session.find_by_id("wnd[1]", raise_error=False)
    if popup is not None:
        session.find_by_id("wnd[1]").send_v_key(0)  # Confirm
except Exception:
    pass  # Session may already be closed after /nEX
```

## Pytest Fixture

```python
# unittests/sapgui/conftest.py

@pytest.fixture
def sap_desktop_session():
    """Login to SAP GUI desktop, yield session, logoff on teardown.

    Requires SAP_CONNECTION_NAME, SAP_USER, SAP_PASSWORD, SAP_MANDANT,
    SAP_LANGUAGE in .env or environment.
    """
    if not is_sap_integration_test_machine():
        pytest.skip("SAP integration tests only run on authorized machines")

    settings = get_settings()
    if not settings.sap_connection_name:
        pytest.skip("SAP_CONNECTION_NAME not set")
    if not settings.sap_user or not settings.sap_password:
        pytest.skip("SAP_USER and SAP_PASSWORD must be set for desktop login")
    if not settings.sap_mandant:
        pytest.skip("SAP_MANDANT must be set for desktop login")

    session = login(
        connection_name=settings.sap_connection_name,
        client=settings.sap_mandant,
        user=settings.sap_user,
        password=settings.sap_password,
        language=settings.sap_language,
    )
    yield session
    logoff(session)
```

Function-scoped (default) — each test gets a fresh login/logoff cycle.

## Error Handling

- `SapGuiTimeoutError`: SAP GUI not running and launch timed out, or session didn't become available
- `ScriptingDisabledError`: Server has scripting disabled (existing check in `_com.py`)
- `SapConnectionError("Login failed: ...")`: Wrong credentials or SAP error on login screen

## What Changes in Existing Code

- `models/config.py`: Add `sap_connection_name: str = ""` field
- `.env.example`: Add `SAP_CONNECTION_NAME=` line
- `unittests/conftest.py`: Add `SAP_CONNECTION_NAME` to `clean_environment` fixture
- `sapgui/_login.py`: New file with `login()`, `logoff()`, helper functions
- `unittests/sapgui/conftest.py`: Add `sap_desktop_session` fixture
- `unittests/sapgui/test_login.py`: New test file
- `unittests/sapgui/test_integration.py`: Add login/logoff integration tests
