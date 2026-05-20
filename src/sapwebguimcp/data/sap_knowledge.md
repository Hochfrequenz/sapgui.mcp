# SAP Web GUI Knowledge Base

This file contains domain knowledge, tips, and best practices for working with SAP Web GUI.
The content is loaded by `sap_get_capabilities()` and provided to the AI model.

## Finding Transactions: Use the Catalog First

**BEFORE guessing transaction codes or searching online**, use the `search_transactions` tool to search the local transaction catalog.

The catalog contains ~4,000 SAP transactions with descriptions, and searching it is:

- **Instant** - No network latency, no SAP session needed
- **Accurate** - Data scraped from the actual SAP system via SE93
- **Comprehensive** - Covers common areas: SD, MM, FI, CO, PP, BC, IS-U

**Example queries:**

- `search_transactions("sales order")` - Find sales order transactions
- `search_transactions("VA")` - Find all transactions starting with VA
- `search_transactions("customer", area="SD")` - Customer transactions in Sales & Distribution
- `search_transactions("Kundenauftrag")` - German keywords work too (catalog is in German)

**Only if the catalog doesn't help**, then:

1. Try online resources (help.sap.com via `browser_navigate` - see workaround below)
2. Use SE93 to look up unknown transaction codes
3. Ask the user for clarification

## MCP-Tools are Faster than manual evaluation

ALWAYS, before trying to use `browser_evaluate` or any other `browser_` tool, check if there is a dedicated MCP tool that does what you want.
MCP tools are optimized to work with SAP Web GUI and will be much faster and more reliable.
You can still manually evaluate JavaScript code if no MCP tool exists for your use case or if the tools don't work, but this should be the exception, not the rule.
In case it doesn't work use the respetive tool to submit feedback to improve the MCP tools.

## Keyboard Shortcuts

Always check `sap_get_shortcuts` before clicking buttons - shortcuts are faster and more reliable.

Common shortcuts (German keyboard labels shown, work the same on EN keyboards):

- **F3** - Back (Zurück)
- **F8** - Execute (Ausführen)
- **Ctrl+S** - Save (Sichern)
- **Shift+F3** - Exit completely (Beenden)
- **Enter** - Confirm current action
- **F4** - Open search help / value list which helps you to fill meaningful values to a field.
  Browser focus needs to be on the respective field before hitting F4.
  This opens a popup with available values - this is expected behavior, not an error.
  Read the values before closing the popup.

### `*` wildcards

Often to search something you can use `*` as wildcard.
So if you search say for a report in se38 which starts with "Z" and contains "energy" enter `Z*energy*` in the field, hit F4 and hope for results.

## When Stuck

1. **Check the status bar** - SAP shows errors, warnings, and info messages there
2. **Look for popups** - A popup may be waiting for your response - check if it's an error, confirmation, or help dialog
3. **Try F3 (Back)** - Often helps to back out and retry
4. **Reset to Easy Access first** - If inputs seem stuck or fields aren't being picked up, use `sap_transaction("YOUR_TCODE", reset_first=True)`. This navigates to SAP Easy Access (`/n`) first, clearing all residual state (popups, error messages, field values) before opening the transaction. This is the most reliable way to recover from state bleeding.
5. **Start over** - Either by restarting the transaction or using sap_login again (changes will be lost)

## Working with Modal Dialogs (Popups)

SAP often opens modal dialogs (popups) for confirmations, data entry forms,
transport prompts, and error messages. These appear at `wnd[1]` or `wnd[2]`.

**All tools automatically operate on the active window.** When a popup is open,
`sap_discover_fields`, `sap_get_form_fields`, `sap_fill_form`, `sap_press_key`,
and other tools target the popup — not the main window behind it.

**How to detect a popup opened:**
- Check the `active_window` field in tool results. `"wnd[0]"` means the main
  window; `"wnd[1]"` or higher means a modal dialog is open.
