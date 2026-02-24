# SE38 In-Place Report Editing Tool — Design

## Goal

Add an MCP tool `sap_se38_edit` that modifies existing ABAP reports directly in SE38, including syntax check and activation. This enables in-place code changes for workbench objects not tracked in git.

## Scope

- Edit EXISTING reports only (no creating new reports — use abapGit for that)
- Full source replacement (read current → modify → paste back)
- Mandatory syntax check + activation after every edit
- Auto-revert to backup if check or activation fails

## Architecture

**Approach C**: Separate tool with shared check/activate helper (reusable for future SE24/SE37 edit tools).

### Tool API

```python
sap_se38_edit(program_name: str, new_source: str) -> SE38EditResult
```

MCP annotations: `destructiveHint=True`, `idempotentHint=True`, `readOnlyHint=False`.

### Result Model

```python
class SE38EditResult(BaseModel):
    success: bool
    program_name: str
    backup_source: str  # original code before edit (for LLM reference)
    check_messages: list[str]  # compiler messages from syntax check
    error: str | None  # if failed, what went wrong
    activated: bool  # whether activation succeeded
```

## Internal Workflow

```
1. Navigate to SE38 → fill program name → F6 (direct change mode)
2. Read current source from textarea (id: textedit#TEC_cnt2) → store as backup
3. Click textarea → Ctrl+A → Delete → type/paste new source
4. Ctrl+F2 (syntax check) → read toolbar note / status bar
5. If check fails → revert (paste backup) → return errors
6. Ctrl+F3 (activate) → read toolbar note / status bar
7. If activation fails → revert (paste backup) → return errors
8. Return success with backup source and messages
```

### SAP UI Details (from exploration)

**Editor element**: `<textarea id="textedit#TEC_cnt2">` — holds full source with `\n` line breaks.

**ARIA snapshot**: Shows as `textbox` containing all source as a single string with `*` separators.

**Navigation shortcuts**:

- F6 from initial screen → direct change mode (title: "ändern")
- Ctrl+F1 → toggle display/change mode
- Ctrl+F2 → syntax check
- Ctrl+F3 → activate

**Status messages (DE)**:

- Check success: `"Es wurden keine Syntaxfehler in Report ZTEST_MCP_EDIT gefunden"`
- Activate success: `"Aktives Objekt wurde generiert"`
- Messages appear as `note` element in toolbar (with prefix "Erfolgreich Meldungsleiste")

**Edit mode indicators**:

- Title contains "ändern" (DE) / "Change" (EN) — vs "anzeigen"/"Display"
- Cut/Paste buttons enabled (vs `[disabled]` in display mode)
- Extra toolbar with "Sichern Hervorgehoben" (Save) + "Abbrechen" (Cancel)

### Shared Helper (for future SE24/SE37 reuse)

```python
async def _check_and_activate(page, object_name: str) -> tuple[bool, list[str]]:
    """Run syntax check (Ctrl+F2) and activation (Ctrl+F3).
    Returns (success, messages).
    """
```

### Revert Logic

```python
async def _revert_editor(page, backup_source: str) -> None:
    """Replace editor content with backup source."""
    # Click editor → Ctrl+A → Delete → type backup
```

## Safety

- Backup stored in Python memory (dict keyed by program name)
- Auto-revert on check failure (code never left in broken state)
- Auto-revert on activation failure
- Backup source returned to LLM in result (so it can re-edit if needed)

## Testing Strategy

- **Unit tests**: Mock browser interactions, test status message parsing, test revert logic
- **Integration tests**: Use ZTEST_MCP_EDIT report (pre-created in SAP), verify round-trip edit + check + activate
- **Snapshot tests**: Capture ARIA snapshots at each step for regression testing

## Out of Scope

- Creating new reports (use abapGit)
- SE24 class editing (future — same architecture, source-based view)
- SE37 function module editing (future — same architecture)
- Transport request handling (assume object is already in a transport)
