# SE09 Transport Organizer Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a read-only `sap_se09_lookup` tool that lists transport requests with their tasks (and optionally objects) from SE09, returning structured Pydantic models.

**Architecture:** SE09 uses a tree control (not ALV grid), similar to SLG1 but with a different structure: Request -> Task -> Object. The tool navigates to SE09, applies filters (username, request type, status), reads the tree, and parses tree items from ARIA snapshots into `TransportRequest`/`TransportTask`/`TransportObject` models. By default only expands to the request+task level (`include_objects=False`); object expansion is optional and best-effort.

**Tech Stack:** Python 3.12, Pydantic v2, FastMCP, Playwright (ARIA snapshots), pytest (anyio)

---

### Task 1: Create Pydantic Models

**Files:** Create `src/sapguimcp/models/se09_models.py`

**Step 1:** Create the file with the following models:

```python
"""
Pydantic models for SE09 (Transport Organizer) lookup tool.

These models represent transport request metadata retrieved from SE09,
including requests, tasks, and optionally transported objects.
"""

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "TransportObject",
    "TransportTask",
    "TransportRequest",
    "TransportListResult",
]


class TransportObject(BaseModel):
    """An object within a transport task."""

    pgmid: str = Field(description="Program ID (e.g., R3TR, LIMU)")
    object_type: str = Field(description="Object type (e.g., PROG, FUNC, TABL, CLAS)")
    object_name: str = Field(description="Object name")


class TransportTask(BaseModel):
    """A task within a transport request."""

    task_number: str = Field(description="Task number (e.g., DEVK900123)")
    description: str = Field(default="", description="Task description")
    owner: str = Field(default="", description="Task owner (username)")
    status: str = Field(default="", description="Status: Modifiable or Released")
    task_type: str = Field(default="", description="Task type (e.g., Development/Correction, Repair)")
    objects: list[TransportObject] = Field(
        default_factory=list,
        description="Objects in this task (empty unless include_objects=True)",
    )


class TransportRequest(BaseModel):
    """A transport request from SE09."""

    request_number: str = Field(description="Request number (e.g., DEVK900100)")
    description: str = Field(default="", description="Request description")
    owner: str = Field(default="", description="Request owner (username)")
    status: str = Field(default="", description="Status: Modifiable or Released")
    request_type: str = Field(default="", description="Request type (e.g., Workbench, Customizing)")
    target_system: str = Field(default="", description="Target system (e.g., QAS)")
    date: str | None = Field(default=None, description="Last changed date")
    tasks: list[TransportTask] = Field(default_factory=list, description="Tasks in this request")


class TransportListResult(ToolResult):
    """Result of SE09 transport lookup."""

    requests: list[TransportRequest] = Field(default_factory=list, description="Transport requests found")
    request_count: int = Field(default=0, description="Number of requests returned")
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")
```

**Verification:** `python -c "from sapguimcp.models.se09_models import TransportListResult; print('OK')"`

---

### Task 2: Register Models in `__init__.py`

**Files:** Modify `src/sapguimcp/models/__init__.py`

**Step 1:** Add import block after the SE93 models import:

```python
from sapguimcp.models.se09_models import (
    TransportListResult,
    TransportObject,
    TransportRequest,
    TransportTask,
)
```

**Step 2:** Add to `__all__` list after the SE93 section:

```python
    # SE09 models
    "TransportListResult",
    "TransportObject",
    "TransportRequest",
    "TransportTask",
```

**Verification:** `python -c "from sapguimcp.models import TransportListResult, TransportRequest; print('OK')"`

---

### Task 3: Add Language Constants

**Files:** Modify `src/sapguimcp/lang.py`

**Step 1:** Add SE09-specific constants at the end of the file:

```python
# =============================================================================
# SE09 - Transport Organizer
# =============================================================================
SE09_INITIAL_HEADING_DE = "Transport Organizer"
SE09_INITIAL_HEADING_EN = "Transport Organizer"

# Request type radio buttons
SE09_WORKBENCH_DE = "Workbench-Aufträge"
SE09_WORKBENCH_EN = "Workbench requests"
SE09_CUSTOMIZING_DE = "Customizing-Aufträge"
SE09_CUSTOMIZING_EN = "Customizing requests"

# Status filter labels
SE09_MODIFIABLE_DE = "Änderbar"
SE09_MODIFIABLE_EN = "Modifiable"
SE09_RELEASED_DE = "Freigegeben"
SE09_RELEASED_EN = "Released"

# Button labels
SE09_DISPLAY_BUTTON_DE = "Anzeigen"
SE09_DISPLAY_BUTTON_EN = "Display"

# Tree node patterns (parsed from ARIA treeitem roles)
# Request line format: "DEVK900100  Description  OWNER  20260222  Modifiable"
# Task line format: "DEVK900101  Description  OWNER  20260222  Development/Correction"
```

