# Citrix Relay Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Citrix relay backend that proxies `SapUiBackend` calls over file-based RPC to a relay agent running inside a Citrix session, enabling SAP GUI automation when direct COM/browser access is unavailable.

**Architecture:** `CitrixBackend` on the client side writes JSON command files to a shared directory and polls for JSON response files. A standalone `RelayAgent` on the Citrix server reads commands, delegates to `DesktopBackend` via COM, and writes responses. Communication uses atomic file writes (tmp+rename) with heartbeat-based liveness detection and shared-secret token authentication.

**Tech Stack:** Python 3.11+, pydantic, asyncio, PyInstaller (for relay .exe), NTFS ACLs (win32security)

**Design Spec:** `docs/design/citrix-relay-backend-design.md`

---

## File Structure

```
src/sapwebguimcp/
├── backend/
│   ├── citrix/
│   │   ├── __init__.py            # Re-exports CitrixBackend
│   │   ├── _backend.py            # CitrixBackend (SapUiBackend proxy)
│   │   ├── _relay_agent.py        # RelayAgent (server-side, standalone)
│   │   ├── _transport.py          # atomic_write_json, read_json, message formats
│   │   └── _exceptions.py         # RelayError, RelayDisconnectedError, RelayProtocolError
│   ├── manager.py                 # MODIFY: add citrix branch
│   ├── types.py                   # MODIFY: ScreenSnapshot union stays (CitrixBackend returns ComTreeSnapshot)
│   └── protocol.py                # MODIFY: docstring only (backend_type includes "citrix")
├── models/
│   └── config.py                  # MODIFY: BackendType, new citrix settings
├── tools/
│   └── _backend_utils.py          # MODIFY: _is_desktop_backend → _is_com_backend

unittests/
├── citrix/
│   ├── __init__.py
│   ├── test_transport.py          # atomic_write_json, serialization
│   ├── test_exceptions.py         # Exception types
│   ├── test_citrix_backend.py     # CitrixBackend._call, _deserialize, _check_heartbeat
│   ├── test_relay_agent.py        # RelayAgent._execute, _serialize, token validation
│   └── test_manager_citrix.py     # BackendManager citrix branch
├── test_backend_manager.py        # MODIFY: add citrix acceptance test
├── test_backend_utils.py          # NEW: test _is_com_backend

relay/
├── relay_agent.py                 # Entry point for PyInstaller: from sapwebguimcp.backend.citrix._relay_agent import main; main()
└── relay.spec                     # PyInstaller spec (Phase 2, placeholder)
```

---

### Task 1: Transport Layer — Exceptions & Atomic I/O

**Files:**
- Create: `src/sapwebguimcp/backend/citrix/__init__.py`
- Create: `src/sapwebguimcp/backend/citrix/_exceptions.py`
- Create: `src/sapwebguimcp/backend/citrix/_transport.py`
- Create: `unittests/citrix/__init__.py`
- Create: `unittests/citrix/test_exceptions.py`
- Create: `unittests/citrix/test_transport.py`

- [ ] **Step 1: Write failing tests for exceptions**

```python
# unittests/citrix/test_exceptions.py
"""Tests for Citrix relay exceptions."""

from sapwebguimcp.backend.citrix._exceptions import (
    RelayDisconnectedError,
    RelayError,
    RelayProtocolError,
)


def test_relay_error_is_runtime_error() -> None:
    err = RelayError("something broke")
    assert isinstance(err, RuntimeError)
    assert str(err) == "something broke"


def test_relay_disconnected_error_is_relay_error() -> None:
    err = RelayDisconnectedError("heartbeat stale")
    assert isinstance(err, RelayError)


def test_relay_protocol_error_is_relay_error() -> None:
    err = RelayProtocolError("version mismatch")
    assert isinstance(err, RelayError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_exceptions.py -v`
Expected: ImportError — module not found

- [ ] **Step 3: Implement exceptions**

```python
# src/sapwebguimcp/backend/citrix/_exceptions.py
"""Citrix relay exception hierarchy."""


class RelayError(RuntimeError):
    """Base error for relay communication failures."""


class RelayDisconnectedError(RelayError):
    """Raised when the relay agent is unreachable (heartbeat stale or shutdown)."""


class RelayProtocolError(RelayError):
    """Raised on protocol version mismatch during handshake."""
```

```python
# src/sapwebguimcp/backend/citrix/__init__.py
"""Citrix relay backend — file-based RPC proxy to DesktopBackend in a Citrix session."""
```

```python
# unittests/citrix/__init__.py
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_exceptions.py -v`
Expected: 3 passed

- [ ] **Step 5: Write failing tests for transport**

```python
# unittests/citrix/test_transport.py
"""Tests for Citrix relay transport utilities."""

import json
from pathlib import Path

from sapwebguimcp.backend.citrix._transport import atomic_write_json, read_json


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "test.json"
    atomic_write_json(target, {"key": "value"})
    assert target.exists()
    assert json.loads(target.read_text()) == {"key": "value"}


def test_atomic_write_no_leftover_tmp(tmp_path: Path) -> None:
    target = tmp_path / "test.json"
    atomic_write_json(target, {"a": 1})
    tmp_file = target.with_suffix(".json.tmp")
    assert not tmp_file.exists()


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "test.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text()) == {"v": 2}


def test_read_json(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    target.write_text(json.dumps({"hello": "world"}))
    assert read_json(target) == {"hello": "world"}


def test_read_json_missing_file(tmp_path: Path) -> None:
    target = tmp_path / "nope.json"
    assert read_json(target) is None


def test_read_json_corrupted_file(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    target.write_text("not valid json{{{")
    assert read_json(target) is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_transport.py -v`
Expected: ImportError

- [ ] **Step 7: Implement transport**

```python
# src/sapwebguimcp/backend/citrix/_transport.py
"""Atomic file I/O and JSON helpers for the Citrix relay protocol."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically via tmp-file + rename."""
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp_path, path)


def read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, returning None if it does not exist or is unreadable.

    Uses try/except instead of exists() to avoid TOCTOU races.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (FileNotFoundError, json.JSONDecodeError):
        return None
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_transport.py -v`
Expected: 6 passed

- [ ] **Step 9: Commit**

```bash
git add src/sapwebguimcp/backend/citrix/ unittests/citrix/
git commit -m "feat(citrix): add transport layer — exceptions and atomic JSON I/O"
```

---

### Task 2: CitrixBackend — Core RPC Client

**Files:**
- Create: `src/sapwebguimcp/backend/citrix/_backend.py`
- Create: `unittests/citrix/test_citrix_backend.py`
- Modify: `src/sapwebguimcp/backend/citrix/__init__.py`

- [ ] **Step 1: Write failing tests for CitrixBackend**

