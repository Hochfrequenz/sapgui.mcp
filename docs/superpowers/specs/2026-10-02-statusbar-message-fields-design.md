# Status bar message class, number and parameters (#917, desktop)

## Problem

`sap_read_status_bar` returns only `type` and `message`. The type is not a reliable success
signal. Checked live: the "transaction does not exist" message came back as type `S` in one run
and `E` in another. Skills therefore match on the message text, which depends on the logon
language (see #883).

## Decision

On the **desktop backend**, `StatusBarInfo` additionally carries the T100 message identity read
from SAP GUI scripting through sapsucker >= 1.4.0 (Hochfrequenz/sapsucker#116). The WebGUI
backend is unchanged and leaves the new fields empty.

## Design

`StatusBarInfo` (`src/sapguimcp/models/sap_results.py`) gets three optional fields:

| Field                | Type          | Desktop value                                                                                                       |
| -------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------- |
| `message_id`         | `str \| None` | `GuiStatusbar.message_id` (message class, padding stripped, e.g. `"DS"`); `None` when empty                         |
| `message_number`     | `str \| None` | `GuiStatusbar.message_number` as returned (zero-padded, e.g. `"017"`); `None` when empty                            |
| `message_parameters` | `list[str]`   | `message_parameter(0..3)` (the T100 variables `&1`–`&4`), with trailing empty values removed; `[]` for an empty bar |

- `DesktopBackend.get_status_bar` reads the fields in the same `com.run` call that already reads
  the text and type. If a member raises, the new fields fall back to `None` / `[]`. The text and
  type behave exactly as today.
- The field descriptions explain that the class and number identify a message independently of
  the logon language. Skills should check these instead of the text, and both fields are
  desktop-only.
- The `sap_read_status_bar` tool description says the same thing.
- **No sandbox helper.** In `sap_run_script`, scripts can read
  `session.find_by_id("wnd[0]/sbar").message_id` (and the other fields) directly with
  sapsucker >= 1.4.0. The tool description gets one line saying so. Adding a helper would
  change the sandbox contract for no gain.
- The `sapsucker` pin moves to `>=1.4.0`.

## Tests

- **Unit:**
    - desktop `get_status_bar` with a fake status bar: values set, empty bar, trailing empty
      parameters trimmed, and a member raising leaves only the new fields empty;
    - the model defaults.
- **Live desktop** (required, run one at a time):
    - a nonexistent transaction (`/nZZNOSUCHTX`) gives message class `S#`, number `343`, and
      parameters `["ZZNOSUCHTX"]`;
    - SE38 display of a nonexistent program gives `DS`, `017`, and the program name as the
      parameter;
    - after `/n`, the bar is empty and the new fields are `None` / `[]`.

    The assertions use class and number only, never the text, so the tests pass in any logon
    language.

## Out of scope

The WebGUI backend, the sandbox helper, and the `MessageAsPopup` / `MessageHasLongText` flags.