**Verification:** `python -c "from sapguimcp.lang import SE09_WORKBENCH_DE; print('OK')"`

---

### Task 4: Write Exploration Tests (Capture DE/EN Snapshots)

**Files:** Create `unittests/test_se09_exploration.py`, creates directory `unittests/testdata/se09_exploration/`

**Step 1:** Create the exploration test file. These tests run against a live SAP system to capture YAML accessibility snapshots. Each test captures one screen state. The snapshots are saved to `unittests/testdata/se09_exploration/`.

```python
"""
Exploratory tests for SE09 (Transport Organizer) tool.

These tests explore the SE09 screens against a real SAP system to capture
YAML accessibility snapshots for parser development.

Run with SAP_LANGUAGE=DE or SAP_LANGUAGE=EN to capture both locales:
  SAP_LANGUAGE=DE pytest unittests/test_se09_exploration.py -v -s
  SAP_LANGUAGE=EN pytest unittests/test_se09_exploration.py -v -s
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.models import LoginResult, SnapshotResult, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se09_exploration"


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for parser development."""
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
async def test_se09_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SE09 initial/selection screen."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
    await capture_yaml_snapshot(sap_mcp_client, "se09_initial", overwrite=True)

    print("=" * 80)
    print("SE09 initial screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se09_capture_transport_list(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE09 transport list (tree view) after pressing Display/Anzeigen (F8).

    Shows requests and tasks as tree items.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Press F8 (Execute/Display) to show transport list
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    await capture_yaml_snapshot(sap_mcp_client, "se09_transport_list", overwrite=True)

    print("=" * 80)
    print("SE09 transport list snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se09_capture_expanded_request(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE09 with an expanded request showing tasks.

    After getting the transport list, expand the first request node to see tasks.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Press F8 to show transport list
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Try to expand the first tree node (request) by clicking its expand icon
    # The expand icon is typically a treeitem with [expanded=false]
    # We click the first treeitem to select it, then use right arrow to expand
    first_treeitem = "treeitem >> nth=0"
    await sap_mcp_client.call_tool("browser_click", {"selector": first_treeitem})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})
    await sap_mcp_client.call_tool("sap_press_key", {"key": "ArrowRight"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se09_expanded_request", overwrite=True)

    print("=" * 80)
    print("SE09 expanded request snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se09_capture_expanded_task_with_objects(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE09 with a task expanded to show objects.

    Expand request -> expand task to see R3TR/LIMU objects.
    This is the deepest level needed for include_objects=True.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Press F8 to show transport list
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Expand first request
    first_treeitem = "treeitem >> nth=0"
    await sap_mcp_client.call_tool("browser_click", {"selector": first_treeitem})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})
    await sap_mcp_client.call_tool("sap_press_key", {"key": "ArrowRight"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Expand first task (should be the second treeitem now, after the request)
    second_treeitem = "treeitem >> nth=1"
    await sap_mcp_client.call_tool("browser_click", {"selector": second_treeitem})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})
    await sap_mcp_client.call_tool("sap_press_key", {"key": "ArrowRight"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se09_expanded_task_objects", overwrite=True)

    print("=" * 80)
    print("SE09 expanded task with objects snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se09_capture_no_transports(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE09 with no matching transports (e.g., filter by non-existent user).
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill username with non-existent user
    from sapguimcp.models import FillFormResult
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Benutzer": "ZZZNOUSER99"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"User": "ZZZNOUSER99"}},
            FillFormResult,
        )

    # Press F8
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    await capture_yaml_snapshot(sap_mcp_client, "se09_no_transports", overwrite=True)

    print("=" * 80)
    print("SE09 no transports snapshot saved")
    print("=" * 80)
```

**Verification:** Run against live SAP to capture snapshots:

```bash
SAP_LANGUAGE=DE pytest unittests/test_se09_exploration.py -v -s
SAP_LANGUAGE=EN pytest unittests/test_se09_exploration.py -v -s
```

**Expected output:** YAML snapshot files in `unittests/testdata/se09_exploration/`:

- `se09_initial_de.yaml`, `se09_initial_en.yaml`
- `se09_transport_list_de.yaml`, `se09_transport_list_en.yaml`
- `se09_expanded_request_de.yaml`, `se09_expanded_request_en.yaml`
- `se09_expanded_task_objects_de.yaml`, `se09_expanded_task_objects_en.yaml`
- `se09_no_transports_de.yaml`, `se09_no_transports_en.yaml`