```python
# unittests/citrix/test_citrix_backend.py
"""Tests for CitrixBackend — the client-side RPC proxy."""

import asyncio
import base64
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sapwebguimcp.backend.citrix._backend import CitrixBackend
from sapwebguimcp.backend.citrix._exceptions import (
    RelayDisconnectedError,
    RelayError,
)
from sapwebguimcp.backend.citrix._transport import atomic_write_json


def _make_relay_dir(tmp_path: Path) -> Path:
    relay_dir = tmp_path / "sapgui-relay-test"
    relay_dir.mkdir()
    (relay_dir / "commands").mkdir()
    (relay_dir / "responses").mkdir()
    return relay_dir


def _write_fresh_heartbeat(relay_dir: Path, status: str = "idle") -> None:
    from datetime import datetime, timezone

    atomic_write_json(
        relay_dir / "heartbeat.json",
        {
            "status": status,
            "current_command": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def test_backend_type_is_citrix(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="abc123")
    assert backend.backend_type == "citrix"


def test_call_writes_command_and_reads_response(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="tok123", poll_interval_s=0.01)
    _write_fresh_heartbeat(relay_dir)

    async def run() -> str:
        # Simulate relay writing response after a short delay
        async def fake_relay() -> None:
            await asyncio.sleep(0.05)
            atomic_write_json(
                relay_dir / "responses" / "000001.json",
                {
                    "id": "000001",
                    "token": "tok123",
                    "success": True,
                    "result": "hello",
                    "duration_ms": 10,
                },
            )

        asyncio.create_task(fake_relay())
        return await backend._call("get_page_title")

    result = asyncio.run(run())
    assert result == "hello"

    # Command file should have been written
    cmd_path = relay_dir / "commands" / "000001.json"
    assert cmd_path.exists()
    cmd = json.loads(cmd_path.read_text())
    assert cmd["method"] == "get_page_title"
    assert cmd["token"] == "tok123"


def test_call_raises_relay_error_on_failure(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="tok", poll_interval_s=0.01)
    _write_fresh_heartbeat(relay_dir)

    async def run() -> None:
        async def fake_relay() -> None:
            await asyncio.sleep(0.05)
            atomic_write_json(
                relay_dir / "responses" / "000001.json",
                {
                    "id": "000001",
                    "token": "tok",
                    "success": False,
                    "error": "ValueError: field not found",
                },
            )

        asyncio.create_task(fake_relay())
        await backend._call("fill_field", label="X", value="Y")

    with pytest.raises(RelayError, match="field not found"):
        asyncio.run(run())


def test_deserialize_bytes(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="t")
    raw = {"_type": "bytes", "data": base64.b64encode(b"PNG_DATA").decode()}
    assert backend._deserialize(raw) == b"PNG_DATA"


def test_deserialize_passthrough(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="t")
    assert backend._deserialize({"foo": "bar"}) == {"foo": "bar"}
    assert backend._deserialize(None) is None
    assert backend._deserialize(42) == 42


def test_check_heartbeat_stale_raises(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="t", heartbeat_timeout_s=5)
    # Write a heartbeat 20s in the past
    from datetime import datetime, timezone, timedelta

    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    atomic_write_json(
        relay_dir / "heartbeat.json",
        {"status": "idle", "current_command": None, "timestamp": old_ts},
    )
    with pytest.raises(RelayDisconnectedError, match="Heartbeat"):
        backend._check_heartbeat()


def test_check_heartbeat_shutdown_raises(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="t")
    from datetime import datetime, timezone

    atomic_write_json(
        relay_dir / "heartbeat.json",
        {
            "status": "shutdown",
            "current_command": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    with pytest.raises(RelayDisconnectedError, match="beendet"):
        backend._check_heartbeat()


def test_check_heartbeat_no_file_ok(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="t")
    backend._check_heartbeat()  # Should not raise


def test_check_heartbeat_disconnected_raises(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="t")
    from datetime import datetime, timezone

    atomic_write_json(
        relay_dir / "heartbeat.json",
        {
            "status": "disconnected",
            "current_command": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    with pytest.raises(RelayDisconnectedError, match="COM-Fehler"):
        backend._check_heartbeat()


def test_call_ignores_stale_token_response(tmp_path: Path) -> None:
    """Response with wrong token should be skipped, correct one accepted."""
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="correct_tok", poll_interval_s=0.01)
    _write_fresh_heartbeat(relay_dir)

    async def run() -> str:
        async def fake_relay() -> None:
            # First: write a stale response with wrong token
            await asyncio.sleep(0.03)
            atomic_write_json(
                relay_dir / "responses" / "000001.json",
                {"id": "000001", "token": "old_wrong_tok", "success": True, "result": "stale", "duration_ms": 1},
            )
            # Then: write the correct response
            await asyncio.sleep(0.05)
            atomic_write_json(
                relay_dir / "responses" / "000001.json",
                {"id": "000001", "token": "correct_tok", "success": True, "result": "fresh", "duration_ms": 1},
            )

        asyncio.create_task(fake_relay())
        return await backend._call("get_page_title")

    result = asyncio.run(run())
    assert result == "fresh"


def test_browser_only_methods_raise(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="t")
    with pytest.raises(NotImplementedError):
        backend.load_js("foo.js")
    with pytest.raises(NotImplementedError):
        asyncio.run(backend.evaluate_javascript("1+1"))
    with pytest.raises(NotImplementedError):
        asyncio.run(backend.fill_element_by_locator("[id=x]", "v"))
    with pytest.raises(NotImplementedError):
        asyncio.run(backend.click_element("#btn"))


def test_response_file_deleted_after_read(tmp_path: Path) -> None:
    relay_dir = _make_relay_dir(tmp_path)
    backend = CitrixBackend(relay_dir, token="tok", poll_interval_s=0.01)
    _write_fresh_heartbeat(relay_dir)

    async def run() -> None:
        async def fake_relay() -> None:
            await asyncio.sleep(0.05)
            atomic_write_json(
                relay_dir / "responses" / "000001.json",
                {"id": "000001", "token": "tok", "success": True, "result": None, "duration_ms": 1},
            )

        asyncio.create_task(fake_relay())
        await backend._call("wait", timeout_ms=100)

    asyncio.run(run())
    assert not (relay_dir / "responses" / "000001.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_citrix_backend.py -v`
Expected: ImportError

- [ ] **Step 3: Implement CitrixBackend**

