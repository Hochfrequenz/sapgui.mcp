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
- **F4** - Open search help / value list which helps you to fill meaningful values to a field (browser focus needs to be on the respective field before hitting F4 - this often opens a popup which we don't want to dismiss in most cases)

## When Stuck

1. **Check the status bar** - SAP shows errors, warnings, and info messages there
2. **Look for popups** - A blocking popup may be waiting for confirmation (maybe use popup tools)
3. **Try F3 (Back)** - Often helps to back out and retry
4. **Start over** - either by restarting the transaction or using sap_login again (changes will be lost)

After you found out how to solve a specific problem without these workarounds, consider providing feedback to the devs.

## No Programming
Don't try to write any ABAP code with this MCP.
Use Claude Code and abapGit instead.
But you may use this MCP tool to test code which was generated with Claude Code and pushed/pull to the SAP system with abapGit.

## Functional Background

- This MCP server was designed with a S/4 utilities system in mind, so many transactions relate to the legacy SAP IS-U (Industry Solution for Utilities) or (mostly) are the same.
- Often before you start guessing, you'll be faster if you try to find e.g. table or transaction names online.

### Accessing SAP Help Portal via Chrome Browser
The best ressource for finding correct SAP specific information, is the SAP help portal.
Their robots.txt disallows browsers integrated into regular AI tools (like Claude, Gemini or ChatGPT).
This leads to the symptom that when the human user asks the LLM to do an online research, they'll find links to the SAP help portal but requests will fail.
The workaround is to use the same browser that is used to access the SAP Web GUI to visit the help portal (instead of the SAP GUI)

Therefore use the tool `browser_navigate` to access the help portal, e.g. this URL:
```json
{
  `url`: `https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/021b182b0c47416c8fafed67ebfd78a9/266dce53118d4308e10000000a174cb4.html`
}
```
Add a little `browser_wait` for the site to load (10s is sufficient).
If you find a cookie banner/layover: Click on "Alle Ablehnen".
Then proceed like a user would do.
Make sure to NOT use `sap_`... MCP tools on the help portal.
`browser_snapshot` should be the way to go to access information after you loaded SAP help portal in the browser.
If you see that online research failed when accessing `help.sap.com`, use thie workaround with the respective URL.

## Transaction Code Tips

<!-- Add your transaction-specific knowledge here -->

## Common Patterns

<!-- Add patterns you've learned over time -->