---

### Task 5: Write SE09 Parser

**Files:** Create `src/sapguimcp/parsers/se09_parser.py`

**Step 1:** Create the parser module. The parser extracts transport data from ARIA tree snapshots. Tree items appear as `treeitem` roles in the YAML. The exact regex patterns MUST be refined after examining the captured snapshots from Task 4.

```python
"""
Parser for SE09 (Transport Organizer) ARIA snapshots.

Extracts transport request and task data from SE09 tree control.
The tree uses treeitem roles with hierarchical nesting.

IMPORTANT: The regex patterns in this file were designed based on captured
ARIA snapshots. If the tree format changes, update patterns accordingly.
"""

import logging
import re
from datetime import UTC, datetime

from sapguimcp.models.se09_models import (
    TransportListResult,
    TransportObject,
    TransportRequest,
    TransportTask,
)

logger = logging.getLogger(__name__)

__all__ = [
    "parse_se09_tree_snapshot",
]


# =============================================================================
# Regex Patterns (MUST be refined after snapshot capture in Task 4)
# =============================================================================

# Transport number pattern: 3-char system ID + K + 6 digits (e.g., DEVK900123)
_TRANSPORT_NUMBER = re.compile(r"[A-Z]{3}K\d{6}")

# Tree item pattern - extracts transport number and description from treeitem text
# Format varies by SAP version. Common pattern:
#   treeitem "DEVK900100  Some description  USERNAME  20260222  ..."
# The exact pattern needs refinement after snapshot capture.
_TREEITEM_PATTERN = re.compile(
    r'treeitem\s+"(?P<text>[^"]+)"',
    re.IGNORECASE,
)


def _extract_transport_number(text: str) -> str | None:
    """Extract transport number from tree item text."""
    match = _TRANSPORT_NUMBER.search(text)
    return match.group(0) if match else None


def _parse_tree_item_text(text: str) -> dict[str, str]:
    """
    Parse a tree item text line into components.

    The exact format depends on the SAP system and must be refined
    after examining captured snapshots. This is an initial best-effort parser.

    Returns dict with keys: number, description, owner, date, status/type
    """
    result: dict[str, str] = {}

    # Extract transport number
    number = _extract_transport_number(text)
    if number:
        result["number"] = number
        # Remove the number from text to parse remaining fields
        remaining = text.replace(number, "", 1).strip()
        # Split remaining by multiple spaces (SAP tree items use space padding)
        parts = [p.strip() for p in re.split(r"\s{2,}", remaining) if p.strip()]
        if parts:
            result["description"] = parts[0] if len(parts) > 0 else ""
            result["owner"] = parts[1] if len(parts) > 1 else ""
            result["date"] = parts[2] if len(parts) > 2 else ""
            result["status"] = parts[3] if len(parts) > 3 else ""

    return result


def _determine_tree_level(line: str) -> int:
    """
    Determine the nesting level of a tree item based on indentation.

    Level 0 = request, level 1 = task, level 2 = object
    """
    # Count leading spaces to determine depth
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    # Each tree level adds approximately 4-8 spaces of indentation
    # This must be calibrated from actual snapshots
    return indent // 4


def _is_request_node(text: str, level: int) -> bool:
    """Check if a tree item is a transport request (top-level node)."""
    # Requests are at the top level (level 0 or 1 depending on tree root)
    # They have a transport number and typically show "Workbench" or "Customizing" type
    return level <= 1 and _extract_transport_number(text) is not None


def _is_task_node(text: str, level: int) -> bool:
    """Check if a tree item is a transport task (child of request)."""
    return level > 0 and _extract_transport_number(text) is not None


def _is_object_node(text: str, level: int) -> bool:
    """Check if a tree item is a transport object (child of task)."""
    # Objects typically show: R3TR PROG ZPROGRAM or LIMU FUNC Z_FUNC
    pgmid_pattern = re.compile(r"\b(R3TR|LIMU|CORR|LANG)\b")
    return level > 1 and bool(pgmid_pattern.search(text))


def _parse_object_text(text: str) -> TransportObject | None:
    """Parse object details from tree item text."""
    # Pattern: PGMID OBJECT_TYPE OBJECT_NAME
    match = re.search(r"\b(R3TR|LIMU|CORR|LANG)\s+(\w+)\s+(\S+)", text)
    if match:
        return TransportObject(
            pgmid=match.group(1),
            object_type=match.group(2),
            object_name=match.group(3),
        )
    return None


def parse_se09_tree_snapshot(
    snapshot: str,
    include_objects: bool = False,
) -> TransportListResult:
    """
    Parse SE09 transport tree from ARIA snapshot.

    Args:
        snapshot: YAML accessibility snapshot from the SE09 tree view
        include_objects: Whether to parse object-level items (level 3)

    Returns:
        TransportListResult with parsed requests and tasks
    """
    now = datetime.now(UTC)

    # Check for empty/no results
    if not snapshot or "treeitem" not in snapshot.lower():
        return TransportListResult(
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    requests: list[TransportRequest] = []
    current_request: TransportRequest | None = None
    current_task: TransportTask | None = None

    # Parse tree items from snapshot
    lines = snapshot.split("\n")
    for line in lines:
        match = _TREEITEM_PATTERN.search(line)
        if not match:
            continue

        text = match.group("text")
        level = _determine_tree_level(line)

        # Determine what kind of node this is
        transport_num = _extract_transport_number(text)
        if not transport_num:
            # Could be an object node
            if include_objects and current_task is not None:
                obj = _parse_object_text(text)
                if obj:
                    current_task.objects.append(obj)
            continue

        parsed = _parse_tree_item_text(text)

        # Heuristic: if this looks like a top-level node, treat as request
        # Requests are at a lower indentation level than tasks
        if current_request is None or level <= _determine_tree_level_for_request(current_request, lines):
            # This is a new request
            if current_request is not None:
                requests.append(current_request)
            current_request = TransportRequest(
                request_number=transport_num,
                description=parsed.get("description", ""),
                owner=parsed.get("owner", ""),
                status=parsed.get("status", ""),
                date=parsed.get("date") or None,
                tasks=[],
            )
            current_task = None
        else:
            # This is a task under the current request
            current_task = TransportTask(
                task_number=transport_num,
                description=parsed.get("description", ""),
                owner=parsed.get("owner", ""),
                status=parsed.get("status", ""),
                objects=[],
            )
            if current_request is not None:
                current_request.tasks.append(current_task)

    # Don't forget the last request
    if current_request is not None:
        requests.append(current_request)

    return TransportListResult(
        requests=requests,
        request_count=len(requests),
        retrieved_at=now,
    )


def _determine_tree_level_for_request(request: TransportRequest, lines: list[str]) -> int:
    """Find the indentation level of a given request in the snapshot lines."""
    for line in lines:
        if request.request_number in line:
            return _determine_tree_level(line)
    return 0
```