```python
# src/sapwebguimcp/backend/citrix/_backend.py
"""CitrixBackend — client-side RPC proxy for the Citrix relay."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sapwebguimcp.backend.citrix._exceptions import (
    RelayDisconnectedError,
    RelayError,
)
from sapwebguimcp.backend.citrix._transport import atomic_write_json, read_json

logger = logging.getLogger(__name__)


class CitrixBackend:
    """Proxy: every SapUiBackend method becomes a JSON command file,
    waits for a JSON response file, and returns the result.

    **Serialization note:** Methods that return Pydantic models on the
    desktop/webgui backends will return plain dicts here (the relay
    serializes via ``model_dump()``). Tool code already accesses model
    attributes via dict-style patterns in many places. Methods returning
    ``tuple`` (e.g. ``open_new_session``) are reconstructed explicitly.
    """

    backend_type = "citrix"

    def __init__(
        self,
        relay_dir: Path,
        token: str,
        poll_interval_s: float = 0.1,
        heartbeat_timeout_s: float = 10.0,
    ) -> None:
        self._relay_dir = relay_dir
        self._token = token
        self._poll_interval_s = poll_interval_s
        self._heartbeat_timeout_s = heartbeat_timeout_s
        self._counter = 0
        # Private event loop for sync → async bridge (get_session_token).
        # Cannot use run_until_complete() because the MCP server already
        # runs an event loop. Instead we submit to a thread-loop and block.
        self._sync_loop = asyncio.new_event_loop()
        self._sync_thread = threading.Thread(target=self._sync_loop.run_forever, daemon=True)
        self._sync_thread.start()

    # -- Browser-only methods (not available via Citrix relay) --

    def load_js(self, filename: str) -> str:
        raise NotImplementedError("load_js is not available via Citrix relay")

    async def evaluate_javascript(self, script: str, arg: Any = None) -> Any:
        raise NotImplementedError("evaluate_javascript is not available via Citrix relay")

    async def fill_element_by_locator(self, locator: str, value: str, delay_ms: int = 30) -> bool:
        raise NotImplementedError("fill_element_by_locator is not available via Citrix relay")

    async def click_element(self, selector: str) -> bool:
        raise NotImplementedError("click_element is not available via Citrix relay")

    # -- Sync method --

    def get_session_token(self) -> str:
        future = asyncio.run_coroutine_threadsafe(self._call("get_session_token"), self._sync_loop)
        return future.result(timeout=60)

    # -- All async SapUiBackend methods → proxy via _call --

    async def fill_field(self, label: str, value: str) -> None:
        await self._call("fill_field", label=label, value=value)

    async def fill_main_input(self, value: str, labels: list[str]) -> bool:
        return await self._call("fill_main_input", value=value, labels=labels)

    async def fill_form(self, fields: dict[str, str]) -> Any:
        return await self._call("fill_form", fields=fields)

    async def fill_grid_cell(self, row: int, column: int | str, value: str) -> None:
        await self._call("fill_grid_cell", row=row, column=column, value=value)

    async def click_button(self, label: str) -> None:
        await self._call("click_button", label=label)

    async def click_tab(self, label: str) -> None:
        await self._call("click_tab", label=label)

    async def press_key(self, key: str) -> Any:
        return await self._call("press_key", key=key)

    async def type_text(self, text: str) -> None:
        await self._call("type_text", text=text)

    async def set_checkbox(self, label: str, checked: bool) -> None:
        await self._call("set_checkbox", label=label, checked=checked)

    async def set_radio_button(self, label: str) -> None:
        await self._call("set_radio_button", label=label)

    async def select_dropdown(self, label: str, option: str) -> Any:
        return await self._call("select_dropdown", label=label, option=option)

    async def focus_and_type(self, accessible_name: str, text: str, delay_ms: int = 0) -> bool:
        return await self._call("focus_and_type", accessible_name=accessible_name, text=text, delay_ms=delay_ms)

    async def get_status_bar(self) -> Any:
        return await self._call("get_status_bar")

    async def get_screen_info(self) -> Any:
        return await self._call("get_screen_info")

    async def get_screen_text(self, include_dropdown_options: bool = False) -> Any:
        return await self._call("get_screen_text", include_dropdown_options=include_dropdown_options)

    async def discover_fields(self) -> Any:
        return await self._call("discover_fields")

    async def get_form_fields(self, *, include_dropdown_options: bool = False) -> Any:
        return await self._call("get_form_fields", include_dropdown_options=include_dropdown_options)

    async def discover_buttons(self) -> Any:
        return await self._call("discover_buttons")

    async def get_snapshot(self) -> Any:
        return await self._call("get_snapshot")

    async def take_screenshot(self) -> bytes:
        # _call() already runs _deserialize() which decodes {"_type": "bytes", ...}
        return await self._call("take_screenshot")

    async def read_table(self, start_row: int = 1, end_row: int | None = None, max_rows: int = 100) -> Any:
        return await self._call("read_table", start_row=start_row, end_row=end_row, max_rows=max_rows)

    async def click_table_cell(self, row: int, column: int | str, action: str = "click") -> Any:
        return await self._call("click_table_cell", row=row, column=column, action=action)

    async def get_dropdown_options(self, label: str) -> list[str]:
        return await self._call("get_dropdown_options", label=label)

    async def get_page_title(self) -> str:
        return await self._call("get_page_title")

    async def login(
        self,
        url: str,
        username: str,
        password: str,
        client: str,
        language: str,
        session_id: str | None = None,
        connection_name: str | None = None,
    ) -> Any:
        return await self._call(
            "login",
            url=url,
            username=username,
            password=password,
            client=client,
            language=language,
            session_id=session_id,
            connection_name=connection_name,
        )

    async def list_connections(self) -> list[Any]:
        return await self._call("list_connections")

    async def discover_clients(self, connection_name: str) -> dict[str, Any]:
        return await self._call("discover_clients", connection_name=connection_name)

    async def enter_transaction(self, tcode: str) -> Any:
        return await self._call("enter_transaction", tcode=tcode)

    async def get_session_status(self) -> Any:
        return await self._call("get_session_status")

    async def wait_for_ready(self, timeout_ms: int = 15000) -> None:
        await self._call("wait_for_ready", timeout_ms=timeout_ms)

    async def bring_to_front(self) -> None:
        await self._call("bring_to_front")

    async def wait_for_sap_ready(self, timeout_ms: int = 5000) -> None:
        await self._call("wait_for_sap_ready", timeout_ms=timeout_ms)

    async def wait(self, timeout_ms: int = 200) -> None:
        await self._call("wait", timeout_ms=timeout_ms)

    async def start_keepalive(self, interval_seconds: int = 300) -> None:
        await self._call("start_keepalive", interval_seconds=interval_seconds)

    async def stop_keepalive(self) -> bool:
        return await self._call("stop_keepalive")

    async def open_new_session(self, tcode: str) -> tuple[str | None, int, str | None]:
        result = await self._call("open_new_session", tcode=tcode)
        # JSON serializes tuples as lists — reconstruct tuple for callers
        return tuple(result) if isinstance(result, list) else result

    async def is_page_closed(self) -> bool:
        return await self._call("is_page_closed")

    async def close_page(self) -> None:
        await self._call("close_page")

    async def list_sessions(self) -> list[Any]:
        return await self._call("list_sessions")

    async def close_session(self, session_id: str) -> bool:
        return await self._call("close_session", session_id=session_id)

    async def bind_session(self, session_id: str, agent_id: str) -> str | None:
        return await self._call("bind_session", session_id=session_id, agent_id=agent_id)

    async def release_session(self, session_id: str) -> str | None:
        return await self._call("release_session", session_id=session_id)

    async def has_session(self, session_id: str) -> bool:
        return await self._call("has_session", session_id=session_id)

    async def read_editor_source(self) -> str | None:
        return await self._call("read_editor_source")

    async def replace_editor_source(self, code: str) -> bool:
        return await self._call("replace_editor_source", code=code)

    async def check_and_activate(self) -> Any:
        return await self._call("check_and_activate")

    async def dismiss_language_dialog(self) -> None:
        await self._call("dismiss_language_dialog")

    async def check_popup(self) -> Any:
        return await self._call("check_popup")

    async def dismiss_popup(self, button_label: str | None = None, use_close_button: bool = False) -> Any:
        return await self._call("dismiss_popup", button_label=button_label, use_close_button=use_close_button)

    # -- Core RPC machinery --

    async def _call(self, method: str, **args: Any) -> Any:
        """Write command, poll for response, return result."""
        self._counter += 1
        cmd_id = f"{self._counter:06d}"

        cmd = {
            "id": cmd_id,
            "token": self._token,
            "method": method,
            "args": args,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        cmd_path = self._relay_dir / "commands" / f"{cmd_id}.json"
        atomic_write_json(cmd_path, cmd)
        logger.debug("Command %s: %s(%s)", cmd_id, method, list(args.keys()))

        while True:
            resp_path = self._relay_dir / "responses" / f"{cmd_id}.json"
            if resp_path.exists():
                resp = json.loads(resp_path.read_text(encoding="utf-8"))
                resp_path.unlink()
                # Ignore stale responses from a previous relay (wrong token)
                if resp.get("token") != self._token:
                    logger.debug("Ignoring stale response %s (token mismatch)", cmd_id)
                    continue
                if not resp["success"]:
                    raise RelayError(resp["error"])
                return self._deserialize(resp.get("result"))
            self._check_heartbeat()
            await asyncio.sleep(self._poll_interval_s)

    def _deserialize(self, result: Any) -> Any:
        """Deserialize special types from JSON response."""
        if isinstance(result, dict) and result.get("_type") == "bytes":
            return base64.b64decode(result["data"])
        return result

    def _check_heartbeat(self) -> None:
        """Verify relay is alive via heartbeat file."""
        hb = read_json(self._relay_dir / "heartbeat.json")
        if hb is None:
            return  # No heartbeat yet — relay still starting
        if hb.get("status") == "shutdown":
            raise RelayDisconnectedError("Relay wurde beendet")
        if hb.get("status") == "disconnected":
            raise RelayDisconnectedError("SAP-Session in Citrix getrennt (COM-Fehler)")
        ts = datetime.fromisoformat(hb["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > self._heartbeat_timeout_s:
            raise RelayDisconnectedError(f"Heartbeat ist {age:.0f}s alt")
```

