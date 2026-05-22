# SE38 In-Place Report Editing — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `sap_se38_edit` tool that modifies existing ABAP reports in SE38 with syntax check, activation, and auto-revert on failure.

**Architecture:** Single tool with shared `_check_and_activate` / `_revert_editor` helpers (reusable for future SE24/SE37). Full source replacement: read backup → paste new code → check → activate → revert on failure.

**Tech Stack:** Python 3.12, Playwright (browser automation), Pydantic (models), FastMCP (tool registration), pytest + anyio (testing)

---

### Task 1: Create SE38EditResult model

**Files:**

- Create: `src/sapguimcp/models/se38_edit_models.py`
- Modify: `src/sapguimcp/models/__init__.py`
- Test: `unittests/test_se38_edit.py`

**Step 1: Write the failing test**

Create `unittests/test_se38_edit.py`:

```python
"""Tests for SE38 edit tool."""

import pytest
from pydantic import ValidationError


def test_se38_edit_result_success() -> None:
    """Test successful SE38EditResult creation."""
    from sapguimcp.models.se38_edit_models import SE38EditResult

    result = SE38EditResult(
        success=True,
        program_name="ZTEST_MCP_EDIT",
        backup_source="REPORT ZTEST_MCP_EDIT.\nWRITE 'OLD'.",
        check_messages=["No syntax errors found"],
        activated=True,
    )
    assert result.success is True
    assert result.program_name == "ZTEST_MCP_EDIT"
    assert result.backup_source == "REPORT ZTEST_MCP_EDIT.\nWRITE 'OLD'."
    assert result.activated is True
    assert result.error is None


def test_se38_edit_result_failure() -> None:
    """Test failed SE38EditResult creation via factory."""
    from sapguimcp.models.se38_edit_models import SE38EditResult

    result = SE38EditResult.failure(
        error="Syntax error in line 3",
        program_name="ZTEST_MCP_EDIT",
        backup_source="REPORT ZTEST_MCP_EDIT.\nWRITE 'OLD'.",
        check_messages=["Syntax error: unexpected token"],
        activated=False,
    )
    assert result.success is False
    assert result.error == "Syntax error in line 3"
    assert result.activated is False


def test_se38_edit_result_validation_error() -> None:
    """Test that success=True with error raises ValidationError."""
    from sapguimcp.models.se38_edit_models import SE38EditResult

    with pytest.raises(ValidationError):
        SE38EditResult(
            success=True,
            error="This should not be set",
            program_name="ZTEST",
            backup_source="",
            check_messages=[],
            activated=False,
        )
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_se38_edit.py::test_se38_edit_result_success -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sapguimcp.models.se38_edit_models'`

**Step 3: Write minimal implementation**

Create `src/sapguimcp/models/se38_edit_models.py`:

```python
"""Models for SE38 (ABAP Report Editor) edit operations."""

from pydantic import Field

from sapguimcp.models.base import ToolResult


class SE38EditResult(ToolResult):
    """Result of editing an ABAP report in SE38."""

    program_name: str = Field(description="Name of the ABAP report that was edited")
    backup_source: str = Field(description="Original source code before editing (for reference/undo)")
    check_messages: list[str] = Field(default_factory=list, description="Messages from syntax check (Ctrl+F2)")
    activated: bool = Field(default=False, description="Whether the report was successfully activated")
```

Add to `src/sapguimcp/models/__init__.py` — add import and `__all__` entry:

```python
from sapguimcp.models.se38_edit_models import SE38EditResult
```

Add `"SE38EditResult"` to the `__all__` list.

**Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/test_se38_edit.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add src/sapguimcp/models/se38_edit_models.py src/sapguimcp/models/__init__.py unittests/test_se38_edit.py
git commit -m "feat(se38): add SE38EditResult model"
```

---

### Task 2: Implement shared \_check_and_activate helper

**Files:**

- Create: `src/sapguimcp/tools/edit_helpers.py`
- Test: `unittests/test_se38_edit.py` (append)

**Step 1: Write the failing test**

Append to `unittests/test_se38_edit.py`:

```python
import re