- After actions that change screen state (`sap_press_key`, `sap_fill_form`),
  always note the `active_window` value.

**Typical workflow:**
1. `sap_press_key(key="F5")` → result has `active_window="wnd[1]"` (dialog opened)
2. `sap_discover_fields()` → shows fields in the dialog
3. `sap_fill_form({...})` → fills dialog fields
4. `sap_press_key(key="Enter")` → result has `active_window="wnd[0]"` (dialog closed)

**To dismiss a dialog you don't need:** Use `sap_close_popup(close=True)` or
`sap_press_key(key="Escape")`.

**Cannot navigate while a dialog is open:** `sap_transaction()` will fail if a
modal dialog is present — dismiss it first.

### State Bleeding Between Transactions

SAP WebGUI can "bleed" state between sequential transactions. Symptoms:

- Fields don't accept new values (previous values persist)
- F7/F8 doesn't execute (SAP didn't register the field change)
- Status bar shows errors from the previous transaction

**Root cause:** SAP WebGUI hooks into low-level keyboard events (`keydown`/`keyup`), not the standard DOM `input`/`change` events that JavaScript-based field fills trigger. After navigating between transactions, SAP's internal model may not detect JS-only value changes.

**Solutions (in order of preference):**

1. **`reset_first=True`** - Use `sap_transaction("SE24", reset_first=True)` to navigate to Easy Access before entering the transaction. This clears all residual state.
2. **Manual `/n` reset** - Call `sap_press_key("Enter")` with `/n` in the OK-code field, then re-enter your transaction.
3. **Real keyboard typing** - If a field value isn't being picked up, try clearing the field and retyping the value manually using `sap_press_key` with individual keystrokes.

After you found out how to solve a specific problem without these workarounds, consider providing feedback to the devs.

## ABAP Development with Claude Code and abapGit

**The strongly preferred approach** for ABAP development is to use Claude Code together with abapGit.
Writing ABAP locally, pushing to Git, and pulling via abapGit is **much faster, more stable, and fully version-controlled**.
Always choose abapGit-based development when possible.

For objects in packages that are **not source-controlled via abapGit**, the edit tools (`sap_se38_edit`, `sap_se37_edit`, `sap_se24_edit`) allow in-place editing of existing ABAP reports, function modules, and class methods directly in SAP.
These are fallback options for quick modifications to objects that are not tracked in Git.
Using Git is always the preferred option — there should be no doubt about it.

### Setup

