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

### State Bleeding Between Transactions

SAP WebGUI can "bleed" state between sequential transactions. Symptoms:

- Fields don't accept new values (previous values persist)
- F7/F8 doesn't execute (SAP didn't register the field change)
- Status bar shows errors from the previous transaction

**Root cause:** SAP WebGUI hooks into low-level keyboard events (`keydown`/`keyup`), not the standard DOM `input`/`change` events that JavaScript-based field fills trigger. After navigating between transactions, SAP's internal model may not detect JS-only value changes.

**Solutions (in order of preference):**

1. **`reset_first=True`** - Use `sap_transaction("SE24", reset_first=True)` to navigate to Easy Access before entering the transaction. This clears all residual state.
2. **Manual `/n` reset** - Call `sap_keyboard("Enter")` with `/n` in the OK-code field, then re-enter your transaction.
3. **Real keyboard typing** - If a field value isn't being picked up, try clearing the field and retyping the value manually using `sap_keyboard` with individual keystrokes.

After you found out how to solve a specific problem without these workarounds, consider providing feedback to the devs.

## ABAP Development with Claude Code and abapGit

**The strongly preferred approach** for ABAP development is to use Claude Code together with abapGit.
Writing ABAP locally, pushing to Git, and pulling via abapGit is **much faster, more stable, and fully version-controlled**.
Always choose abapGit-based development when possible.

For objects in packages that are **not source-controlled via abapGit**, the edit tools (`sap_se38_edit`, `sap_se37_edit`, `sap_se24_edit`) allow in-place editing of existing ABAP reports, function modules, and class methods directly in SAP.
These are fallback options for quick modifications to objects that are not tracked in Git.
Using Git is always the preferred option — there should be no doubt about it.

**Key rules:** All abapGit filenames MUST be lowercase. Workflow: write locally → push to Git → pull in abapGit → test with MCP → iterate. Use `sap_abapgit_pull` (may need a second call if status is unknown). One Git repo = one ABAP package; use this MCP server to explore objects outside your package.

**Avoid SE80** — prefer SE37, SE38, SE24, SE11, SE16 for ABAP development (simpler UI, better MCP support).

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

Use `sap_se16_query` which handles pagination automatically. For other transactions with ALV grids, use `log_feedback` to report pagination needs.

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

All major SAP, browser, and SE* tools accept an optional `session` parameter. Sub-agents **must** pass `session` and `agent_id` on every tool call. Use `sap_transaction(tcode, new_window=True)` to open a new session (returns `session_id` — always check it's not `None`). Release sessions when done with `sap_session_release(session_id)`.

- **Primary session "s1"** is created automatically on `sap_login()`
- **Session limit:** Typically 6 per SAP user
- **Cross-agent access:** Logs a warning but still proceeds
- Use descriptive agent_ids (e.g., `"order-processor"`, not `"agent1"`)