class TestParseStatusNote:
    """Tests for parsing status bar notes from ARIA snapshots."""

    def test_parse_check_success_de(self) -> None:
        """German check success message."""
        from sapguimcp.tools.edit_helpers import parse_toolbar_note

        snapshot = '- note "Erfolgreich Meldungsleiste Es wurden keine Syntaxfehler in Report ZTEST_MCP_EDIT gefunden"'
        success, message = parse_toolbar_note(snapshot)
        assert success is True
        assert "keine Syntaxfehler" in message or "No syntax errors" in message

    def test_parse_activate_success_de(self) -> None:
        """German activation success message."""
        from sapguimcp.tools.edit_helpers import parse_toolbar_note

        snapshot = '- note "Erfolgreich Meldungsleiste Aktives Objekt wurde generiert"'
        success, message = parse_toolbar_note(snapshot)
        assert success is True
        assert "generiert" in message or "generated" in message

    def test_parse_check_failure_de(self) -> None:
        """German check failure message (error pattern)."""
        from sapguimcp.tools.edit_helpers import parse_toolbar_note

        snapshot = '- note "Fehler Meldungsleiste Syntaxfehler in Zeile 3"'
        success, message = parse_toolbar_note(snapshot)
        assert success is False
        assert "Syntaxfehler" in message

    def test_parse_no_note(self) -> None:
        """No note in snapshot."""
        from sapguimcp.tools.edit_helpers import parse_toolbar_note

        snapshot = "- button 'Aktivieren'"
        success, message = parse_toolbar_note(snapshot)
        assert success is False
        assert message  # should have a default message
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_se38_edit.py::TestParseStatusNote -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sapguimcp.tools.edit_helpers'`

**Step 3: Write minimal implementation**

Create `src/sapguimcp/tools/edit_helpers.py`:

```python
"""
Shared helpers for ABAP source code editing (SE38, SE24, SE37).

These helpers handle the common check/activate workflow and status message parsing.
"""

import logging
import re

from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Patterns for toolbar note messages
_SUCCESS_PATTERNS = re.compile(
    r"Erfolgreich|Successfully|keine Syntaxfehler|No syntax errors|"
    r"Aktives Objekt wurde generiert|generated successfully",
    re.IGNORECASE,
)
_ERROR_PATTERNS = re.compile(
    r"Fehler|Error|Syntaxfehler|syntax error",
    re.IGNORECASE,
)


def parse_toolbar_note(snapshot_text: str) -> tuple[bool, str]:
    """Parse the toolbar note from an ARIA snapshot to determine success/failure.

    The SAP ABAP editor shows status messages as a 'note' element in the toolbar area.
    Format: note "Erfolgreich Meldungsleiste <actual message>"
    Or:     note "Fehler Meldungsleiste <actual message>"

    Returns:
        (success, message) tuple.
    """
    match = re.search(r'note\s+"([^"]+)"', snapshot_text)
    if not match:
        return False, "No status message found in toolbar"

    full_note = match.group(1)
    # Strip the "Erfolgreich/Fehler Meldungsleiste" prefix to get the actual message
    message = re.sub(r"^(Erfolgreich|Fehler)\s+Meldungsleiste\s+", "", full_note).strip()
    if not message:
        message = full_note

    if _SUCCESS_PATTERNS.search(full_note):
        return True, message
    if _ERROR_PATTERNS.search(full_note):
        return False, message
    # Unknown pattern — treat as failure for safety
    return False, message


async def read_editor_source(page: Page, editor_selector: str = "textarea[id*='textedit']") -> str | None:
    """Read the current source code from the SAP editor textarea.

    Args:
        page: Playwright page.
        editor_selector: CSS selector for the editor textarea.

    Returns:
        Source code string, or None if editor not found.
    """
    try:
        textarea = page.locator(editor_selector).first
        if not await textarea.is_visible(timeout=3000):
            return None
        return await textarea.input_value()
    except Exception:
        logger.warning("Could not read editor content with selector %s", editor_selector)
        return None


async def replace_editor_source(page: Page, new_source: str, editor_selector: str = "textarea[id*='textedit']") -> bool:
    """Replace the entire editor content with new source code.

    Clicks the editor, selects all (Ctrl+A), deletes, then types the new source.

    Args:
        page: Playwright page.
        new_source: The new ABAP source code to paste.
        editor_selector: CSS selector for the editor textarea.

    Returns:
        True if replacement succeeded.
    """
    try:
        textarea = page.locator(editor_selector).first
        await textarea.click()
        await page.keyboard.press("Control+a")
        await page.wait_for_timeout(200)
        await page.keyboard.press("Delete")
        await page.wait_for_timeout(200)
        await textarea.fill(new_source)
        return True
    except Exception:
        logger.exception("Failed to replace editor source")
        return False


async def check_and_activate(page: Page) -> tuple[bool, list[str], bool]:
    """Run syntax check (Ctrl+F2) and activation (Ctrl+F3) on the current editor.

    Returns:
        (success, messages, activated) tuple:
        - success: True if both check and activation passed
        - messages: List of status messages collected
        - activated: True if activation specifically succeeded
    """
    messages: list[str] = []

    # Syntax check (Ctrl+F2)
    await page.keyboard.press("Control+F2")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    snapshot = await page.locator("body").aria_snapshot()
    check_ok, check_msg = parse_toolbar_note(snapshot)
    messages.append(f"Check: {check_msg}")

    if not check_ok:
        return False, messages, False

    # Activation (Ctrl+F3)
    await page.keyboard.press("Control+F3")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    snapshot = await page.locator("body").aria_snapshot()
    activate_ok, activate_msg = parse_toolbar_note(snapshot)
    messages.append(f"Activate: {activate_msg}")

    return activate_ok, messages, activate_ok
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/test_se38_edit.py -v`
Expected: All PASSED (including Task 1 tests)

**Step 5: Commit**

```bash
git add src/sapguimcp/tools/edit_helpers.py unittests/test_se38_edit.py
git commit -m "feat(se38): add shared edit helpers (check/activate, status parsing)"
```

---

### Task 3: Implement sap_se38_edit tool

**Files:**

- Create: `src/sapguimcp/tools/se38_edit_tools.py`
- Modify: `src/sapguimcp/tools/__init__.py`
- Modify: `src/sapguimcp/server.py`

**Step 1: Write the failing test**

Append to `unittests/test_se38_edit.py`:

```python
def test_se38_edit_tool_is_registered() -> None:
    """Test that sap_se38_edit tool is registered on the MCP server."""
    import asyncio
    from sapguimcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    tool_names = [t.name for t in tools]
    assert "sap_se38_edit" in tool_names, f"sap_se38_edit not found in {tool_names}"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_se38_edit.py::test_se38_edit_tool_is_registered -v`
Expected: FAIL with `AssertionError: sap_se38_edit not found in [...]`

**Step 3: Write the tool implementation**

Create `src/sapguimcp/tools/se38_edit_tools.py`:

```python
"""
SE38 (ABAP Report Editor) edit tool.

Provides sap_se38_edit for modifying existing ABAP reports with
syntax check, activation, and auto-revert on failure.
"""

import logging

from fastmcp import FastMCP

from sapguimcp.models import SE38EditResult
from sapguimcp.models.browser import get_browser_manager
from sapguimcp.tools.edit_helpers import check_and_activate, read_editor_source, replace_editor_source
from sapguimcp.tools.sap_tools import sap_transaction_impl

logger = logging.getLogger(__name__)


def register_se38_edit_tools(mcp: FastMCP) -> None:
    """Register SE38 edit tools with the MCP server."""

    @mcp.tool(
        description=(
            "Edit an existing ABAP report in SE38.\n\n"
            "Replaces the entire source code, runs syntax check (Ctrl+F2), "
            "and activates (Ctrl+F3). Auto-reverts if check or activation fails.\n\n"
            "**Important:** Only for EXISTING reports. To create new reports, use abapGit.\n\n"
            "**Workflow:** Read current source with sap_read_se38_source first, "
            "modify it, then call this tool with the full new source."
        ),
        annotations={
            "destructiveHint": True,
            "readOnlyHint": False,
            "idempotentHint": True,
        },
    )
    async def sap_se38_edit(
        program_name: str,
        new_source: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE38EditResult:
        """Edit an existing ABAP report, check syntax, and activate.

        Args:
            program_name: Name of the ABAP report (e.g., 'ZTEST_MCP_EDIT').
            new_source: Complete new ABAP source code to replace the current code.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE38EditResult with success status, backup source, and check messages.
        """
        program_name = program_name.strip().upper()
        backup_source = ""

        try:
            browser_manager = await get_browser_manager()
            page = await browser_manager.get_or_create_session_page_checked(
                session, agent_id, "sap_se38_edit"
            )
        except Exception as exc:
            return SE38EditResult.failure(
                error=f"Browser not available: {exc}",
                program_name=program_name,
                backup_source="",
                activated=False,
            )

        try:
            # 1. Navigate to SE38
            tx_result = await sap_transaction_impl("SE38", page=page)
            if not tx_result.get("success"):
                return SE38EditResult.failure(
                    error=f"Failed to navigate to SE38: {tx_result.get('error')}",
                    program_name=program_name,
                    backup_source="",
                    activated=False,
                )

            await page.wait_for_timeout(1000)

            # 2. Fill program name and enter change mode (F6)
            # Try German then English field label
            field = page.get_by_role("textbox", name="Programm")
            if not await field.is_visible(timeout=2000):
                field = page.get_by_role("textbox", name="Program")
            await field.click(click_count=3)
            await page.keyboard.press("Delete")
            await page.keyboard.type(program_name)

            # F6 = direct change mode
            await page.keyboard.press("F6")
            await page.wait_for_timeout(2000)
            await page.wait_for_load_state("networkidle")

            # 3. Read current source (backup)
            backup_source = await read_editor_source(page) or ""
            if not backup_source:
                return SE38EditResult.failure(
                    error="Could not read current source code from editor. Is the report accessible?",
                    program_name=program_name,
                    backup_source="",
                    activated=False,
                )

            logger.info("SE38 edit: backup saved for %s (%d chars)", program_name, len(backup_source))

            # 4. Replace editor content
            replaced = await replace_editor_source(page, new_source)
            if not replaced:
                return SE38EditResult.failure(
                    error="Failed to replace editor content",
                    program_name=program_name,
                    backup_source=backup_source,
                    activated=False,
                )

            # 5. Check and activate
            success, messages, activated = await check_and_activate(page)

            if not success:
                # Auto-revert
                logger.warning("SE38 edit: check/activate failed for %s, reverting", program_name)
                reverted = await replace_editor_source(page, backup_source)
                if reverted:
                    # Re-activate the backup to leave in consistent state
                    await check_and_activate(page)
                    messages.append("Auto-reverted to original source")
                else:
                    messages.append("WARNING: Auto-revert failed! Manual intervention needed.")

                return SE38EditResult.failure(
                    error=f"Check/activate failed: {'; '.join(messages)}",
                    program_name=program_name,
                    backup_source=backup_source,
                    check_messages=messages,
                    activated=False,
                )

            return SE38EditResult(
                success=True,
                program_name=program_name,
                backup_source=backup_source,
                check_messages=messages,
                activated=activated,
            )

        except Exception as exc:
            logger.exception("SE38 edit failed for %s", program_name)
            return SE38EditResult.failure(
                error=f"Unexpected error: {exc}",
                program_name=program_name,
                backup_source=backup_source,
                activated=False,
            )
```