1. **Install abapGit in SAP** - Follow the [abapGit installation guide](https://docs.abapgit.org/user-guide/getting-started/install.html).
   See also [abapGit.org](https://abapgit.org/) for an overview.
2. **Install Claude Code** - Follow the [official documentation](https://docs.anthropic.com/en/docs/claude-code/overview)
3. **Configure the SAP WebGUI MCP Server** - Add this MCP server to your Claude Code configuration.
   See [MCP server setup](https://docs.anthropic.com/en/docs/claude-code/mcp-servers)
4. **Clone your abapGit repository** - Open Claude Code in the local repository directory where your ABAP code lives

### Finding abapGit in SAP

If you don't have a transaction code for abapGit yet:

1. **SE93** - Check if a transaction like `ZABAPGIT` already exists
2. **SE38** - Search for programs matching `*abap*git*` (e.g., `ZABAPGIT_STANDALONE`)
3. **Create transaction** - If needed, use SE93 to create a transaction code pointing to the abapGit program

### ⚠️ abapGit File Naming: Lowercase is Required

**All filenames in an abapGit repository MUST be lowercase.** abapGit serializes and expects filenames in lowercase. While ABAP object names are uppercase internally (e.g., `ZCL_MY_CLASS`), the corresponding files must be lowercase (e.g., `zcl_my_class.clas.abap`, `zcl_my_class.clas.xml`).

**Common mistake:** Creating files with uppercase names like `ZCL_MY_CLASS.clas.abap` — abapGit will fail with:

```
File not found: zcl_my_class.clas.xml
Import of object ZCL_MY_CLASS failed
```

**Fix:** Rename all files to lowercase. Use `git mv` to rename (not just the filesystem) so Git tracks the change:

```bash
git mv src/ZCL_MY_CLASS.clas.abap src/zcl_my_class.clas.abap
git mv src/ZCL_MY_CLASS.clas.xml src/zcl_my_class.clas.xml
```

### Development Workflow

1. **Write code in Claude Code** - Let Claude Code generate/modify your ABAP code locally
2. **Push to Git** - Commit and push your changes to the Git repository
3. **Pull in abapGit** - In SAP, open abapGit and pull the latest changes from the repository
4. **Test with MCP** - Use this MCP server to navigate to transactions and test your code
5. **Iterate** - Fix issues in Claude Code, push, pull, test again

### Known Issue: `sap_abapgit_pull` Returns "Pull status unknown"

The `sap_abapgit_pull` tool may return "Pull status unknown" on the first call because the SAP status bar is empty after navigating to the report.
**Workaround:** Simply call `sap_abapgit_pull` a second time, or press F8 (Ausführen/Execute) after the first call to actually trigger the pull execution.

### Performance Tip: Use a Separate SAP Window (Modus)

When pulling changes in abapGit, it's helpful to do this in a **separate SAP window (Modus)**.
This way, the MCP server doesn't need to switch back and forth between abapGit and your test transaction.

To open a new Modus: Use menu **System → Erzeugen Modus** or enter `/o` in the command field.

> **Note:** Multi-session support is now available! See "Multi-Session Support" section below.
> Each sub-agent can have its own session, allowing parallel work without interference.

### Understanding abapGit Scope: 1 Repository = 1 Package

In abapGit, **one Git repository corresponds to exactly one ABAP package**.
This means your repository only contains the development objects within that specific package.

However, real-world ABAP development often requires interacting with objects **outside** your package:

- Standard SAP function modules, classes, or tables
- Objects in other custom packages
- Data dictionary structures you need to understand

**Use this MCP server to explore these external objects** without guessing.
You can navigate to the relevant transactions and inspect objects that aren't part of your abapGit repository.

### ABAP Development Transactions

Use these focused transactions for ABAP development.
Each has a simple, MCP-friendly UI:

| Transaction | Purpose                               | Example Use                                                  |
| ----------- | ------------------------------------- | ------------------------------------------------------------ |
| **SE37**    | Function Modules (Funktionsbausteine) | View, edit (sap_se37_edit) signature, parameters, exceptions |
| **SE38**    | Reports / Programs                    | View, edit (sap_se38_edit), and test ABAP reports            |
| **SE24**    | Classes (Klassen)                     | View, edit (sap_se24_edit) class methods, attributes         |
| **SE11**    | Data Dictionary (DDIC)                | View table structures, data elements, domains                |
| **SE16**    | Table Contents                        | Browse actual data in tables (read-only recommended)         |

> **Avoid SE80** (Object Navigator / Workbench): Its complex tree-based UI is difficult for the MCP server to parse and navigate.
> Prefer the smaller, focused transactions above.

## Functional Background

- This MCP server was designed with a S/4 utilities system in mind, so many transactions relate to the legacy SAP IS-U (Industry Solution for Utilities) or (mostly) are the same.
- **Use `search_transactions` first** before guessing transaction codes. If the catalog doesn't help, try SAP Help Portal (see below).

### Accessing SAP Help Portal via Chrome Browser

The best resource for finding correct SAP specific information is the SAP help portal.
Their robots.txt disallows browsers integrated into regular AI tools (like Claude, Gemini or ChatGPT).
This leads to the symptom that when the human user asks the LLM to do an online research, they'll find links to the SAP help portal but requests will fail.
The workaround is to use the same browser that is used to access the SAP Web GUI to visit the help portal (instead of the SAP GUI).

Therefore, use the tool `browser_navigate` to access the help portal, e.g. this URL:

```json
{
    "url": "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/021b182b0c47416c8fafed67ebfd78a9/266dce53118d4308e10000000a174cb4.html"
}
```

Add a little `browser_wait` for the site to load (10s is sufficient).
If you find a cookie banner/layover: Click on "Alle Ablehnen".
Then proceed like a user would do.
Make sure to NOT use `sap_`... MCP tools on the help portal.
`browser_snapshot` should be the way to go to access information after you loaded SAP help portal in the browser.
If you see that online research failed when accessing `help.sap.com`, use this workaround with the respective URL.

USE THIS APPROACH TO ACCESS HELP.SAP.COM ONLY.

## Transaction Code Tips

<!-- Add your transaction-specific knowledge here -->

## Stateful Selection Screens

**Problem:** SAP selection screens (SE09, SE16, SM37, etc.) remember their field values and checkbox states across sessions on the SAP side, per user. This means the screen you see when entering a transaction is NOT a clean default — it reflects whatever the user (or an automation tool) last entered.

**Impact on automation:** If your tool assumes a default checkbox state (e.g., "Workbench is checked by default in SE09"), it will break when the user previously used a different configuration. The checkbox state persists even across browser sessions and logins.

**Solution:** Transaction-specific tools use `ensure_screen_state()` to always explicitly set the desired state before executing. This reads the ARIA snapshot, diffs against the target, applies only necessary changes, and verifies the result. Labels that don't match the current language produce harmless warnings (bilingual support via `bilingual_target()`).

**Applies to:** All SAP selection screens, not just SE09. Any transaction with a selection screen (SE16, SM37, SLG1, etc.) has this stateful behavior.

## Selection Screen State Management

For general-purpose exploration of unknown screens:

- Use `sap_get_form_fields` to see all controls including checkbox/radio `checked` state
- Use `sap_set_checkbox(label, checked)` to toggle a checkbox
- Use `sap_set_radio_button(label)` to select a radio button
- These tools are safer than raw `browser_evaluate` for SAP form controls

## Common Patterns

### ALV Grid Pagination (Feature Request)

**Problem:** ALV grids in SAP Web GUI use lazy loading - only visible rows (~7-13) are in the DOM at a time. To read all rows, you need to paginate through the grid using PageDown.

**Current Solution:** The `sap_se16_query` tool in `se16_tools.py` implements a pagination pattern that:

1. Focuses the grid (required for PageDown to work)
2. Uses PageDown to scroll through pages
3. Deduplicates rows (pages can overlap)
4. Detects end-of-data via first-row key comparison
5. Handles stuck/empty pages gracefully

**Key Techniques:**

- Focus grid before pagination: `page.locator("[role='grid']").first.click()`
- Row deduplication via set with composite keys
- First-row key comparison to detect end
- Stuck counter (stop after 3 empty pages)
- ~1 second wait between pages for lazy loading

**Performance:** ~7 rows/second due to pagination overhead.

**Reuse Opportunity:** Consider extracting a reusable `alv_collect_rows()` helper that other transaction tools can use. Currently each tool would need to copy this pattern.

Use `log_feedback` to report if you encounter a transaction that needs pagination support.

## Multi-Session Support (Parallel Agents)

For bulk operations (create 100 business partners, process many orders, etc.), you can run **parallel sub-agents**, each with their own SAP session.

### Session Management Tools

| Tool                                      | Purpose                                                         |
| ----------------------------------------- | --------------------------------------------------------------- |
| `sap_transaction(tcode, new_window=True)` | Open a new SAP session with a transaction, returns `session_id` |
| `sap_session_list()`                      | List all active sessions with IDs and titles                    |
| `sap_session_close(session_id)`           | Close a specific session by ID                                  |
| `sap_session_bind(session_id, agent_id)`  | Bind a session to an agent for parallel workflows               |
| `sap_session_release(session_id)`         | Unbind a session from an agent without closing it               |

### Workflow Example

```python
# Parent agent creates sessions for 3 parallel sub-agents
sap_transaction("BP", new_window=True)  # Returns session_id="s2"
sap_session_bind(session_id="s2", agent_id="subagent-1")

sap_transaction("BP", new_window=True)  # Returns session_id="s3"
sap_session_bind(session_id="s3", agent_id="subagent-2")

sap_transaction("BP", new_window=True)  # Returns session_id="s4"
sap_session_bind(session_id="s4", agent_id="subagent-3")

# Spawn sub-agents with session assignment:
# "Your SAP session is 's2'. Pass session='s2' and agent_id='subagent-1' to ALL SAP/browser tools."

# Each sub-agent works independently:
sap_fill_form({"Name": "Customer 1"}, session="s2", agent_id="subagent-1")
sap_press_key("F8", session="s2", agent_id="subagent-1")  # Execute
```

### Tools Supporting `session` Parameter

All major SAP and browser tools accept an optional `session` parameter:

**SAP Tools:**

- `sap_transaction`, `sap_press_key`, `sap_get_screen_text`
- `sap_fill_form`, `sap_set_field`, `sap_get_form_fields`
- `sap_read_table`, `sap_click_table_cell`
- `sap_discover_fields`, `sap_discover_buttons`, `sap_get_shortcuts`
- `sap_close_popup`, `sap_read_status_bar`, `sap_get_screen_info`

**Browser Tools:**

- `browser_click`, `browser_fill`, `browser_keyboard`
- `browser_snapshot`, `browser_screenshot`, `browser_get_html`
- `browser_navigate`, `browser_wait`, `browser_evaluate`, `browser_select_option`

**SE\* Tools:**

- `sap_se11_lookup`, `sap_se16_query`, `sap_se24_lookup`, `sap_se37_lookup`, `sap_se93_lookup`

### Instructions for Sub-Agents

If you are a sub-agent working on an SAP task, your parent agent should have given you a `session` and `agent_id`.
You **must** pass both parameters on **every session-aware** SAP/browser tool call (i.e., those that accept `session` and `agent_id` parameters).
Session-management tools like `sap_session_release(session_id)` only take `session_id`.

```python
sap_transaction("VA01", session="s2", agent_id="subagent-orders")
sap_fill_form({"Customer": "12345"}, session="s2", agent_id="subagent-orders")
sap_press_key("Enter", session="s2", agent_id="subagent-orders")
```

When finished, release your session: `sap_session_release(session_id="s2")`

### Cross-Agent Access

If an agent accesses a session bound to a different agent, a **warning** is logged but the operation **still proceeds**.
This helps debug cross-talk issues without blocking work.

### Best Practices

- **Use descriptive agent_ids** like `"order-processor"`, not `"agent1"`
- **Always release sessions** when done to allow reuse
- **Check `sap_session_list()`** if unsure about session state

### Important Notes

- **Primary session "s1"** is created automatically on `sap_login()`
- **Session limit:** Typically 6 sessions per SAP user (configured in SAP)
- **Alternative:** Use `sap_transaction("BP", new_window=True)` to open a transaction directly in a new session. This **auto-registers** the new session and returns the `session_id` in the result.
- **Cleanup:** Sessions are closed automatically when their browser tab closes, or use `sap_session_close(session_id)`

### Using `new_window=True` for Quick Session Creation

```python
# Open transaction in new session - session is auto-registered
result = sap_transaction("BP", new_window=True)

# IMPORTANT: Always check if session was created successfully!
# session_id can be None if SAP session limit reached or timing issues
if result.session_id is None:
    # Handle failure - session was not created
    # Passing None to session= would use primary session (s1) instead!
    raise RuntimeError("Failed to create new SAP session")

# Use the new session (now guaranteed to be valid)
sap_fill_form({"Name": "Customer 1"}, session=result.session_id)
sap_press_key("Control+s", session=result.session_id)
```
