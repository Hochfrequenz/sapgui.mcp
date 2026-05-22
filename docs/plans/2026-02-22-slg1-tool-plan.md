# SLG1 Application Log Reader Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a read-only `sap_slg1_lookup` MCP tool that searches and reads SAP application logs via transaction SLG1, returning structured log entries with messages parsed from the ALV Tree Control.

**Architecture:** The tool follows the established lookup pattern (SE37, SE24, SE93): a Pydantic model layer (`slg1_models.py`), a parser layer (`slg1_parser.py`) that extracts structured data from ARIA/YAML accessibility snapshots, and a tool layer (`slg1_tools.py`) that orchestrates navigation, snapshot capture, and parsing. SLG1 uses an ALV Tree Control (not ALV grid), so the parser must handle `treeitem` roles with expand icons and AJAX-loaded child nodes, limited to 2 levels of expansion, max 50 logs, and max 200 messages per log.

**Tech Stack:** Python 3.12+, Pydantic v2, FastMCP, Playwright (via browser_manager), pytest + anyio for tests.

---

### Task 1: Create Pydantic Models (`slg1_models.py`)

**Files:** Create `src/sapguimcp/models/slg1_models.py`

**Step 1:** Create the file with the following models, following the pattern in `se37_models.py`:

```python
"""
Pydantic models for SLG1 (Application Log) lookup tool.

These models represent application log data retrieved from SLG1,
including log headers and individual log messages.
"""

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "SLG1Message",
    "SLG1LogEntry",
    "SLG1LogListResult",
    "SLG1FileSummary",
]


class SLG1Message(BaseModel):
    """A single message within an application log entry."""

    type: str = Field(description="Message type: S (Success), W (Warning), E (Error), I (Info), A (Abort)")
    text: str = Field(description="Message text")
    timestamp: str | None = Field(default=None, description="Message timestamp if available")


class SLG1LogEntry(BaseModel):
    """A single application log entry with its messages."""

    log_number: str = Field(description="Log number")
    object: str = Field(description="Log object (e.g., EABL, EA)")
    subobject: str = Field(default="", description="Log subobject")
    external_id: str = Field(default="", description="External identifier")
    date: str = Field(description="Log date")
    time: str = Field(description="Log time")
    user: str = Field(default="", description="User who created the log")
    message_count: int = Field(default=0, description="Total number of messages in this log")
    messages: list[SLG1Message] = Field(default_factory=list, description="Log messages (up to 200)")
    messages_truncated: bool = Field(
        default=False,
        description="True if more messages exist than were fetched (max 200)",
    )


class SLG1LogListResult(ToolResult):
    """Result of SLG1 application log lookup."""

    logs: list[SLG1LogEntry] = Field(default_factory=list, description="Log entries found")
    log_count: int = Field(default=0, description="Total number of logs found")
    logs_truncated: bool = Field(
        default=False,
        description="True if more logs exist than were fetched (max 50)",
    )
    filters_applied: dict[str, str] = Field(
        default_factory=dict,
        description="Filters that were applied to the search",
    )
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")


class SLG1FileSummary(ToolResult):
    """Summary returned when results are written to file."""

    output_file: str = Field(description="Path to the output file")
    log_count: int = Field(description="Number of logs retrieved")
    total_messages: int = Field(description="Total messages across all logs")
    logs_truncated: bool = Field(default=False, description="Whether the log list was truncated")
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")
```

**Step 2:** Verify the file is syntactically correct:

```bash
python -c "from sapguimcp.models.slg1_models import SLG1Message, SLG1LogEntry, SLG1LogListResult, SLG1FileSummary; print('OK')"
```

Expected output: `OK`

---

### Task 2: Register Models in `models/__init__.py`

**Files:** Modify `src/sapguimcp/models/__init__.py`

**Step 1:** Add the import block after the SE93 models import (around line 119-125):

```python
from sapguimcp.models.slg1_models import (
    SLG1FileSummary,
    SLG1LogEntry,
    SLG1LogListResult,
    SLG1Message,
)
```

**Step 2:** Add to the `__all__` list, after the SE93 models section (around line 259), add a new comment section:

```python
    # SLG1 models
    "SLG1FileSummary",
    "SLG1LogEntry",
    "SLG1LogListResult",
    "SLG1Message",
```

**Step 3:** Verify the import works:

```bash
python -c "from sapguimcp.models import SLG1Message, SLG1LogEntry, SLG1LogListResult, SLG1FileSummary; print('OK')"
```

Expected output: `OK`

---

### Task 3: Add SLG1 Language Constants

**Files:** Modify `src/sapguimcp/lang.py`