- [ ] **Step 4: Update `__init__.py` to re-export**

```python
# src/sapwebguimcp/backend/citrix/__init__.py
"""Citrix relay backend — file-based RPC proxy to DesktopBackend in a Citrix session."""

from sapwebguimcp.backend.citrix._backend import CitrixBackend

__all__ = ["CitrixBackend"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_citrix_backend.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add src/sapwebguimcp/backend/citrix/ unittests/citrix/test_citrix_backend.py
git commit -m "feat(citrix): add CitrixBackend — client-side RPC proxy"
```

---

### Task 3: RelayAgent — Server-Side Command Processor

**Files:**
- Create: `src/sapwebguimcp/backend/citrix/_relay_agent.py`
- Create: `unittests/citrix/test_relay_agent.py`

- [ ] **Step 1: Write failing tests for RelayAgent**

```python
# unittests/citrix/test_relay_agent.py
"""Tests for RelayAgent — the server-side command processor."""

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapwebguimcp.backend.citrix._relay_agent import RelayAgent
from sapwebguimcp.backend.citrix._transport import atomic_write_json, read_json


def _make_relay_dir(tmp_path: Path, token: str = "secret") -> tuple[Path, RelayAgent]:
    """Create a relay dir and agent with mocked DesktopBackend."""
    relay_dir = tmp_path / "sapgui-relay-test"
    relay_dir.mkdir()
    (relay_dir / "commands").mkdir()
    (relay_dir / "responses").mkdir()

    agent = RelayAgent.__new__(RelayAgent)
    agent._relay_dir = relay_dir
    agent._token = token
    agent._backend = MagicMock()
    agent._loop = None  # Not needed for unit tests
    agent._current_command = None
    agent._disconnected = False
    return relay_dir, agent


def test_serialize_none() -> None:
    _, agent = _make_relay_dir(Path("/tmp/fake"))
    assert agent._serialize(None) is None


def test_serialize_bytes() -> None:
    _, agent = _make_relay_dir(Path("/tmp/fake"))
    result = agent._serialize(b"PNG_DATA")
    assert result == {"_type": "bytes", "data": base64.b64encode(b"PNG_DATA").decode()}


def test_serialize_pydantic_model() -> None:
    _, agent = _make_relay_dir(Path("/tmp/fake"))
    mock_model = MagicMock()
    mock_model.model_dump.return_value = {"status": "ok"}
    assert agent._serialize(mock_model) == {"status": "ok"}


def test_serialize_passthrough() -> None:
    _, agent = _make_relay_dir(Path("/tmp/fake"))
    assert agent._serialize("hello") == "hello"
    assert agent._serialize(42) == 42


def test_serialize_list_of_models() -> None:
    _, agent = _make_relay_dir(Path("/tmp/fake"))
    m1 = MagicMock()
    m1.model_dump.return_value = {"id": "s1"}
    m2 = MagicMock()
    m2.model_dump.return_value = {"id": "s2"}
    result = agent._serialize([m1, m2])
    assert result == [{"id": "s1"}, {"id": "s2"}]


def test_serialize_tuple() -> None:
    _, agent = _make_relay_dir(Path("/tmp/fake"))
    # open_new_session returns tuple(str|None, int, str|None)
    result = agent._serialize(("s2", 2, "SAP Easy Access"))
    assert result == ["s2", 2, "SAP Easy Access"]


def test_execute_success(tmp_path: Path) -> None:
    relay_dir, agent = _make_relay_dir(tmp_path, token="tok")
    agent._backend.get_page_title = AsyncMock(return_value="SAP Easy Access")

    import asyncio

    loop = asyncio.new_event_loop()
    agent._loop = loop

    cmd = {"id": "000001", "method": "get_page_title", "args": {}}
    result = agent._execute(cmd)
    assert result["success"] is True
    assert result["result"] == "SAP Easy Access"
    assert result["id"] == "000001"

    loop.close()


def test_execute_error(tmp_path: Path) -> None:
    relay_dir, agent = _make_relay_dir(tmp_path, token="tok")
    agent._backend.fill_field = AsyncMock(side_effect=ValueError("not found"))

    import asyncio

    loop = asyncio.new_event_loop()
    agent._loop = loop

    cmd = {"id": "000002", "method": "fill_field", "args": {"label": "X", "value": "Y"}}
    result = agent._execute(cmd)
    assert result["success"] is False
    assert "ValueError: not found" in result["error"]

    loop.close()


def test_token_mismatch_ignored(tmp_path: Path) -> None:
    relay_dir, agent = _make_relay_dir(tmp_path, token="correct_token")
    cmd = {"id": "000001", "token": "wrong_token", "method": "noop", "args": {}}
    # Verify that validate_token returns False for wrong token
    assert agent._validate_token(cmd) is False
    assert agent._validate_token({"token": "correct_token"}) is True


def test_execute_sets_disconnected_on_com_error(tmp_path: Path) -> None:
    """COM errors should set _disconnected flag for heartbeat."""
    relay_dir, agent = _make_relay_dir(tmp_path, token="tok")
    # Simulate a COM error (pywintypes.com_error)
    com_error = type("com_error", (Exception,), {})
    agent._backend.fill_field = AsyncMock(side_effect=com_error("RPC server unavailable"))

    import asyncio

    loop = asyncio.new_event_loop()
    agent._loop = loop

    assert agent._disconnected is False
    cmd = {"id": "000003", "method": "fill_field", "args": {"label": "X", "value": "Y"}}
    result = agent._execute(cmd)
    assert result["success"] is False
    assert agent._disconnected is True

    loop.close()


def test_execute_clears_disconnected_on_success(tmp_path: Path) -> None:
    """Successful execution should clear _disconnected flag."""
    relay_dir, agent = _make_relay_dir(tmp_path, token="tok")
    agent._disconnected = True
    agent._backend.get_page_title = AsyncMock(return_value="SAP")

    import asyncio

    loop = asyncio.new_event_loop()
    agent._loop = loop

    cmd = {"id": "000004", "method": "get_page_title", "args": {}}
    result = agent._execute(cmd)
    assert result["success"] is True
    assert agent._disconnected is False

    loop.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_relay_agent.py -v`
Expected: ImportError

- [ ] **Step 3: Implement RelayAgent**