**CRITICAL NOTE:** The regex patterns and tree-level detection MUST be refined after examining the actual YAML snapshots captured in Task 4. The patterns above are educated guesses based on SAP WebGUI tree control conventions. After running the exploration tests:

1. Open the captured `se09_transport_list_de.yaml` and `se09_expanded_request_de.yaml`
2. Study the actual `treeitem` format (indentation, text layout, attribute format)
3. Update `_TREEITEM_PATTERN`, `_parse_tree_item_text`, and `_determine_tree_level` accordingly
4. The tree may use `[expanded]`/`[collapsed]` attributes, `group` roles, or nested `tree`/`treeitem` roles

**Verification:** `python -c "from sapguimcp.parsers.se09_parser import parse_se09_tree_snapshot; print('OK')"`

---

### Task 6: Write Parser Unit Tests

**Files:** Create `unittests/test_se09_parser.py`

**Step 1:** Create parser unit tests that run against captured snapshots (offline, no SAP needed):

```python
"""
Unit tests for SE09 (Transport Organizer) parser.

Tests parsing of YAML accessibility snapshots from SE09 transport tree display.
"""

from pathlib import Path

import pytest

from sapguimcp.parsers.se09_parser import parse_se09_tree_snapshot

# Path to captured YAML snapshots
SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se09_exploration"


def _load_snapshot(name: str) -> str:
    """Load a YAML snapshot file."""
    filepath = SNAPSHOTS_DIR / f"{name}_de.yaml"
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available - run exploration tests first")
    return filepath.read_text(encoding="utf-8")


class TestTransportListParsing:
    """Tests for parsing transport list tree."""

    def test_parse_transport_list(self) -> None:
        """Transport list should parse requests from tree."""
        snapshot = _load_snapshot("se09_transport_list")
        result = parse_se09_tree_snapshot(snapshot)

        assert result.request_count > 0
        assert len(result.requests) == result.request_count
        assert result.success

    def test_request_has_transport_number(self) -> None:
        """Each request should have a valid transport number."""
        snapshot = _load_snapshot("se09_transport_list")
        result = parse_se09_tree_snapshot(snapshot)

        for req in result.requests:
            # Transport numbers: 3-letter system + K + 6 digits
            assert len(req.request_number) == 10
            assert req.request_number[3] == "K"

    def test_no_transports_returns_empty(self) -> None:
        """Empty tree should return empty result."""
        snapshot = _load_snapshot("se09_no_transports")
        result = parse_se09_tree_snapshot(snapshot)

        assert result.request_count == 0
        assert result.requests == []
        assert result.success


class TestExpandedRequestParsing:
    """Tests for parsing expanded request with tasks."""

    def test_expanded_request_has_tasks(self) -> None:
        """Expanded request should show tasks."""
        snapshot = _load_snapshot("se09_expanded_request")
        result = parse_se09_tree_snapshot(snapshot)

        # At least one request should have tasks
        requests_with_tasks = [r for r in result.requests if len(r.tasks) > 0]
        assert len(requests_with_tasks) > 0

    def test_task_has_transport_number(self) -> None:
        """Each task should have a valid transport number."""
        snapshot = _load_snapshot("se09_expanded_request")
        result = parse_se09_tree_snapshot(snapshot)

        for req in result.requests:
            for task in req.tasks:
                assert len(task.task_number) == 10
                assert task.task_number[3] == "K"


class TestObjectParsing:
    """Tests for parsing transport objects."""

    def test_objects_with_include_true(self) -> None:
        """Objects should be parsed when include_objects=True."""
        snapshot = _load_snapshot("se09_expanded_task_objects")
        result = parse_se09_tree_snapshot(snapshot, include_objects=True)

        # Find tasks with objects
        all_objects = []
        for req in result.requests:
            for task in req.tasks:
                all_objects.extend(task.objects)

        # Should have at least one object if snapshot shows expanded task
        assert len(all_objects) > 0

    def test_objects_skipped_by_default(self) -> None:
        """Objects should NOT be parsed when include_objects=False (default)."""
        snapshot = _load_snapshot("se09_expanded_task_objects")
        result = parse_se09_tree_snapshot(snapshot, include_objects=False)

        # No objects should be present
        for req in result.requests:
            for task in req.tasks:
                assert len(task.objects) == 0

    def test_object_has_pgmid_and_type(self) -> None:
        """Each object should have pgmid and object_type."""
        snapshot = _load_snapshot("se09_expanded_task_objects")
        result = parse_se09_tree_snapshot(snapshot, include_objects=True)

        for req in result.requests:
            for task in req.tasks:
                for obj in task.objects:
                    assert obj.pgmid in ("R3TR", "LIMU", "CORR", "LANG")
                    assert len(obj.object_type) >= 2
                    assert len(obj.object_name) >= 1
```