**Step 1:** Add an SLG1 section after the SE93 section (after line 166), before the Helper Functions section:

```python
# =============================================================================
# SLG1 - Application Log
# =============================================================================
SLG1_INITIAL_SCREEN_DE = "Auswahl von Applikations-Logs"
SLG1_INITIAL_SCREEN_EN = "Analyze Application Log"

SLG1_OBJECT_DE = "Objekt"
SLG1_OBJECT_EN = "Object"

SLG1_SUBOBJECT_DE = "Unterobjekt"
SLG1_SUBOBJECT_EN = "Subobject"

SLG1_EXTERNAL_ID_DE = "Externe Identifikation"
SLG1_EXTERNAL_ID_EN = "External ID"

SLG1_FROM_DATE_DE = "Datum ab"
SLG1_FROM_DATE_EN = "From date"

SLG1_TO_DATE_DE = "Datum bis"
SLG1_TO_DATE_EN = "To date"

SLG1_FROM_TIME_DE = "Uhrzeit ab"
SLG1_FROM_TIME_EN = "From time"

SLG1_TO_TIME_DE = "Uhrzeit bis"
SLG1_TO_TIME_EN = "To time"

SLG1_EXECUTE_DE = "Ausf\u00fchren"
SLG1_EXECUTE_EN = "Execute"

SLG1_NO_LOGS_FOUND_DE = "Keine Protokolle gefunden"
SLG1_NO_LOGS_FOUND_EN = "No logs found"
```

**NOTE:** The exact DE/EN labels for SLG1 selection screen fields and tree columns must be verified during exploration testing (Task 4). The values above are educated guesses based on standard SAP naming. Update these constants after capturing real snapshots.

---

### Task 4: Write Exploration Tests for YAML Snapshot Capture

**Files:** Create `unittests/test_slg1_exploration.py`, create directory `unittests/testdata/slg1_exploration/`

**Step 1:** Create the exploration test file following the pattern from `test_se37_integration.py`:

```python
"""
Exploratory tests for SLG1 (Application Log) tool.

These tests explore the SLG1 screens against a real SAP system to capture:
1. SLG1 selection screen (initial screen with filter fields)
2. SLG1 log list (ALV Tree Control with log headers)
3. SLG1 expanded log (tree node expanded to show messages)
4. SLG1 no results screen

Prerequisites:
- SAP system must have application logs (e.g., object EABL or any common log object)
- Run with SAP_LANGUAGE=DE first, then SAP_LANGUAGE=EN to capture both locales
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.models import LoginResult, SnapshotResult, StatusBarInfo, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "slg1_exploration"


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for SLG1 development."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.snapshot

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.yaml"
    filepath = YAML_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        YAML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"Saved YAML snapshot: {filepath}")

    return yaml_content


@pytest.mark.anyio
async def test_slg1_01_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SLG1 selection screen (initial screen with filter fields)."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SLG1"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "slg1_initial", overwrite=True)

    print("=" * 80)
    print("SLG1 initial screen snapshot saved")
    print(f"Snapshot preview:\n{snapshot[:2000]}")
    print("=" * 80)


@pytest.mark.anyio
async def test_slg1_02_capture_log_list(sap_mcp_client: ClientSession) -> None:
    """
    Capture SLG1 log list result (ALV Tree with log headers).

    Uses a common log object - adjust the object name to match your SAP system.
    Try objects like: EABL, EA, /SAPTRX/, BALM, or any custom Z* log object.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SLG1"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill object field - use a common log object that exists in most SAP systems
    # Try DE field name first, then EN
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekt": "EABL"}},
        type(LoginResult),  # Use any ToolResult subclass for fill
    )
    if not fill.success:
        await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object": "EABL"}},
            type(LoginResult),
        )

    # Execute (F8)
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "slg1_log_list", overwrite=True)
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print("=" * 80)
    print("SLG1 log list snapshot saved")
    print(f"Status: {status.message}")
    print(f"Snapshot preview:\n{snapshot[:3000]}")
    print("=" * 80)


@pytest.mark.anyio
async def test_slg1_03_capture_expanded_log(sap_mcp_client: ClientSession) -> None:
    """
    Capture SLG1 tree with first log node expanded to show messages.

    This is the critical snapshot for understanding the ALV Tree Control structure.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SLG1"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill and execute
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekt": "EABL"}},
        type(LoginResult),
    )
    if not fill.success:
        await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object": "EABL"}},
            type(LoginResult),
        )

    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Try to expand the first tree node
    # ALV Tree nodes typically have treeitem role with expand icons
    # Try clicking the first expandable tree item
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[role='treeitem'] img[title*='Expand'], [role='treeitem'] img[title*='Einblenden']"},
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "slg1_expanded_log", overwrite=True)

    print("=" * 80)
    print("SLG1 expanded log snapshot saved")
    print(f"Snapshot preview:\n{snapshot[:4000]}")
    print("=" * 80)


@pytest.mark.anyio
async def test_slg1_04_capture_no_results(sap_mcp_client: ClientSession) -> None:
    """Capture SLG1 screen when no logs are found."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SLG1"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Use a non-existent log object
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekt": "ZZZNOTEXIST99"}},
        type(LoginResult),
    )
    if not fill.success:
        await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object": "ZZZNOTEXIST99"}},
            type(LoginResult),
        )

    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "slg1_no_results", overwrite=True)
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print("=" * 80)
    print("SLG1 no results snapshot saved")
    print(f"Status: {status.message}")
    print(f"Snapshot preview:\n{snapshot[:2000]}")
    print("=" * 80)
```