```python
# src/sapwebguimcp/backend/citrix/_relay_agent.py
"""RelayAgent — standalone server-side command processor for Citrix sessions.

Watches a shared directory for JSON command files, executes them via
DesktopBackend (COM Scripting), and writes JSON response files.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sapwebguimcp.backend.citrix._exceptions import RelayError
from sapwebguimcp.backend.citrix._transport import atomic_write_json

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = 1
_HEARTBEAT_INTERVAL_S = 2.0
_EXECUTE_TIMEOUT_S = 300  # 5 min safety timeout


class RelayAgent:
    """Watch-loop: read commands → execute via DesktopBackend → write responses."""

    def __init__(self, relay_dir_base: Path, poll_interval_s: float = 0.05) -> None:
        suffix = secrets.token_hex(4)
        self._relay_dir = relay_dir_base / f"sapgui-relay-{suffix}"
        self._relay_dir.mkdir(parents=True)
        self._set_ntfs_acls(self._relay_dir)
        (self._relay_dir / "commands").mkdir()
        (self._relay_dir / "responses").mkdir()

        self._poll_interval_s = poll_interval_s
        self._token = secrets.token_hex(32)
        self._shutdown = False
        self._current_command: str | None = None  # Tracks busy state for heartbeat
        self._disconnected = False  # Set on COM/session errors (heartbeat → "disconnected")

        # Persistent async event loop in a dedicated thread for DesktopBackend
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()

        # DesktopBackend will be initialized in run() after handshake
        self._backend: Any = None

    @property
    def relay_dir(self) -> Path:
        return self._relay_dir

    def _set_ntfs_acls(self, path: Path) -> None:
        """Set restrictive NTFS ACLs: only current user has access."""
        if sys.platform != "win32":
            return
        try:
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{_get_username()}:(OI)(CI)F"],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Could not set NTFS ACLs on %s — continuing without restriction", path)

    def _write_handshake(self) -> None:
        atomic_write_json(
            self._relay_dir / "handshake.json",
            {
                "token": self._token,
                "relay_version": "1.0.0",
                "protocol_version": _PROTOCOL_VERSION,
                "backend_ready": True,
                "pid": _get_pid(),
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _update_heartbeat(self, status: str, current_command: str | None) -> None:
        atomic_write_json(
            self._relay_dir / "heartbeat.json",
            {
                "status": status,
                "current_command": current_command,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _start_heartbeat_thread(self) -> None:
        def heartbeat_loop() -> None:
            while not self._shutdown:
                if self._disconnected:
                    status = "disconnected"
                    cmd_id = None
                else:
                    cmd_id = self._current_command
                    status = "busy" if cmd_id else "idle"
                self._update_heartbeat(status, cmd_id)
                time.sleep(_HEARTBEAT_INTERVAL_S)

        t = threading.Thread(target=heartbeat_loop, daemon=True)
        t.start()

    def _validate_token(self, cmd: dict[str, Any]) -> bool:
        return cmd.get("token") == self._token

    # COM error types that indicate a disconnected SAP session
    _COM_ERROR_NAMES = ("com_error", "pywintypes.com_error", "COMError", "DisconnectedError")

    def _execute(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Execute a single command via DesktopBackend and return response dict."""
        method_name = cmd["method"]
        method = getattr(self._backend, method_name)
        try:
            future = asyncio.run_coroutine_threadsafe(method(**cmd["args"]), self._loop)
            result = future.result(timeout=_EXECUTE_TIMEOUT_S)
            # Successful execution clears any previous disconnected state
            self._disconnected = False
            return {
                "id": cmd["id"],
                "token": self._token,
                "success": True,
                "result": self._serialize(result),
            }
        except Exception as e:
            # Detect COM/session errors → set heartbeat to "disconnected"
            error_type = type(e).__name__
            if error_type in self._COM_ERROR_NAMES or "com_error" in str(type(e)).lower():
                self._disconnected = True
                logger.error("COM error detected, heartbeat → disconnected: %s", e)
            return {
                "id": cmd["id"],
                "token": self._token,
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }

    def _serialize(self, result: Any) -> Any:
        """Serialize Python objects for JSON transport.

        Handles: None, bytes, Pydantic models, lists (recursive), tuples (→ list),
        and passthrough for JSON-native types.
        """
        if result is None:
            return None
        if isinstance(result, bytes):
            return {"_type": "bytes", "data": base64.b64encode(result).decode()}
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, (list, tuple)):
            return [self._serialize(item) for item in result]
        return result

    def run(self) -> None:
        """Main loop: initialize backend, write handshake, process commands."""
        # Initialize DesktopBackend in the async event loop
        from sapwebguimcp.backend.desktop import DesktopBackend
        from sapwebguimcp.backend.desktop._com_thread import ComThread

        com_thread = ComThread()
        self._backend = DesktopBackend(com_thread=com_thread)

        self._write_handshake()
        self._start_heartbeat_thread()

        print(f"Relay directory: {self._relay_dir}")
        print("Relay ready. Waiting for commands...")
        logger.info("Relay started at %s", self._relay_dir)

        try:
            while not self._shutdown:
                cmd_files = sorted(
                    self._relay_dir.glob("commands/*.json"),
                    key=lambda f: f.name,
                )
                for cmd_file in cmd_files:
                    if cmd_file.suffix == ".tmp":
                        continue
                    try:
                        cmd = json.loads(cmd_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        logger.warning("Skipping unreadable command: %s", cmd_file.name)
                        cmd_file.unlink(missing_ok=True)
                        continue

                    if not self._validate_token(cmd):
                        logger.debug("Ignoring command %s with invalid token", cmd.get("id"))
                        cmd_file.unlink(missing_ok=True)
                        continue

                    self._current_command = cmd["id"]
                    logger.info("Executing %s: %s", cmd["id"], cmd["method"])

                    start = time.monotonic()
                    result = self._execute(cmd)
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    result["duration_ms"] = elapsed_ms

                    resp_path = self._relay_dir / "responses" / f"{cmd['id']}.json"
                    atomic_write_json(resp_path, result)
                    cmd_file.unlink(missing_ok=True)

                    self._current_command = None
                    logger.info("Done %s in %dms (success=%s)", cmd["id"], elapsed_ms, result["success"])

                time.sleep(self._poll_interval_s)
        except KeyboardInterrupt:
            logger.info("Relay shutting down...")
        finally:
            self._shutdown = True
            self._update_heartbeat("shutdown", None)
            com_thread.shutdown()
            self._loop.call_soon_threadsafe(self._loop.stop)


def _get_username() -> str:
    import os

    return os.environ.get("USERNAME", os.environ.get("USER", "UNKNOWN"))


def _get_pid() -> int:
    import os

    return os.getpid()


def main() -> None:
    """CLI entry point for the relay agent."""
    import argparse

    parser = argparse.ArgumentParser(description="SAP GUI Relay Agent for Citrix sessions")
    parser.add_argument(
        "--relay-dir-base",
        type=Path,
        default=Path(r"\\Client\C$"),
        help="Base directory for the relay folder (default: \\\\Client\\C$)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    agent = RelayAgent(relay_dir_base=args.relay_dir_base)

    # Add file handler for relay.log inside the relay directory (per design spec).
    # Commands are logged without token, responses without result details.
    file_handler = logging.FileHandler(agent.relay_dir / "relay.log", encoding="utf-8")
    file_handler.setLevel(getattr(logging, args.log_level))
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)

    agent.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_relay_agent.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/sapwebguimcp/backend/citrix/_relay_agent.py unittests/citrix/test_relay_agent.py
git commit -m "feat(citrix): add RelayAgent — server-side command processor"
```

---

### Task 4: Config & BackendManager Integration

**Files:**
- Modify: `src/sapwebguimcp/models/config.py`
- Modify: `src/sapwebguimcp/backend/manager.py`
- Modify: `src/sapwebguimcp/backend/protocol.py` (docstring only)
- Create: `unittests/citrix/test_manager_citrix.py`