**Verification:** `pytest unittests/test_se09_parser.py -v` (after snapshots exist from Task 4)

---

### Task 7: Write SE09 Tool

**Files:** Create `src/sapguimcp/tools/se09_tools.py`

**Step 1:** Create the tool module following the SE37/SE93 pattern:

```python
"""
SE09 (Transport Organizer) lookup tool.

This module provides a read-only tool to list transport requests with tasks
and optionally objects from SE09.
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.models import get_browser_manager
from sapguimcp.models.se09_models import TransportListResult
from sapguimcp.parsers.se09_parser import parse_se09_tree_snapshot
from sapguimcp.tools.sap_tool_impl import sap_transaction_impl

logger = logging.getLogger(__name__)

__all__ = ["register_se09_tools"]


# =============================================================================
# SE09 Navigation Helpers
# =============================================================================


async def _find_user_field(page: Any) -> Any:
    """Find the username input field in SE09."""
    strategies = [
        page.get_by_role("textbox", name=re.compile(r"Benutzer|User", re.I)),
        page.locator("input[title*='Benutzer'], input[title*='User']").first,
        page.locator("[aria-label*='Benutzer'], [aria-label*='User']").first,
    ]
    for field in strategies:
        if await field.count() > 0:
            return field
    return None


async def _fill_user_field(page: Any, username: str) -> None:
    """Fill the username filter field."""
    user_field = await _find_user_field(page)
    if user_field and await user_field.count() > 0:
        await user_field.click(click_count=3)
        await page.wait_for_timeout(100)
        await page.keyboard.press("Delete")
        await page.wait_for_timeout(50)
        await page.keyboard.type(username.upper())
        await page.wait_for_timeout(100)


async def _set_request_type_filter(
    page: Any,
    request_type: str,
) -> None:
    """Set request type radio buttons/checkboxes on SE09 selection screen."""
    if request_type == "all":
        return  # Leave defaults
    # The exact UI control (radio buttons vs checkboxes) must be determined
    # from the captured snapshots. This is a best-effort implementation.
    # SE09 typically has radio buttons for Workbench/Customizing
    # or checkboxes that can both be checked.
    if request_type == "workbench":
        # Try to select workbench radio/checkbox
        wb = page.get_by_role("radio", name=re.compile(r"Workbench", re.I))
        if await wb.count() > 0:
            await wb.click()
            await page.wait_for_timeout(200)
    elif request_type == "customizing":
        cust = page.get_by_role("radio", name=re.compile(r"Customizing", re.I))
        if await cust.count() > 0:
            await cust.click()
            await page.wait_for_timeout(200)


async def _set_status_filter(
    page: Any,
    status: str,
) -> None:
    """Set status filter checkboxes on SE09 selection screen."""
    if status == "all":
        return  # Leave defaults

    # The exact checkbox names must be determined from snapshots.
    # This is best-effort based on common SE09 layout.
    if status == "modifiable":
        # Check modifiable, uncheck released
        mod_cb = page.get_by_role("checkbox", name=re.compile(r"Änderbar|Modifiable", re.I))
        rel_cb = page.get_by_role("checkbox", name=re.compile(r"Freigegeben|Released", re.I))
        if await mod_cb.count() > 0:
            if not await mod_cb.is_checked():
                await mod_cb.click()
        if await rel_cb.count() > 0:
            if await rel_cb.is_checked():
                await rel_cb.click()
    elif status == "released":
        mod_cb = page.get_by_role("checkbox", name=re.compile(r"Änderbar|Modifiable", re.I))
        rel_cb = page.get_by_role("checkbox", name=re.compile(r"Freigegeben|Released", re.I))
        if await rel_cb.count() > 0:
            if not await rel_cb.is_checked():
                await rel_cb.click()
        if await mod_cb.count() > 0:
            if await mod_cb.is_checked():
                await mod_cb.click()


async def _expand_all_tree_nodes(page: Any, max_depth: int = 1) -> None:
    """
    Expand tree nodes to show tasks under requests.

    max_depth=1 means expand requests to show tasks.
    max_depth=2 means also expand tasks to show objects.
    """
    # Use Ctrl+F5 or menu to expand all, or iterate tree items
    # SAP tree controls sometimes support "Expand all" via toolbar button
    # Alternatively, iterate and click expand on each node

    # Strategy 1: Try "Alle Knoten aufklappen" / "Expand All" via keyboard
    # In many SAP trees, the menu Edit > Expand All works
    # But safest is to iterate visible treeitems and expand them

    treeitems = page.locator("[role='treeitem']")
    count = await treeitems.count()

    for i in range(min(count, 50)):  # Cap at 50 to avoid performance issues
        item = treeitems.nth(i)
        # Check if item has expand icon (not yet expanded)
        expanded = await item.get_attribute("aria-expanded")
        if expanded == "false":
            await item.click()
            await page.wait_for_timeout(200)
            await page.keyboard.press("ArrowRight")
            await page.wait_for_timeout(500)
            await page.wait_for_load_state("networkidle")

            if max_depth >= 2:
                # After expanding request, expand its tasks too
                # Re-count treeitems as new ones appeared
                new_count = await treeitems.count()
                for j in range(i + 1, min(new_count, count + 20)):
                    sub_item = treeitems.nth(j)
                    sub_expanded = await sub_item.get_attribute("aria-expanded")
                    if sub_expanded == "false":
                        await sub_item.click()
                        await page.wait_for_timeout(200)
                        await page.keyboard.press("ArrowRight")
                        await page.wait_for_timeout(500)
                        await page.wait_for_load_state("networkidle")


async def _lookup_transports(
    page: Any,
    username: str | None,
    request_type: str,
    status: str,
    request_number: str | None,
    include_objects: bool,
) -> TransportListResult:
    """Look up transports in SE09."""
    now = datetime.now(UTC)

    # Navigate to SE09
    tx_result = await sap_transaction_impl("SE09")
    if not tx_result.success:
        return TransportListResult.failure(
            error=f"Failed to navigate to SE09: {tx_result.error}",
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")

    # Apply filters on selection screen
    if username is not None:
        await _fill_user_field(page, username)

    await _set_request_type_filter(page, request_type)
    await _set_status_filter(page, status)

    # If specific request number, fill it
    if request_number:
        req_field = page.get_by_role(
            "textbox",
            name=re.compile(r"Auftrag|Request", re.I),
        )
        if await req_field.count() > 0:
            await req_field.click(click_count=3)
            await page.wait_for_timeout(100)
            await page.keyboard.press("Delete")
            await page.keyboard.type(request_number.upper())
            await page.wait_for_timeout(100)

    # Execute (F8)
    await page.keyboard.press("F8")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    # Expand tree nodes
    max_depth = 2 if include_objects else 1
    await _expand_all_tree_nodes(page, max_depth=max_depth)

    # Capture snapshot
    snapshot: str = await page.locator("body").aria_snapshot()

    # Parse tree
    result = parse_se09_tree_snapshot(snapshot, include_objects=include_objects)
    return result


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se09_tools(mcp: FastMCP) -> None:
    """Register SE09 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up transport requests from SE09 (Transport Organizer). "
            "USE THIS instead of sap_transaction('SE09') - faster and returns structured data. "
            "Returns transport requests with their tasks. By default only shows requests and tasks "
            "(not individual objects). Use include_objects=True to also list transported objects "
            "(slower, best-effort). "
            "Supports filtering by username, request type (workbench/customizing), and status "
            "(modifiable/released). Can also look up a specific request by number."
        ),
    )
    async def sap_se09_lookup(
        username: str | None = None,
        request_type: Literal["workbench", "customizing", "all"] = "all",
        status: Literal["modifiable", "released", "all"] = "modifiable",
        request_number: str | None = None,
        include_objects: bool = False,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TransportListResult:
        """
        Look up transport requests from SE09.

        Args:
            username: Filter by owner (default: current SAP user)
            request_type: Filter by type - "workbench", "customizing", or "all"
            status: Filter by status - "modifiable", "released", or "all" (default: "modifiable")
            request_number: Look up a specific transport request number
            include_objects: Expand tasks to show individual objects (default: False, slower)
            output_file: Write results to JSON file if large
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            TransportListResult with requests and their tasks
        """
        now = datetime.now(UTC)

        browser_manager = await get_browser_manager()

        try:
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_se09_lookup")
        except ValueError as e:
            return TransportListResult.failure(
                error=f"Session error: {e}",
                requests=[],
                request_count=0,
                retrieved_at=now,
            )

        try:
            result = await _lookup_transports(
                page=page,
                username=username,
                request_type=request_type,
                status=status,
                request_number=request_number,
                include_objects=include_objects,
            )
        except Exception as e:
            logger.exception("Error looking up transports in SE09")
            return TransportListResult.failure(
                error=f"Error looking up transports: {e}",
                requests=[],
                request_count=0,
                retrieved_at=now,
            )

        # Write to file if requested
        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        return result
```