**Step 2:** Run exploration tests against real SAP to capture DE snapshots:

```bash
SAP_LANGUAGE=DE pytest unittests/test_slg1_exploration.py -v -s --no-header 2>&1 | head -100
```

**Step 3:** Run again with EN to capture EN snapshots:

```bash
SAP_LANGUAGE=EN pytest unittests/test_slg1_exploration.py -v -s --no-header 2>&1 | head -100
```

**Step 4:** After capturing snapshots, examine the YAML files to understand:

- Exact field labels (DE/EN) on the SLG1 selection screen
- ALV Tree structure: how `treeitem` roles appear, expand icon selectors
- Log header columns: log number, object, subobject, ext ID, date, time, user
- Message format: type icon, text, timestamp
- Update the `lang.py` constants from Task 3 if needed

**Expected output files:**

- `unittests/testdata/slg1_exploration/slg1_initial_de.yaml`
- `unittests/testdata/slg1_exploration/slg1_initial_en.yaml`
- `unittests/testdata/slg1_exploration/slg1_log_list_de.yaml`
- `unittests/testdata/slg1_exploration/slg1_log_list_en.yaml`
- `unittests/testdata/slg1_exploration/slg1_expanded_log_de.yaml`
- `unittests/testdata/slg1_exploration/slg1_expanded_log_en.yaml`
- `unittests/testdata/slg1_exploration/slg1_no_results_de.yaml`
- `unittests/testdata/slg1_exploration/slg1_no_results_en.yaml`

---

### Task 5: Write SLG1 Parser

**Files:** Create `src/sapguimcp/parsers/slg1_parser.py`

**Depends on:** Task 4 (need captured snapshots to understand ARIA structure)

**Step 1:** Create the parser file. The exact regex patterns depend on what the ARIA snapshots look like. The skeleton below provides the structure; patterns must be refined after examining the captured YAML snapshots from Task 4:

```python
"""
Parser for SLG1 (Application Log) ARIA snapshots.

Extracts log entries and messages from the ALV Tree Control in SLG1.
The tree has two levels:
  Level 1: Log headers (log number, object, subobject, date, time, user)
  Level 2: Messages within each log (type, text, timestamp)

Handles German and English label support.
"""

import logging
import re
from datetime import UTC, datetime

from sapguimcp.lang import (
    SLG1_INITIAL_SCREEN_DE,
    SLG1_INITIAL_SCREEN_EN,
    SLG1_NO_LOGS_FOUND_DE,
    SLG1_NO_LOGS_FOUND_EN,
)
from sapguimcp.models.slg1_models import (
    SLG1LogEntry,
    SLG1LogListResult,
    SLG1Message,
)

logger = logging.getLogger(__name__)

__all__ = [
    "parse_slg1_log_list",
    "parse_slg1_tree_snapshot",
    "is_slg1_no_results",
    "is_slg1_initial_screen",
]

# Max limits per design doc
MAX_LOGS = 50
MAX_MESSAGES_PER_LOG = 200

# --- Regex patterns (MUST be refined after examining real snapshots) ---

# Tree item pattern for log headers (level 1 nodes)
# Expected ARIA format: treeitem "LogNumber Object SubObject ExtID Date Time User"
# The exact format depends on the SAP ALV Tree Control rendering in WebGUI
_LOG_HEADER_PATTERN = re.compile(
    r'treeitem\s+"(?P<content>[^"]+)"',
    re.IGNORECASE,
)

# Message type indicators in tree items
_MESSAGE_TYPE_MAP = {
    "S": "S",  # Success (green)
    "W": "W",  # Warning (yellow)
    "E": "E",  # Error (red)
    "I": "I",  # Info (blue)
    "A": "A",  # Abort (red, critical)
}


def is_slg1_initial_screen(snapshot: str) -> bool:
    """Check if we're on the SLG1 selection screen."""
    header = "\n".join(snapshot.split("\n")[:15])
    return (
        SLG1_INITIAL_SCREEN_DE.lower() in header.lower()
        or SLG1_INITIAL_SCREEN_EN.lower() in header.lower()
    )


def is_slg1_no_results(snapshot: str) -> bool:
    """Check if SLG1 returned no logs."""
    snapshot_lower = snapshot.lower()
    return (
        SLG1_NO_LOGS_FOUND_DE.lower() in snapshot_lower
        or SLG1_NO_LOGS_FOUND_EN.lower() in snapshot_lower
    )


def parse_slg1_tree_snapshot(
    snapshot: str,
    expanded_snapshots: dict[int, str] | None = None,
) -> list[SLG1LogEntry]:
    """
    Parse the SLG1 ALV Tree snapshot into log entries.

    Args:
        snapshot: The ARIA snapshot of the log list tree
        expanded_snapshots: Optional dict mapping log index to expanded node snapshot

    Returns:
        List of parsed SLG1LogEntry objects

    NOTE: This function's implementation depends heavily on the actual ARIA
    snapshot structure captured in Task 4. The pattern matching must be
    adapted to the real tree item format observed in the snapshots.
    """
    logs: list[SLG1LogEntry] = []
    # TODO: Implement after examining real ARIA snapshots from Task 4
    # 1. Find all level-1 treeitem nodes (log headers)
    # 2. Extract log_number, object, subobject, external_id, date, time, user from each
    # 3. For expanded nodes, parse level-2 treeitem nodes (messages)
    # 4. Extract message type, text, timestamp from each message node
    # 5. Apply MAX_LOGS and MAX_MESSAGES_PER_LOG limits
    return logs


def parse_slg1_messages_from_snapshot(snapshot: str) -> tuple[list[SLG1Message], bool]:
    """
    Parse messages from an expanded log node snapshot.

    Args:
        snapshot: ARIA snapshot after expanding a log node

    Returns:
        Tuple of (messages list, messages_truncated bool)

    NOTE: Implementation depends on Task 4 snapshot analysis.
    """
    messages: list[SLG1Message] = []
    truncated = False
    # TODO: Implement after examining real ARIA snapshots
    # 1. Find all level-2 treeitem nodes within the expanded node
    # 2. Extract type (S/W/E/I/A), text, timestamp
    # 3. Truncate at MAX_MESSAGES_PER_LOG, set truncated=True if more exist
    return messages, truncated


def parse_slg1_log_list(
    snapshot: str,
    expanded_snapshots: dict[int, str] | None = None,
) -> SLG1LogListResult:
    """
    Parse the full SLG1 result into a SLG1LogListResult.

    Args:
        snapshot: ARIA snapshot of the log list screen
        expanded_snapshots: Optional dict mapping log index to expanded snapshot

    Returns:
        SLG1LogListResult with parsed logs
    """
    now = datetime.now(UTC)

    if is_slg1_no_results(snapshot):
        return SLG1LogListResult(
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    logs = parse_slg1_tree_snapshot(snapshot, expanded_snapshots)
    logs_truncated = len(logs) >= MAX_LOGS

    return SLG1LogListResult(
        logs=logs[:MAX_LOGS],
        log_count=len(logs),
        logs_truncated=logs_truncated,
        retrieved_at=now,
    )
```

**Step 2:** Verify the parser module loads:

```bash
python -c "from sapguimcp.parsers.slg1_parser import parse_slg1_log_list, is_slg1_initial_screen; print('OK')"
```

**IMPORTANT:** The parser patterns (`_LOG_HEADER_PATTERN`, message parsing, etc.) are placeholders. After running exploration tests in Task 4 and examining the captured YAML snapshots, the patterns MUST be updated to match the actual ARIA tree structure. The tree format for ALV Tree Control in SAP WebGUI will look different from ALV grids.

---

### Task 6: Write Parser Unit Tests

**Files:** Create `unittests/test_slg1_parser.py`

**Depends on:** Task 4 (captured snapshots), Task 5 (parser)

**Step 1:** Create parser unit tests that load captured YAML snapshots and validate parsing:

```python
"""
Unit tests for SLG1 (Application Log) parser.

Tests parsing of YAML accessibility snapshots from SLG1 log display screens.
"""

from pathlib import Path

import pytest

from sapguimcp.parsers.slg1_parser import (
    is_slg1_initial_screen,
    is_slg1_no_results,
    parse_slg1_log_list,
    parse_slg1_tree_snapshot,
)

SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "slg1_exploration"


def _load_snapshot(name: str) -> str:
    """Load a YAML snapshot file."""
    filepath = SNAPSHOTS_DIR / f"{name}_de.yaml"
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available - run exploration tests first")
    return filepath.read_text(encoding="utf-8")


class TestSLG1ScreenDetection:
    """Tests for detecting SLG1 screen states."""

    def test_detect_initial_screen(self) -> None:
        """Should detect the SLG1 selection screen."""
        snapshot = _load_snapshot("slg1_initial")
        assert is_slg1_initial_screen(snapshot) is True

    def test_detect_no_results(self) -> None:
        """Should detect when no logs are found."""
        snapshot = _load_snapshot("slg1_no_results")
        assert is_slg1_no_results(snapshot) is True

    def test_log_list_is_not_initial(self) -> None:
        """Log list screen should not be detected as initial."""
        snapshot = _load_snapshot("slg1_log_list")
        assert is_slg1_initial_screen(snapshot) is False


class TestSLG1LogListParsing:
    """Tests for parsing the log list tree."""

    def test_parse_log_list_has_entries(self) -> None:
        """Should parse at least one log entry from the list."""
        snapshot = _load_snapshot("slg1_log_list")
        result = parse_slg1_log_list(snapshot)

        assert result.success
        assert result.log_count > 0
        assert len(result.logs) > 0

    def test_log_entry_has_required_fields(self) -> None:
        """Each log entry should have log_number, object, date, time."""
        snapshot = _load_snapshot("slg1_log_list")
        result = parse_slg1_log_list(snapshot)

        if not result.logs:
            pytest.skip("No logs parsed - check snapshot content")

        entry = result.logs[0]
        assert entry.log_number, "log_number should not be empty"
        assert entry.object, "object should not be empty"
        assert entry.date, "date should not be empty"
        assert entry.time, "time should not be empty"

    def test_no_results_returns_empty(self) -> None:
        """No results should return empty log list."""
        snapshot = _load_snapshot("slg1_no_results")
        result = parse_slg1_log_list(snapshot)

        assert result.success
        assert result.log_count == 0
        assert len(result.logs) == 0
        assert result.logs_truncated is False


class TestSLG1MessageParsing:
    """Tests for parsing messages from expanded log nodes."""

    def test_expanded_log_has_messages(self) -> None:
        """Expanded log should contain messages."""
        snapshot = _load_snapshot("slg1_expanded_log")
        logs = parse_slg1_tree_snapshot(snapshot)

        # Find a log with messages (from expanded node)
        logs_with_messages = [log for log in logs if len(log.messages) > 0]
        if not logs_with_messages:
            pytest.skip("No expanded log with messages found in snapshot")

        log = logs_with_messages[0]
        assert log.message_count > 0
        assert len(log.messages) > 0

    def test_message_has_type_and_text(self) -> None:
        """Each message should have a type and text."""
        snapshot = _load_snapshot("slg1_expanded_log")
        logs = parse_slg1_tree_snapshot(snapshot)

        logs_with_messages = [log for log in logs if len(log.messages) > 0]
        if not logs_with_messages:
            pytest.skip("No expanded log with messages found")

        msg = logs_with_messages[0].messages[0]
        assert msg.type in ("S", "W", "E", "I", "A"), f"Unexpected message type: {msg.type}"
        assert msg.text, "Message text should not be empty"
```

**Step 2:** Run parser unit tests (will initially skip if snapshots not captured):

```bash
pytest unittests/test_slg1_parser.py -v --no-header
```

---

### Task 7: Write SLG1 Tool (`slg1_tools.py`)

**Files:** Create `src/sapguimcp/tools/slg1_tools.py`

**Depends on:** Tasks 1-5

**Step 1:** Create the tool file following the SE37 tool pattern:

```python
"""
SLG1 (Application Log) lookup tool.

This module provides a tool to search and read SAP application logs via SLG1,
returning strongly-typed Pydantic models with log entries and messages.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.models import get_browser_manager
from sapguimcp.models.slg1_models import (
    SLG1FileSummary,
    SLG1LogListResult,
)
from sapguimcp.parsers.slg1_parser import (
    MAX_LOGS,
    is_slg1_initial_screen,
    is_slg1_no_results,
    parse_slg1_log_list,
)
from sapguimcp.tools.sap_tool_impl import sap_transaction_impl

logger = logging.getLogger(__name__)

__all__ = ["register_slg1_tools"]


def _format_sap_date(iso_date: str, language: str) -> str:
    """
    Convert ISO date (YYYY-MM-DD) to SAP format based on language.

    DE -> DD.MM.YYYY
    EN -> MM/DD/YYYY
    """
    parts = iso_date.split("-")
    if len(parts) != 3:
        return iso_date  # Return as-is if not valid ISO format
    year, month, day = parts
    if language.upper() == "DE":
        return f"{day}.{month}.{year}"
    return f"{month}/{day}/{year}"


async def _fill_slg1_selection_screen(
    page: Any,
    object_name: str,
    subobject: str | None = None,
    external_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> str | None:
    """
    Fill the SLG1 selection screen fields.

    Returns error message on failure, None on success.
    """
    from sapguimcp.models.config import get_settings
    from sapguimcp.tools.sap_tool_impl import _load_js_with_field_utils

    settings = get_settings()
    language = settings.sap_language

    # Build fields dict - only include fields that have values
    fields: dict[str, str] = {}

    # Object is required
    if language == "DE":
        fields["Objekt"] = object_name
    else:
        fields["Object"] = object_name

    if subobject:
        if language == "DE":
            fields["Unterobjekt"] = subobject
        else:
            fields["Subobject"] = subobject

    if external_id:
        if language == "DE":
            fields["Externe Identifikation"] = external_id
        else:
            fields["External ID"] = external_id

    if from_date:
        sap_date = _format_sap_date(from_date, language)
        # Field names for date range - must be refined after exploration
        if language == "DE":
            fields["Datum ab"] = sap_date
        else:
            fields["From date"] = sap_date

    if to_date:
        sap_date = _format_sap_date(to_date, language)
        if language == "DE":
            fields["Datum bis"] = sap_date
        else:
            fields["To date"] = sap_date

    if from_time:
        if language == "DE":
            fields["Uhrzeit ab"] = from_time
        else:
            fields["From time"] = from_time

    if to_time:
        if language == "DE":
            fields["Uhrzeit bis"] = to_time
        else:
            fields["To time"] = to_time

    # Fill all fields using the JS-based form filler
    try:
        result = await page.evaluate(
            _load_js_with_field_utils("fill_form_fields.js"),
            {"fields": fields},
        )
        not_found = result.get("notFound", [])
        if not_found:
            logger.warning("SLG1 fields not found", extra={"not_found": not_found})
            # Try alternate field names if primary ones fail
            # This will be refined after exploration testing
    except Exception as e:
        return f"Error filling SLG1 selection screen: {e}"

    return None


async def _expand_tree_node(page: Any, node_index: int) -> bool:
    """
    Expand a tree node at the given index by clicking its expand icon.

    Returns True if expansion was successful.
    """
    try:
        # ALV Tree expand icons are typically img elements within treeitem roles
        # The exact selector must be refined after examining real ARIA snapshots
        expand_icons = page.locator(
            "[role='treeitem'] img[title*='Expand'], "
            "[role='treeitem'] img[title*='Einblenden'], "
            "[role='treeitem'] img[title*='expand']"
        )
        count = await expand_icons.count()
        if node_index < count:
            await expand_icons.nth(node_index).click()
            await page.wait_for_timeout(1000)
            await page.wait_for_load_state("networkidle")
            return True
        return False
    except Exception:
        logger.debug("Failed to expand tree node", extra={"index": node_index})
        return False


async def _slg1_lookup(
    page: Any,
    object_name: str,
    subobject: str | None = None,
    external_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> SLG1LogListResult:
    """Execute SLG1 lookup and return parsed results."""
    now = datetime.now(UTC)

    # Navigate to SLG1
    tx_result = await sap_transaction_impl("SLG1")
    if not tx_result.success:
        return SLG1LogListResult.failure(
            f"Failed to navigate to SLG1: {tx_result.error}",
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")

    # Fill selection screen
    fill_error = await _fill_slg1_selection_screen(
        page, object_name, subobject, external_id,
        from_date, to_date, from_time, to_time,
    )
    if fill_error:
        return SLG1LogListResult.failure(
            fill_error,
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    # Execute search (F8)
    await page.keyboard.press("F8")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    # Capture result snapshot
    snapshot: str = await page.locator("body").aria_snapshot()

    # Check for no results
    if is_slg1_no_results(snapshot) or is_slg1_initial_screen(snapshot):
        return SLG1LogListResult(
            logs=[],
            log_count=0,
            logs_truncated=False,
            filters_applied={"object": object_name},
            retrieved_at=now,
        )

    # Parse the log list (level 1 - headers only)
    result = parse_slg1_log_list(snapshot)

    # Expand each log to get messages (level 2)
    # Limit to MAX_LOGS expansions
    for i, log_entry in enumerate(result.logs[:MAX_LOGS]):
        expanded = await _expand_tree_node(page, i)
        if expanded:
            expanded_snapshot: str = await page.locator("body").aria_snapshot()
            # Re-parse with expanded data
            # NOTE: This approach re-parses the whole tree after each expansion.
            # An optimization would be to parse only the new child nodes.
            # For v1, re-parsing is acceptable since we cap at 50 logs.
            result = parse_slg1_log_list(expanded_snapshot)

    # Build filters_applied
    filters: dict[str, str] = {"object": object_name}
    if subobject:
        filters["subobject"] = subobject
    if external_id:
        filters["external_id"] = external_id
    if from_date:
        filters["from_date"] = from_date
    if to_date:
        filters["to_date"] = to_date

    result.filters_applied = filters
    return result


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_slg1_tools(mcp: FastMCP) -> None:
    """Register SLG1 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Search and read SAP application logs from SLG1. "
            "USE THIS instead of sap_transaction('SLG1') - faster and returns structured data. "
            "Returns log entries with messages. Best used when the log object/subobject is known "
            "(e.g., EABL for meter reading, EA for energy, /SAPTRX/ for tracking). "
            "Requires at minimum the 'object' parameter. "
            "Returns up to 50 logs with up to 200 messages each."
        ),
    )
    async def sap_slg1_lookup(
        object: str,
        subobject: str | None = None,
        external_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SLG1LogListResult | SLG1FileSummary:
        """
        Search and read SAP application logs from SLG1.

        Args:
            object: Log object (e.g., 'EABL', 'EA', '/SAPTRX/')
            subobject: Log subobject (optional filter)
            external_id: External identifier (installation number, billing doc, etc.)
            from_date: Start date filter (YYYY-MM-DD format)
            to_date: End date filter (YYYY-MM-DD format)
            from_time: Start time filter (HH:MM:SS format)
            to_time: End time filter (HH:MM:SS format)
            output_file: If provided, write results to this JSON file and return summary.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SLG1LogListResult with log entries and messages, or
            SLG1FileSummary with file path when output_file is provided.
        """
        browser_manager = await get_browser_manager()

        try:
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_slg1_lookup")
        except ValueError as e:
            return SLG1LogListResult.failure(
                f"Session error: {e}",
                logs=[],
                log_count=0,
                logs_truncated=False,
                retrieved_at=datetime.now(UTC),
            )

        try:
            result = await _slg1_lookup(
                page, object, subobject, external_id,
                from_date, to_date, from_time, to_time,
            )
        except Exception as e:
            logger.exception("SLG1 lookup failed")
            result = SLG1LogListResult.failure(
                f"SLG1 lookup error: {e}",
                logs=[],
                log_count=0,
                logs_truncated=False,
                retrieved_at=datetime.now(UTC),
            )

        # Write to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            total_messages = sum(len(log.messages) for log in result.logs)
            return SLG1FileSummary(
                success=result.success,
                error=result.error,
                output_file=str(output_path.absolute()),
                log_count=result.log_count,
                total_messages=total_messages,
                logs_truncated=result.logs_truncated,
                retrieved_at=result.retrieved_at,
            )

        return result
```