- [ ] **Step 1: Write failing tests for config and manager**

```python
# unittests/citrix/test_manager_citrix.py
"""Tests for BackendManager citrix integration."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from sapwebguimcp.backend.manager import BackendManager


@pytest.mark.skipif(sys.platform != "win32", reason="citrix backend requires Windows")
def test_backend_type_accepts_citrix() -> None:
    """BackendManager should accept 'citrix' as a valid type."""
    manager = BackendManager(backend_type="citrix")
    assert manager.backend_type == "citrix"


@pytest.mark.skipif(sys.platform == "win32", reason="only fails on non-Windows")
def test_backend_type_citrix_rejected_on_non_windows() -> None:
    """BackendManager should reject 'citrix' on non-Windows platforms."""
    with pytest.raises(RuntimeError, match="requires Windows"):
        BackendManager(backend_type="citrix")


def test_config_accepts_citrix_backend_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """SapWebGuiSettings should accept 'citrix' as backend_type."""
    from sapwebguimcp.models.config import SapWebGuiSettings

    # Reset singleton
    import sapwebguimcp.models.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "_settings", None)
    monkeypatch.setenv("BACKEND_TYPE", "citrix")
    monkeypatch.setenv("CITRIX_RELAY_DIR", r"C:\sapgui-relay-test")

    settings = SapWebGuiSettings()
    assert settings.backend_type == "citrix"
    assert settings.citrix_relay_dir == r"C:\sapgui-relay-test"
    assert settings.citrix_poll_interval_ms == 100
    assert settings.citrix_heartbeat_timeout_s == 10


# -- Tests for _read_handshake_token --


def test_read_handshake_token_success(tmp_path: Path) -> None:
    """Should read token from handshake.json immediately."""
    import asyncio
    from sapwebguimcp.backend.citrix._transport import atomic_write_json

    relay_dir = tmp_path / "relay"
    relay_dir.mkdir()
    atomic_write_json(
        relay_dir / "handshake.json",
        {"token": "secret123", "protocol_version": 1, "relay_version": "1.0.0",
         "backend_ready": True, "pid": 1, "started_at": "2026-01-01T00:00:00Z"},
    )
    token = asyncio.run(BackendManager._read_handshake_token(relay_dir))
    assert token == "secret123"


def test_read_handshake_token_protocol_mismatch(tmp_path: Path) -> None:
    """Should raise RelayProtocolError on version mismatch."""
    import asyncio
    from sapwebguimcp.backend.citrix._exceptions import RelayProtocolError
    from sapwebguimcp.backend.citrix._transport import atomic_write_json

    relay_dir = tmp_path / "relay"
    relay_dir.mkdir()
    atomic_write_json(
        relay_dir / "handshake.json",
        {"token": "t", "protocol_version": 99, "relay_version": "1.0.0",
         "backend_ready": True, "pid": 1, "started_at": "2026-01-01T00:00:00Z"},
    )
    with pytest.raises(RelayProtocolError, match="version mismatch"):
        asyncio.run(BackendManager._read_handshake_token(relay_dir))


def test_read_handshake_token_timeout(tmp_path: Path) -> None:
    """Should raise FileNotFoundError after timeout when no handshake.json."""
    import asyncio
    from unittest.mock import patch

    relay_dir = tmp_path / "relay"
    relay_dir.mkdir()
    # Patch asyncio.sleep to skip waiting (otherwise 30s timeout)
    with patch("sapwebguimcp.backend.manager.asyncio.sleep", new_callable=lambda: asyncio.coroutine(lambda *a: None).__class__):
        # Simpler: just mock sleep to return immediately
        async def fast_sleep(s: float) -> None:
            pass

        with patch("asyncio.sleep", side_effect=fast_sleep):
            with pytest.raises(FileNotFoundError, match="handshake.json"):
                asyncio.run(BackendManager._read_handshake_token(relay_dir))


def test_clear_stale_responses(tmp_path: Path) -> None:
    """Should delete all .json files in responses/ on startup."""
    relay_dir = tmp_path / "relay"
    (relay_dir / "responses").mkdir(parents=True)
    (relay_dir / "responses" / "000001.json").write_text("{}")
    (relay_dir / "responses" / "000002.json").write_text("{}")
    BackendManager._clear_stale_responses(relay_dir)
    assert list((relay_dir / "responses").iterdir()) == []


def test_clear_stale_responses_no_dir(tmp_path: Path) -> None:
    """Should be a no-op when responses/ doesn't exist."""
    relay_dir = tmp_path / "relay"
    relay_dir.mkdir()
    BackendManager._clear_stale_responses(relay_dir)  # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_manager_citrix.py -v`
Expected: validation error / ValueError — "citrix" not in BackendType

- [ ] **Step 3: Update config.py — add citrix to BackendType and new settings**

In `src/sapwebguimcp/models/config.py`, change:

```python
# Line 27: extend BackendType
BackendType = Literal["webgui", "desktop", "citrix"]
```

Add new fields to `SapWebGuiSettings` class (after `com_min_interval_ms`):

```python
    # Citrix Relay Configuration
    citrix_relay_dir: str = Field(
        default=r"C:\sapgui-relay",
        description="Path to the Citrix relay shared directory",
        json_schema_extra={"env": "CITRIX_RELAY_DIR"},
    )
    citrix_poll_interval_ms: int = Field(
        default=100,
        ge=10,
        le=5000,
        description="Poll interval in ms for checking relay responses",
        json_schema_extra={"env": "CITRIX_POLL_INTERVAL_MS"},
    )
    citrix_heartbeat_timeout_s: int = Field(
        default=10,
        ge=2,
        le=60,
        description="Seconds before a stale heartbeat triggers disconnect error",
        json_schema_extra={"env": "CITRIX_HEARTBEAT_TIMEOUT_S"},
    )
```

- [ ] **Step 4: Update manager.py — add citrix branch**

In `src/sapwebguimcp/backend/manager.py`, add import (guarded like desktop):

```python
if sys.platform == "win32" or TYPE_CHECKING:
    from sapwebguimcp.backend.citrix import CitrixBackend
    from sapwebguimcp.backend.desktop import DesktopBackend, _current_session_id
    from sapwebguimcp.backend.desktop._com_thread import ComThread
```

Add validation in `__init__`:

```python
if backend_type == "citrix" and sys.platform != "win32":
    raise RuntimeError(
        "BACKEND_TYPE=citrix requires Windows. "
        "On macOS/Linux, use BACKEND_TYPE=webgui (the default) instead."
    )
```

Add citrix branch in `get_or_create()` before the final `raise ValueError`:

```python
if self.backend_type == "citrix":
    cached = self._backends.get("citrix")
    if cached is not None:
        return cached
    settings = get_settings()
    relay_dir = Path(settings.citrix_relay_dir)
    token = await self._read_handshake_token(relay_dir)
    # Clear stale responses from a previous client run (design: Cleanup-Strategie)
    self._clear_stale_responses(relay_dir)
    backend = CitrixBackend(
        relay_dir,
        token,
        poll_interval_s=settings.citrix_poll_interval_ms / 1000.0,
        heartbeat_timeout_s=float(settings.citrix_heartbeat_timeout_s),
    )
    self._backends["citrix"] = backend
    return backend
```

Add helper method `_read_handshake_token` (async to avoid blocking the event loop):