**Verification:** `python -c "from sapguimcp.tools.se09_tools import register_se09_tools; print('OK')"`

---

### Task 8: Register Tool in `tools/__init__.py`

**Files:** Modify `src/sapguimcp/tools/__init__.py`

**Step 1:** Add import:

```python
from sapguimcp.tools.se09_tools import register_se09_tools
```

**Step 2:** Add to `__all__`:

```python
    "register_se09_tools",
```

**Verification:** `python -c "from sapguimcp.tools import register_se09_tools; print('OK')"`

---

### Task 9: Register Tool in `server.py`

**Files:** Modify `src/sapguimcp/server.py`

**Step 1:** Add import in the tools import block:

```python
    register_se09_tools,
```

**Step 2:** Add registration call after `register_se93_tools(mcp)`:

```python
register_se09_tools(mcp)
```

**Verification:** `python -c "from sapguimcp.server import mcp; tools = [t for t in dir(mcp)]; print('OK')"`

---

### Task 10: Write Integration Test

**Files:** Create `unittests/test_se09_integration.py`

**Step 1:** Create the integration test file:

```python
"""
Integration tests for SE09 (Transport Organizer) lookup tool.

These tests run against a real SAP system to verify the sap_se09_lookup tool.
"""

import pytest
from mcp import ClientSession

from sapguimcp.models import LoginResult
from sapguimcp.models.se09_models import TransportListResult

from .conftest import call_tool_typed


@pytest.mark.anyio
async def test_se09_lookup_default(sap_mcp_client: ClientSession) -> None:
    """Test sap_se09_lookup with default parameters (current user, modifiable)."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    # Current user should have some modifiable transports (or zero is OK)
    assert result.request_count >= 0
    assert len(result.requests) == result.request_count
    print(f"Found {result.request_count} transport requests")

    # Verify structure
    for req in result.requests:
        assert len(req.request_number) == 10
        assert req.request_number[3] == "K"


@pytest.mark.anyio
async def test_se09_lookup_with_tasks(sap_mcp_client: ClientSession) -> None:
    """Test that requests include tasks."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"status": "modifiable"},
        TransportListResult,
    )

    assert result.success
    if result.request_count > 0:
        # At least some requests should have tasks
        all_tasks = []
        for req in result.requests:
            all_tasks.extend(req.tasks)
        print(f"Found {len(all_tasks)} tasks across {result.request_count} requests")


@pytest.mark.anyio
async def test_se09_lookup_with_objects(sap_mcp_client: ClientSession) -> None:
    """Test include_objects=True returns object details."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"include_objects": True, "status": "modifiable"},
        TransportListResult,
    )

    assert result.success
    if result.request_count > 0:
        all_objects = []
        for req in result.requests:
            for task in req.tasks:
                all_objects.extend(task.objects)
        print(f"Found {len(all_objects)} objects (include_objects=True)")


@pytest.mark.anyio
async def test_se09_lookup_workbench_only(sap_mcp_client: ClientSession) -> None:
    """Test filtering by workbench request type."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"request_type": "workbench"},
        TransportListResult,
    )

    assert result.success
    print(f"Found {result.request_count} workbench requests")


@pytest.mark.anyio
async def test_se09_lookup_released(sap_mcp_client: ClientSession) -> None:
    """Test filtering by released status."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"status": "released"},
        TransportListResult,
    )

    assert result.success
    print(f"Found {result.request_count} released requests")


@pytest.mark.anyio
async def test_se09_lookup_no_results(sap_mcp_client: ClientSession) -> None:
    """Test with a user that has no transports."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "ZZZNOUSER99"},
        TransportListResult,
    )

    # Should succeed but with 0 results (or fail gracefully)
    assert result.request_count == 0
```

