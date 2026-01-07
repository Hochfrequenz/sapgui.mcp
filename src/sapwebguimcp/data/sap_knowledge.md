# SAP Web GUI Knowledge Base

This file contains domain knowledge, tips, and best practices for working with SAP Web GUI.
The content is loaded by `sap_get_capabilities()` and provided to the AI model.

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
- Often before you start guessing, you'll be faster if you try to find e.g. table or transaction names online.

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

## IS-U / S/4 Utilities Object Catalog (MCP Resources)

This MCP server includes a comprehensive catalog of IS-U and S/4HANA Utilities objects as **searchable MCP resources**.
Use these resources to quickly find BAPIs, function modules, classes, reports, tables, and namespaces.

### Available Resources

| Resource URI | Description |
|--------------|-------------|
| `bapi://catalog` | Full catalog with all objects |
| `bapi://catalog/search/{pattern}` | **Search across all object types** - use this! |
| `bapi://catalog/categories` | Functional categories (equipment, billing, etc.) |
| `bapi://catalog/category/{id}` | Details for a specific category |
| `bapi://catalog/bapi/{name}` | Details for a specific BAPI/FM |
| `bapi://catalog/classes` | ABAP classes (3,161 verified from SAP) |
| `bapi://catalog/reports` | Reports grouped by functional area |
| `bapi://catalog/tables` | All IS-U/FI-CA tables by domain |
| `bapi://catalog/tables/{domain}` | Tables for specific domain (contracts, billing, etc.) |
| `bapi://catalog/customizing` | IS-U (TE*) and FI-CA (TFK*) customizing tables |
| `bapi://catalog/namespaces` | SAP namespaces (/IDXGC/, /APE/, etc.) |
| `bapi://catalog/workflows` | Common workflow patterns |
| `bapi://catalog/data_model` | IS-U data model hierarchy |
| `bapi://catalog/transactions` | IS-U/FI-CA transactions (10 verified via SE93) |
| `bapi://catalog/field_types` | Field data types for key tables (EVER, DFKKKO, ERCH, EVBS) |
| `bapi://catalog/metadata` | Version, statistics, update instructions |

### Table Domains

The tables are organized into these domains:

| Domain | Description | Key Tables |
|--------|-------------|------------|
| `contracts` | Utility contracts | EVER, EVERH |
| `installations` | Installations | EANL, EANLH, EASTL |
| `point_of_delivery` | POD / MaLo/MeLo | EUIINSTLN, EUITRANS |
| `meter_reading` | Meter reading docs | EABL, EABLG |
| `billing` | Billing documents | ERCH, DBERCHZ |
| `fica_documents` | FI-CA documents | DFKKKO, DFKKOP |
| `contract_account` | Contract accounts | FKKVK, FKKVKP |
| `devices` | Devices/meters | EGERH, EGERS, EQUI |
| `premise` | Premises | EVBS |
| `connection_object` | Connection objects | IFLOT, EHAUISU |
| `tariffs` | Rates and prices | ETTA, ETRF, EPREI |
| `serviceanbieter` | Service providers | ESERVICE, ESERVPROV ✓ |
| `versorgungsszenarien` | Supply scenarios | EVERSREASON, EVERSW ✓ |
| `abrechnung_erweitert` | Extended billing | ERCHARC, ERCHO, ERCHP ✓ |
| `customizing_isu` | IS-U config | TE069, TE221, TE835 |
| `customizing_fica` | FI-CA config | TFK047A, TFK056A |

> ✓ = verified in SAP system

### How to Search

Use `bapi://catalog/search/{pattern}` to search across **all object types** at once:

- `search/meter` - Find all meter-related objects
- `search/billing` - Find billing BAPIs, reports, tables
- `search/partner` - Find business partner objects
- `search/fkk` - Find FI-CA objects

### Verification Status

Objects in the catalog are marked with their verification status:

- **`verified_in_system: true`** - Extracted directly from SAP system via SE16N
- **`source: online_research`** - From documentation, may not exist in your system

Always verify unverified objects in your SAP system before relying on them.

### Extraction Statistics (from SAP)

| Pattern | Count | Status |
|---------|-------|--------|
| BAPI_ISU* | 52 | Complete |
| BAPI_CTRAC* | 73 | Complete |
| BAPI_BUPA* | 194 | Complete |
| /APE/* | 21 | Complete |
| ISU_* | 9,999+ | Exceeded limit |
| FKK* | 9,999+ | Exceeded limit |
| CL_ISU_* | 1,634 | Complete |
| CL_FKK_* | 1,265 | Complete |
| CL_BUPA_* | 262 | Complete |

### Updating the Catalog

See `docs/bapi_catalog_update.md` for instructions on how to:
1. Extract new objects from SAP using SE16N
2. Add objects from documentation
3. Verify unverified objects

## Transaction Code Tips

<!-- Add your transaction-specific knowledge here -->

## Common Patterns

<!-- Add patterns you've learned over time -->