```python
@staticmethod
async def _read_handshake_token(relay_dir: Path) -> str:
    """Read token from handshake.json, waiting up to 30s for relay startup.

    Async to avoid blocking the MCP server event loop during the wait.
    """
    import asyncio
    from sapwebguimcp.backend.citrix._exceptions import RelayProtocolError
    from sapwebguimcp.backend.citrix._transport import read_json

    handshake_path = relay_dir / "handshake.json"
    for _ in range(60):  # 30s at 0.5s intervals
        hs = read_json(handshake_path)
        if hs is not None:
            if hs.get("protocol_version") != 1:
                raise RelayProtocolError(
                    f"Protocol version mismatch: expected 1, got {hs.get('protocol_version')}. "
                    "Update your relay agent."
                )
            return hs["token"]
        await asyncio.sleep(0.5)
    raise FileNotFoundError(
        f"No handshake.json found at {handshake_path} after 30s. "
        "Is the relay agent running?"
    )
```

Add citrix branch in `close()`:

```python
elif self.backend_type == "citrix":
    pass  # CitrixBackend has no resources to release; relay manages itself
```

Add helper method `_clear_stale_responses` (per design Cleanup-Strategie):

```python
@staticmethod
def _clear_stale_responses(relay_dir: Path) -> None:
    """Remove leftover response files from a previous client run."""
    responses_dir = relay_dir / "responses"
    if not responses_dir.is_dir():
        return
    for f in responses_dir.glob("*.json"):
        f.unlink(missing_ok=True)
```

- [ ] **Step 5: Update protocol.py docstring**

In `src/sapwebguimcp/backend/protocol.py`, line 187, change:

```python
    @property
    def backend_type(self) -> str:
        """Return backend identifier: ``'desktop'``, ``'webgui'``, or ``'citrix'``."""
        return ""  # pragma: no cover
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_manager_citrix.py -v`
Expected: all passed

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_backend_manager.py unittests/desktop/test_manager_desktop.py -v`
Expected: all still passing (no regression)

- [ ] **Step 7: Commit**

```bash
git add src/sapwebguimcp/models/config.py src/sapwebguimcp/backend/manager.py src/sapwebguimcp/backend/protocol.py unittests/citrix/test_manager_citrix.py
git commit -m "feat(citrix): integrate CitrixBackend into config and BackendManager"
```

---

### Task 5: Update `_is_desktop_backend` → `_is_com_backend`

**Files:**
- Modify: `src/sapwebguimcp/tools/_backend_utils.py`
- Create: `unittests/test_backend_utils.py`
- Modify: 17 tool files that import `_is_desktop_backend`

- [ ] **Step 1: Write failing tests**

```python
# unittests/test_backend_utils.py
"""Tests for backend detection utilities."""

from unittest.mock import MagicMock

from sapwebguimcp.tools._backend_utils import _is_com_backend


def test_is_com_backend_desktop() -> None:
    backend = MagicMock()
    backend.backend_type = "desktop"
    assert _is_com_backend(backend) is True


def test_is_com_backend_citrix() -> None:
    backend = MagicMock()
    backend.backend_type = "citrix"
    assert _is_com_backend(backend) is True


def test_is_com_backend_webgui() -> None:
    backend = MagicMock()
    backend.backend_type = "webgui"
    assert _is_com_backend(backend) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_backend_utils.py -v`
Expected: ImportError — `_is_com_backend` not found

- [ ] **Step 3: Update `_backend_utils.py`**

Replace entire file content:

```python
"""Shared backend detection utilities for transaction tools."""

from sapwebguimcp.backend.protocol import SapUiBackend


def _is_com_backend(backend: SapUiBackend) -> bool:
    """Check if we're using a COM-based backend (desktop or citrix).

    Both desktop and citrix backends use SAP GUI Scripting (COM) under the
    hood. Use this to branch on desktop-style behavior in tools.
    """
    return backend.backend_type in ("desktop", "citrix")


# Backwards compatibility alias
_is_desktop_backend = _is_com_backend
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_backend_utils.py -v`
Expected: 3 passed

- [ ] **Step 5: Rename all imports in tool files**

In each of these 17 files, replace `_is_desktop_backend` with `_is_com_backend` in both the import and all call sites:

Files to update (all under `src/sapwebguimcp/tools/`):
1. `sap_tools.py`
2. `com_tools.py`
3. `se09_tools.py`
4. `se11_tools.py`
5. `se16_tools.py`
6. `se24_tools.py`
7. `se24_edit_tools.py`
8. `se37_tools.py`
9. `se38_edit_tools.py`
10. `se93_tools.py`
11. `sm30_tools.py`
12. `sm37_tools.py`
13. `st22_tools.py`
14. `slg1_tools.py`
15. `spro_tools.py`
16. `abapgit_tools.py`
17. `quick_report_tools.py`

In each file, change:
```python
from sapwebguimcp.tools._backend_utils import _is_desktop_backend
```
to:
```python
from sapwebguimcp.tools._backend_utils import _is_com_backend
```

And change every call of `_is_desktop_backend(backend)` to `_is_com_backend(backend)`.

**Exception — `com_tools.py`:** The two checks in `com_tools.py` (lines 239, 329) gate COM-only tools. These should ALSO return True for citrix, which `_is_com_backend` already handles correctly. The error messages reference "desktop backend" — update these to "COM-based backend (desktop/citrix)":

```python
# Line ~240-241 in com_tools.py:
"sap_com_snapshot is only available on COM-based backends (desktop/citrix). "
"Use browser_snapshot for WebGUI."