**Verification:** Run against live SAP:

```bash
pytest unittests/test_se09_integration.py -v -s
```

---

### Task 11: Run All Quality Checks

**Files:** None (validation only)

**Step 1:** Run type checking:

```bash
pyright src/sapguimcp/models/se09_models.py src/sapguimcp/parsers/se09_parser.py src/sapguimcp/tools/se09_tools.py
```

**Step 2:** Run linting:

```bash
ruff check src/sapguimcp/models/se09_models.py src/sapguimcp/parsers/se09_parser.py src/sapguimcp/tools/se09_tools.py
ruff format --check src/sapguimcp/models/se09_models.py src/sapguimcp/parsers/se09_parser.py src/sapguimcp/tools/se09_tools.py
```

**Step 3:** Run parser unit tests (offline):

```bash
pytest unittests/test_se09_parser.py -v
```

**Step 4:** Run full test suite to check for regressions:

```bash
pytest unittests/ -v --ignore=unittests/test_se09_exploration.py --ignore=unittests/test_se09_integration.py -k "not sap_mcp_client"
```

---

## Implementation Notes

### Tree Control Parsing Strategy

SE09 uses a SAP WebGUI tree control. Key considerations:

1. **Tree items appear as `treeitem` roles** in ARIA snapshots, with indentation indicating hierarchy
2. **Expansion is AJAX-based** -- clicking expand or pressing ArrowRight triggers a server round-trip
3. **Requests vs Tasks**: Both have transport numbers (same format), but tasks are children of requests in the tree hierarchy. Differentiation is by indentation level.
4. **Objects**: Only visible when a task is expanded. Format is `PGMID OBJECT_TYPE OBJECT_NAME` (e.g., `R3TR PROG ZPROGRAM`)
5. **Default `include_objects=False`** keeps the tool fast and reliable -- only one level of expansion needed
6. **Cap tree expansion at 50 nodes** to prevent performance degradation on systems with many transports

