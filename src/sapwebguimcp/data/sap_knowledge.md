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
- **F5** - Refresh / Create (context dependent)
- **Enter** - Confirm current action
- **F4** - Open search help / value list

## When Stuck

1. **Check the status bar** - SAP shows errors, warnings, and info messages there
2. **Look for popups** - A blocking popup may be waiting for confirmation (maybe use popup tools)
3. **Try F3 (Back)** - Often helps to back out and retry
4. **Start over** - either by restarting the transaction or using sap_login again (changes will be lost)

## Language Considerations

SAP Web GUI may be in German or English. Common translations:

- Save = Sichern
- Execute = Ausführen
- Back = Zurück
- Exit = Beenden
- Create = Anlegen
- Change = Ändern
- Display = Anzeigen

## Functional Background

- This MCP server was designed with a S/4 utilities system in mind, so many transactions relate to the legacy SAP IS-U (Industry Solution for Utilities) or (mostly) are the same.
- Often before you start guessing, you'll be faster if you try to find e.g. table or transaction names online.
- Don't expect the system to behave intuitively - SAP has many legacy behaviors and quirks.

## Transaction Code Tips

<!-- Add your transaction-specific knowledge here -->

## Common Patterns

<!-- Add patterns you've learned over time -->