**Step 2:** Verify the tool module loads:

```bash
python -c "from sapguimcp.tools.slg1_tools import register_slg1_tools; print('OK')"
```

---

### Task 8: Register Tool in `tools/__init__.py` and `server.py`

**Files:** Modify `src/sapguimcp/tools/__init__.py`, modify `src/sapguimcp/server.py`

**Step 1:** In `src/sapguimcp/tools/__init__.py`, add the import (alphabetical order, after se93_tools):

```python
from sapguimcp.tools.slg1_tools import register_slg1_tools
```

Add to `__all__`:

```python
    "register_slg1_tools",
```

**Step 2:** In `src/sapguimcp/server.py`, add the import in the tools import block (around line 23-41):

```python
from sapguimcp.tools import (
    ...
    register_slg1_tools,
    ...
)
```

**Step 3:** Add the registration call after `register_se93_tools(mcp)` (around line 169):

```python
register_slg1_tools(mcp)
```

**Step 4:** Verify the server starts without errors:

```bash
python -c "from sapguimcp.server import mcp; print('Server loaded OK')"
```

---

### Task 9: Write Integration Test

**Files:** Create `unittests/test_slg1_integration.py`

**Depends on:** Tasks 1-8

**Step 1:** Create the integration test file:

```python
"""
Integration tests for SLG1 (Application Log) lookup tool.

These tests run against a real SAP system to verify the sap_slg1_lookup tool
works correctly end-to-end.
"""

import pytest
from mcp import ClientSession

from sapguimcp.models import LoginResult
from sapguimcp.models.slg1_models import SLG1LogListResult

from .conftest import call_tool_typed


@pytest.mark.anyio
async def test_slg1_lookup_with_object(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_slg1_lookup with a log object.

    Uses EABL (meter reading logs) - adjust to a log object that exists
    in your SAP system.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_slg1_lookup",
        {"object": "EABL"},
        SLG1LogListResult,
    )

    assert result.success, f"SLG1 lookup failed: {result.error}"
    # Log count depends on system data - just verify structure
    assert isinstance(result.log_count, int)
    assert isinstance(result.logs, list)
    assert result.logs_truncated in (True, False)

    if result.logs:
        entry = result.logs[0]
        assert entry.log_number, "log_number should not be empty"
        assert entry.object, "object should not be empty"
        assert entry.date, "date should not be empty"

    print(f"Found {result.log_count} logs, truncated={result.logs_truncated}")


@pytest.mark.anyio
async def test_slg1_lookup_no_results(sap_mcp_client: ClientSession) -> None:
    """Test sap_slg1_lookup with non-existent log object."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_slg1_lookup",
        {"object": "ZZZNOTEXIST99"},
        SLG1LogListResult,
    )

    # Should succeed but with 0 logs (or fail with "no logs found")
    assert result.log_count == 0
    assert len(result.logs) == 0


@pytest.mark.anyio
async def test_slg1_lookup_with_date_filter(sap_mcp_client: ClientSession) -> None:
    """Test sap_slg1_lookup with date range filter."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_slg1_lookup",
        {
            "object": "EABL",
            "from_date": "2025-01-01",
            "to_date": "2025-12-31",
        },
        SLG1LogListResult,
    )

    assert result.success, f"SLG1 lookup failed: {result.error}"
    assert "from_date" in result.filters_applied
    assert "to_date" in result.filters_applied

    print(f"Found {result.log_count} logs with date filter")


@pytest.mark.anyio
async def test_slg1_lookup_with_external_id(sap_mcp_client: ClientSession) -> None:
    """Test sap_slg1_lookup with external ID filter."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_slg1_lookup",
        {
            "object": "EABL",
            "external_id": "123456",
        },
        SLG1LogListResult,
    )

    assert result.success, f"SLG1 lookup failed: {result.error}"
    assert "external_id" in result.filters_applied

    print(f"Found {result.log_count} logs with external_id filter")
```