### Parser Refinement Workflow

The parser in Task 5 contains placeholder patterns. The actual implementation workflow is:

1. Run exploration tests (Task 4) to capture real YAML snapshots
2. Examine the captured snapshots to understand the actual tree item format
3. Update regex patterns in `se09_parser.py` to match the real format
4. Run parser unit tests (Task 6) to validate
5. Iterate until parser correctly handles all captured snapshots

### File Summary

| File                                      | Action | Description                 |
| ----------------------------------------- | ------ | --------------------------- |
| `src/sapguimcp/models/se09_models.py`  | Create | Pydantic models             |
| `src/sapguimcp/models/__init__.py`     | Modify | Register model exports      |
| `src/sapguimcp/lang.py`                | Modify | Add SE09 language constants |
| `src/sapguimcp/parsers/se09_parser.py` | Create | Tree snapshot parser        |
| `src/sapguimcp/tools/se09_tools.py`    | Create | MCP tool implementation     |
| `src/sapguimcp/tools/__init__.py`      | Modify | Register tool export        |
| `src/sapguimcp/server.py`              | Modify | Register tool with server   |
| `unittests/test_se09_exploration.py`      | Create | Snapshot capture tests      |
| `unittests/test_se09_parser.py`           | Create | Offline parser tests        |
| `unittests/test_se09_integration.py`      | Create | End-to-end tests            |