# Line ~330-331:
"sap_com_evaluate is only available on COM-based backends (desktop/citrix). "
"Use browser_evaluate for WebGUI."
```

**Exception — `quick_report_tools.py`:** The check `if _is_desktop_backend(backend)` rejects desktop AND should reject citrix. Since citrix is COM-based, `_is_com_backend` correctly returns True, so this tool will also reject citrix. This is correct behavior per the design (quick_report is WebGUI-only).

- [ ] **Step 5b: Fix direct `backend_type == "desktop"` string comparisons**

`sap_tools.py` has two direct `get_settings().backend_type == "desktop"` checks (lines ~885, ~892) that bypass `_is_com_backend`. These must also match citrix, otherwise citrix would fall through to WebGUI-only CSS-selector code.

In `src/sapwebguimcp/tools/sap_tools.py`, change both occurrences:

```python
# Before (line ~885 and ~892):
if get_settings().backend_type == "desktop":
    return FieldLookupResult.failure(
        "sap_lookup_fields returns WebGUI CSS selectors which don't work on Desktop. "

# After:
if get_settings().backend_type in ("desktop", "citrix"):
    return FieldLookupResult.failure(
        "sap_lookup_fields returns WebGUI CSS selectors which don't work on Desktop/Citrix. "
```

**Important:** Re-run `grep -rn 'backend_type == .desktop' src/sapwebguimcp/tools/` at execution time to catch any additional direct comparisons that may have been added since plan creation.

Also check `sap_login_impl.py` line 37: `settings.backend_type == "webgui"` — this is correct as-is. Citrix is not "webgui", so the URL check is correctly skipped (citrix uses `SAP_CONNECTION_NAME` like desktop).

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `cd sapwebgui.mcp && python -m pytest unittests/ -v --ignore=unittests/desktop -x`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add src/sapwebguimcp/tools/_backend_utils.py src/sapwebguimcp/tools/*.py unittests/test_backend_utils.py
git commit -m "refactor: rename _is_desktop_backend → _is_com_backend for citrix support"
```

---

### Task 6: Relay Entry Point & Packaging Skeleton

**Files:**
- Create: `relay/relay_agent.py`
- Create: `relay/relay.spec` (placeholder)

- [ ] **Step 1: Create relay entry point**

```python
# relay/relay_agent.py
"""Entry point for the Citrix Relay Agent standalone executable.

Build with: PyInstaller --onefile relay_agent.py
Run with:   relay.exe --relay-dir-base \\Client\C$\
"""

from sapwebguimcp.backend.citrix._relay_agent import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create PyInstaller spec placeholder**

```python
# relay/relay.spec
# PyInstaller spec for Citrix Relay Agent
# Build: pyinstaller relay.spec
#
# NOTE: This is a Phase 2 deliverable. The spec needs to be validated
# with the actual DesktopBackend dependencies (sapsucker, pywin32, etc.)
# on a Windows machine with SAP GUI installed.
#
# Usage:
#   pyinstaller --onefile relay/relay_agent.py --name relay
```

- [ ] **Step 3: Commit**

```bash
git add relay/
git commit -m "feat(citrix): add relay entry point and packaging skeleton"
```

---

### Task 7: End-to-End Integration Test (Loopback)

**Files:**
- Create: `unittests/citrix/test_integration_loopback.py`

This test verifies the full CitrixBackend → file → RelayAgent → file → CitrixBackend loop using a mock DesktopBackend (no actual SAP/COM needed).

- [ ] **Step 1: Write integration test**

```python
# unittests/citrix/test_integration_loopback.py
"""End-to-end loopback test: CitrixBackend ↔ RelayAgent via filesystem."""

import asyncio
import base64
import json
import secrets
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from sapwebguimcp.backend.citrix._backend import CitrixBackend
from sapwebguimcp.backend.citrix._relay_agent import RelayAgent
from sapwebguimcp.backend.citrix._transport import atomic_write_json, read_json


def _create_mock_relay(tmp_path: Path) -> tuple[Path, str, threading.Event]:
    """Set up relay dir, handshake, and start a minimal relay loop in a thread."""
    relay_dir = tmp_path / "sapgui-relay-loopback"
    relay_dir.mkdir()
    (relay_dir / "commands").mkdir()
    (relay_dir / "responses").mkdir()

    token = secrets.token_hex(16)

    # Write handshake
    atomic_write_json(
        relay_dir / "handshake.json",
        {"token": token, "relay_version": "1.0.0", "protocol_version": 1, "backend_ready": True, "pid": 0, "started_at": "2026-01-01T00:00:00Z"},
    )

    # Mock backend
    mock_backend = MagicMock()
    mock_backend.get_page_title = AsyncMock(return_value="SAP Easy Access")
    mock_backend.take_screenshot = AsyncMock(return_value=b"FAKE_PNG")
    mock_backend.fill_field = AsyncMock(return_value=None)
    mock_backend.get_session_status = AsyncMock(
        return_value=MagicMock(model_dump=MagicMock(return_value={"logged_in": True}))
    )
    mock_backend.click_button = AsyncMock(side_effect=ValueError("Button 'Nope' not found"))

    # Create relay agent (bypass __init__)
    agent = RelayAgent.__new__(RelayAgent)
    agent._relay_dir = relay_dir
    agent._token = token
    agent._backend = mock_backend
    agent._poll_interval_s = 0.02
    agent._shutdown = False
    agent._current_command = None
    agent._disconnected = False
    agent._loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=agent._loop.run_forever, daemon=True)
    loop_thread.start()

    stop_event = threading.Event()

    def relay_loop() -> None:
        while not stop_event.is_set():
            # Write heartbeat
            from datetime import datetime, timezone

            atomic_write_json(
                relay_dir / "heartbeat.json",
                {"status": "idle", "current_command": None, "timestamp": datetime.now(timezone.utc).isoformat()},
            )
            for cmd_file in sorted(relay_dir.glob("commands/*.json"), key=lambda f: f.name):
                if cmd_file.name.endswith(".tmp"):
                    continue
                cmd = json.loads(cmd_file.read_text())
                if cmd.get("token") != token:
                    cmd_file.unlink()
                    continue
                result = agent._execute(cmd)
                result["duration_ms"] = 1
                resp_path = relay_dir / "responses" / f"{cmd['id']}.json"
                atomic_write_json(resp_path, result)
                cmd_file.unlink()
            time.sleep(0.02)
        agent._loop.call_soon_threadsafe(agent._loop.stop)

    relay_thread = threading.Thread(target=relay_loop, daemon=True)
    relay_thread.start()

    return relay_dir, token, stop_event


def test_loopback_get_page_title(tmp_path: Path) -> None:
    relay_dir, token, stop = _create_mock_relay(tmp_path)
    try:
        backend = CitrixBackend(relay_dir, token, poll_interval_s=0.02)
        result = asyncio.run(backend.get_page_title())
        assert result == "SAP Easy Access"
    finally:
        stop.set()


def test_loopback_take_screenshot(tmp_path: Path) -> None:
    relay_dir, token, stop = _create_mock_relay(tmp_path)
    try:
        backend = CitrixBackend(relay_dir, token, poll_interval_s=0.02)
        result = asyncio.run(backend.take_screenshot())
        assert result == b"FAKE_PNG"
    finally:
        stop.set()


def test_loopback_fill_field(tmp_path: Path) -> None:
    relay_dir, token, stop = _create_mock_relay(tmp_path)
    try:
        backend = CitrixBackend(relay_dir, token, poll_interval_s=0.02)
        asyncio.run(backend.fill_field("Name", "Test"))  # Should not raise
    finally:
        stop.set()


def test_loopback_pydantic_model_roundtrip(tmp_path: Path) -> None:
    relay_dir, token, stop = _create_mock_relay(tmp_path)
    try:
        backend = CitrixBackend(relay_dir, token, poll_interval_s=0.02)
        result = asyncio.run(backend.get_session_status())
        assert result == {"logged_in": True}
    finally:
        stop.set()


def test_loopback_error_propagation(tmp_path: Path) -> None:
    """Verify that backend exceptions propagate as RelayError through the relay."""
    from sapwebguimcp.backend.citrix._exceptions import RelayError

    relay_dir, token, stop = _create_mock_relay(tmp_path)
    try:
        backend = CitrixBackend(relay_dir, token, poll_interval_s=0.02)
        with pytest.raises(RelayError, match="Button 'Nope' not found"):
            asyncio.run(backend.click_button("Nope"))
    finally:
        stop.set()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd sapwebgui.mcp && python -m pytest unittests/citrix/test_integration_loopback.py -v`
Expected: 5 passed

- [ ] **Step 3: Commit**

```bash
git add unittests/citrix/test_integration_loopback.py
git commit -m "test(citrix): add end-to-end loopback integration tests"
```

---

### Task 8: Linting, Formatting, Final Verification

- [ ] **Step 1: Run black formatter**

Run: `cd sapwebgui.mcp && python -m black src/sapwebguimcp/backend/citrix/ unittests/citrix/ relay/ src/sapwebguimcp/tools/_backend_utils.py src/sapwebguimcp/models/config.py src/sapwebguimcp/backend/manager.py`

- [ ] **Step 2: Run pylint**

Run: `cd sapwebgui.mcp && python -m pylint src/sapwebguimcp/backend/citrix/ --disable=all --enable=E`

- [ ] **Step 3: Run full test suite**

Run: `cd sapwebgui.mcp && python -m pytest unittests/ -v --ignore=unittests/desktop -x`
Expected: all passed, no regressions

- [ ] **Step 4: Commit any formatting fixes**

```bash
git add -u
git commit -m "style: format citrix backend code with black"
```