**Step 2:** Run integration tests (will skip on non-authorized machines):

```bash
pytest unittests/test_slg1_integration.py -v --no-header
```

---

### Task 10: Verify Full Test Suite

**Files:** None (verification only)

**Step 1:** Run all existing tests to ensure nothing is broken:

```bash
pytest unittests/ -v --no-header -x --ignore=unittests/test_slg1_exploration.py --ignore=unittests/test_slg1_integration.py
```

**Step 2:** Run linting:

```bash
ruff check src/sapguimcp/models/slg1_models.py src/sapguimcp/parsers/slg1_parser.py src/sapguimcp/tools/slg1_tools.py
```

**Step 3:** Run type checking:

```bash
mypy src/sapguimcp/models/slg1_models.py src/sapguimcp/parsers/slg1_parser.py src/sapguimcp/tools/slg1_tools.py
```

---

## Implementation Notes

### Critical Dependencies

- **Task 4 (exploration tests) gates Tasks 5-9.** The parser cannot be finalized without examining real ARIA snapshots from SLG1. The ALV Tree Control renders differently from ALV grids, and the exact `treeitem` structure, column layout, expand icon selectors, and message format are unknown until snapshots are captured.
- After capturing snapshots in Task 4, update:
    - `lang.py` constants (Task 3) with verified DE/EN field labels
    - `slg1_parser.py` regex patterns (Task 5) to match real ARIA tree structure
    - Exploration test selectors (Task 4, test 03) for tree expand icons

### ALV Tree Control Key Facts

- SLG1 results display in an ALV Tree Control, not an ALV grid
- Tree nodes use `treeitem` ARIA role
- Expand icons are typically `img` elements within tree items with title attributes like "Expand"/"Einblenden"
- Expanding a node triggers an AJAX call -- must wait for `networkidle` after click
- Level 1 = log headers, Level 2 = messages within a log
- Do NOT expand beyond level 2 (sub-messages, if any, are ignored)

### Limits

| Limit                | Value    | Controlled By                              |
| -------------------- | -------- | ------------------------------------------ |
| Max logs             | 50       | `MAX_LOGS` in `slg1_parser.py`             |
| Max messages per log | 200      | `MAX_MESSAGES_PER_LOG` in `slg1_parser.py` |
| Max tree depth       | 2 levels | Tool logic (only expand level 1 nodes)     |

### Branch

All work should be done on branch `feat/slg1-tool` based off `main`.
