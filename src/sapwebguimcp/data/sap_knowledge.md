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
4. **Start over** - Either by restarting the transaction or using sap_login again (changes will be lost)

After you found out how to solve a specific problem without these workarounds, consider providing feedback to the devs.

## ABAP Development with Claude Code and abapGit

Don't try to write any ABAP code directly with this MCP server (i.e. by interacting with the sAP GUI for ABAP development).
Instead, use Claude Code together with abapGit for ABAP development.
This MCP server is designed to **test** code that was generated with Claude Code and synchronized via abapGit, but development in the SAP GUI is not recommended.

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

### Development Workflow

1. **Write code in Claude Code** - Let Claude Code generate/modify your ABAP code locally
2. **Push to Git** - Commit and push your changes to the Git repository
3. **Pull in abapGit** - In SAP, open abapGit and pull the latest changes from the repository
4. **Test with MCP** - Use this MCP server to navigate to transactions and test your code
5. **Iterate** - Fix issues in Claude Code, push, pull, test again

### Performance Tip: Use a Separate SAP Window (Modus)

When pulling changes in abapGit, it's helpful to do this in a **separate SAP window (Modus)**.
This way, the MCP server doesn't need to switch back and forth between abapGit and your test transaction.

To open a new Modus: Use menu **System → Erzeugen Modus** or enter `/o` in the command field.

> **Note:** Multi-window support for the MCP server is planned for a future release.
> Until then, using a separate Modus for Git operations keeps your testing session stable.

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

| Transaction | Purpose                               | Example Use                                                    |
| ----------- | ------------------------------------- | -------------------------------------------------------------- |
| **SE37**    | Function Modules (Funktionsbausteine) | View signature, parameters, exceptions of FMs you want to call |
| **SE38**    | Reports / Programs                    | View and test ABAP reports                                     |
| **SE24**    | Classes (Klassen)                     | Inspect class methods, attributes, interfaces                  |
| **SE11**    | Data Dictionary (DDIC)                | View table structures, data elements, domains                  |
| **SE16**    | Table Contents                        | Browse actual data in tables (read-only recommended)           |

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