Register the tool:

In `src/sapguimcp/tools/__init__.py`, add:

```python
from sapguimcp.tools.se38_edit_tools import register_se38_edit_tools
```

Add `"register_se38_edit_tools"` to `__all__`.

In `src/sapguimcp/server.py`, add after the other register calls:

```python
register_se38_edit_tools(mcp)
```

And add to the import block:

```python
from sapguimcp.tools import register_se38_edit_tools
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/test_se38_edit.py -v`
Expected: All PASSED

**Step 5: Commit**

```bash
git add src/sapguimcp/tools/se38_edit_tools.py src/sapguimcp/tools/__init__.py src/sapguimcp/server.py unittests/test_se38_edit.py
git commit -m "feat(se38): add sap_se38_edit tool with check, activate, auto-revert"
```

---

### Task 4: Linting and formatting

**Step 1: Run linting**

Run: `tox -e linting`

Fix any issues (likely line length, import order).

**Step 2: Run formatting**

Run: `tox -e formatting`

Apply any formatting fixes with `black` and `isort`.

**Step 3: Run unit tests**

Run: `tox -e py312`

Ensure all existing tests still pass.

**Step 4: Commit**

```bash
git add -u
git commit -m "style: fix linting and formatting for SE38 edit tool"
```

---

### Task 5: Integration test with real SAP

**Files:**

- Modify: `unittests/test_se38_edit_exploration.py` (append)

**Step 1: Write the integration test**

Append to `unittests/test_se38_edit_exploration.py`:

```python
@pytest.mark.anyio
async def test_se38_edit_round_trip(sap_mcp_client: ClientSession) -> None:
    """
    Integration test: edit ZTEST_MCP_EDIT, check, activate, then restore original.

    This test:
    1. Reads the current source
    2. Modifies it (adds a comment)
    3. Calls sap_se38_edit with modified source
    4. Verifies success
    5. Restores original source
    """
    from sapguimcp.models import SE38EditResult
    from .conftest import call_tool_typed

    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Read current source first
    read_result = await sap_mcp_client.call_tool(
        "sap_read_se38_source", {"program_name": "ZTEST_MCP_EDIT"}
    )
    original_source = None
    for content in read_result.content:
        if hasattr(content, "text"):
            import json
            data = json.loads(content.text)
            if data.get("success"):
                original_source = data["source_code"]
                break

    assert original_source, "Could not read original source"

    # Modify source: add a comment line
    modified_source = original_source.rstrip() + "\n* MCP edit test comment."

    # Edit with sap_se38_edit
    edit_result = await call_tool_typed(
        sap_mcp_client,
        "sap_se38_edit",
        {"program_name": "ZTEST_MCP_EDIT", "new_source": modified_source},
        SE38EditResult,
    )

    assert edit_result.success, f"Edit failed: {edit_result.error}"
    assert edit_result.activated, "Report was not activated"
    assert edit_result.backup_source, "No backup source returned"

    # Restore original source
    restore_result = await call_tool_typed(
        sap_mcp_client,
        "sap_se38_edit",
        {"program_name": "ZTEST_MCP_EDIT", "new_source": original_source},
        SE38EditResult,
    )

    assert restore_result.success, f"Restore failed: {restore_result.error}"
    assert restore_result.activated, "Restore was not activated"
```

**Step 2: Run the integration test**

Run: `python -m pytest unittests/test_se38_edit_exploration.py::test_se38_edit_round_trip -v -s`
Expected: PASSED (requires Chrome with CDP and SAP connection)

**Step 3: Commit**

```bash
git add unittests/test_se38_edit_exploration.py
git commit -m "test(se38): add round-trip integration test for sap_se38_edit"
```

---

### Task 6: Push feature branch

**Step 1: Create and push branch**

```bash
git checkout -b feat/se38-edit
git push -u origin feat/se38-edit
```
