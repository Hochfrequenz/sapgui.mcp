# Standalone Executable Bundling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bundle the MCP server as a single Windows `.exe` so SAP consultants can use it without Docker, GHCR, or Python.

**Architecture:** PyInstaller `--onefile` bundles `server.py` into a standalone exe. Connect-mode only (user's Chrome via CDP). Chrome CDP check at startup logs guidance if Chrome is not detected. CI smoke test verifies the exe starts and responds to MCP initialize.

**Tech Stack:** PyInstaller, tox, GitHub Actions, httpx (already a dependency)

---

### Task 1: Add PyInstaller dependency and tox environment

**Files:**

- Modify: `pyproject.toml`
- Modify: `tox.ini`

**Step 1: Add `build_executable` optional dependency to `pyproject.toml`**

In the `[project.optional-dependencies]` section, after the `dev` group, add:

```toml
build_executable = [
    "pyinstaller>=6.0.0",
]
```

**Step 2: Add `build_executable` tox environment to `tox.ini`**

After the `[testenv:compile_requirements]` section, add:

```ini
[testenv:build_executable]
skip_install = true
deps =
    -r requirements.txt
    .[build_executable]
commands =
    pyinstaller --onefile --name sapgui_mcp_windows src/sapguimcp/server.py
```

**Step 3: Run formatting**

Run: `python -m black pyproject.toml` (no-op, toml not formatted by black)
Run: `npm run format` (checks markdown)

**Step 4: Commit**

```bash
git add pyproject.toml tox.ini
git commit -m "feat: add build_executable tox environment for PyInstaller bundling"
```

---

### Task 2: Add Chrome CDP check at startup

**Files:**

- Modify: `src/sapguimcp/server.py` (in `app_lifespan`)

**Step 1: Write the failing test**

Create test in `unittests/test_server_cdp_check.py`:

```python
"""Tests for Chrome CDP detection at startup."""

import logging

import pytest
import respx
from httpx import Response

from sapguimcp.server import _check_cdp_available


class TestCdpCheck:
    """Tests for the CDP availability check."""

    @respx.mock
    @pytest.mark.anyio
    async def test_cdp_check_success(self, caplog: pytest.LogCaptureFixture) -> None:
        """Logs info when Chrome CDP is reachable."""
        respx.get("http://localhost:9222/json/version").mock(
            return_value=Response(200, json={"Browser": "Chrome/120"})
        )
        with caplog.at_level(logging.INFO):
            await _check_cdp_available("http://localhost:9222")
        assert "Chrome CDP detected" in caplog.text

    @respx.mock
    @pytest.mark.anyio
    async def test_cdp_check_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """Logs warning with guidance when Chrome CDP is not reachable."""
        respx.get("http://localhost:9222/json/version").mock(side_effect=ConnectionError)
        with caplog.at_level(logging.WARNING):
            await _check_cdp_available("http://localhost:9222")
        assert "Chrome not detected" in caplog.text
        assert "--remote-debugging-port=9222" in caplog.text
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_server_cdp_check.py -v`
Expected: FAIL with `ImportError: cannot import name '_check_cdp_available'`

**Step 3: Implement `_check_cdp_available` in `server.py`**

Add this function before `app_lifespan`:

```python
async def _check_cdp_available(cdp_url: str) -> None:
    """Log Chrome CDP availability status. Non-blocking — warns but does not fail."""
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{cdp_url}/json/version", timeout=2.0)
        logger.info("Chrome CDP detected at %s", cdp_url)
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        logger.warning(
            "Chrome not detected on CDP. "
            "Please start Chrome with: "
            'chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\temp\\chrome-debug"'
        )
```

Add `import httpx` to the imports.

Call it in `app_lifespan` right after the "Server starting" log:

```python
await _check_cdp_available(_settings.cdp_url)
```

Also export `_check_cdp_available` in `__all__` for testability.

**Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_server_cdp_check.py -v`
Expected: PASS

**Step 5: Run formatting**

Run: `python -m isort src/sapguimcp/server.py unittests/test_server_cdp_check.py`
Run: `python -m black src/sapguimcp/server.py unittests/test_server_cdp_check.py`

**Step 6: Commit**

```bash
git add src/sapguimcp/server.py unittests/test_server_cdp_check.py
git commit -m "feat: add Chrome CDP detection with user guidance at startup"
```

---

### Task 3: Write the smoke test script

**Files:**

- Create: `unittests/smoke_test_exe.py`

**Step 1: Create smoke test script**

```python
"""Smoke test for the standalone executable.

Starts the exe, sends an MCP initialize request, verifies the response.
Usage: python unittests/smoke_test_exe.py <path-to-exe>
"""

import json
import subprocess
import sys
import time


def main() -> None:
    exe_path = sys.argv[1]
    initialize_request = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smoke-test", "version": "0.1.0"},
            },
        }
    )

    print(f"Starting {exe_path}...")
    proc = subprocess.Popen(
        [exe_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Give the server a moment to start
        time.sleep(3)

        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            print(f"FAIL: Process exited early with code {proc.returncode}")
            print(f"stderr: {stderr}")
            sys.exit(1)

        # Send initialize request
        assert proc.stdin is not None
        proc.stdin.write(initialize_request + "\n")
        proc.stdin.flush()

        # Read response (with timeout)
        assert proc.stdout is not None
        proc.stdout.readline()  # may be empty or a header line

        # Give it a moment to respond
        time.sleep(2)

        # Try to read the actual JSON response
        # MCP uses Content-Length headers, but we just need to verify we get valid JSON back
        response_lines: list[str] = []
        start = time.time()
        while time.time() - start < 10:
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "result" in data or "error" in data:
                    response_lines.append(line)
                    break
            except json.JSONDecodeError:
                # Could be a Content-Length header or log line
                continue

        if not response_lines:
            print("FAIL: No valid JSON-RPC response received within 10 seconds")
            sys.exit(1)

        response = json.loads(response_lines[0])
        if "result" in response:
            print(f"OK: Got valid MCP initialize response: {json.dumps(response['result'], indent=2)[:200]}")
            sys.exit(0)
        else:
            print(f"FAIL: Got error response: {response}")
            sys.exit(1)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
```

**Step 2: Run formatting**

Run: `python -m isort unittests/smoke_test_exe.py`
Run: `python -m black unittests/smoke_test_exe.py`

**Step 3: Commit**

```bash
git add unittests/smoke_test_exe.py
git commit -m "feat: add smoke test script for standalone executable"
```

---

### Task 4: Add CI workflow for building the exe

**Files:**

- Create: `.github/workflows/build_executable.yml`

**Step 1: Create the workflow**

```yaml
name: Build Executable

on:
    push:
        branches: [main]
    pull_request:
        branches: [main]
    release:
        types: [created]

jobs:
    build_standalone_executable:
        needs: []
        strategy:
            matrix:
                python-version: ['3.12']
                os: [windows-latest]
        runs-on: ${{ matrix.os }}
        steps:
            - name: Checkout code
              uses: actions/checkout@v6

            - name: Set up Python ${{ matrix.python-version }}
              uses: actions/setup-python@v6
              with:
                  python-version: ${{ matrix.python-version }}

            - name: Build Executable
              run: |
                  pip install tox
                  tox -e build_executable

            - name: Smoke Test
              run: python unittests/smoke_test_exe.py dist/sapgui_mcp_windows.exe

            - name: Upload Executable as Artifact
              uses: actions/upload-artifact@v6
              with:
                  name: sapgui_mcp_windows
                  path: dist/sapgui_mcp_windows.exe

            - name: Upload Executable to Release
              if: github.event_name == 'release'
              uses: softprops/action-gh-release@v2
              with:
                  files: dist/sapgui_mcp_windows.exe
```

**Step 2: Commit**

```bash
git add .github/workflows/build_executable.yml
git commit -m "ci: add workflow to build and smoke-test standalone executable"
```

---

### Task 5: Test the build locally

**Step 1: Build the exe locally**

Run: `tox -e build_executable`
Expected: PyInstaller produces `dist/sapgui_mcp_windows.exe`

This step may fail due to Playwright hidden imports or missing data files. If so:

**Step 2 (if needed): Create a PyInstaller spec file**

If PyInstaller fails to bundle correctly (missing modules, Playwright issues), create `sapgui_mcp_windows.spec` with explicit `hiddenimports` and `datas` entries. Common fixes:

- Add `hiddenimports=['sapguimcp.tools', 'sapguimcp.parsers', ...]` for all subpackages
- Add `datas` for `src/sapguimcp/js/*.js` and `src/sapguimcp/prompts/*.md`
- Exclude Playwright browser binaries with `excludes`

Update tox.ini to use the spec file:

```ini
commands =
    pyinstaller sapgui_mcp_windows.spec
```

**Step 3: Run the smoke test locally**

Run: `python unittests/smoke_test_exe.py dist/sapgui_mcp_windows.exe`
Expected: `OK: Got valid MCP initialize response`

**Step 4: Commit any spec file or fixes**

```bash
git add -A
git commit -m "fix: adjust PyInstaller config for correct bundling"
```

---

### Task 6: Update documentation

**Files:**

- Modify: `README.md`
- Modify: `.env.example` (no change needed — env vars work the same)

**Step 1: Add "Standalone Executable" section to README**

After the Docker "Quick Start" section and before "Development Setup", add a new section:

````markdown
## Standalone Executable (no Docker)

If you prefer not to use Docker, download the standalone `.exe` from
[GitHub Releases](https://github.com/Hochfrequenz/sapgui.mcp/releases).

### Step 1: Start Chrome with remote debugging

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
```
````

### Step 2: Configure your MCP client

Point your Claude config to the exe:

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/sapgui_mcp_windows.exe",
            "env": {
                "SAP_URL": "https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "SAP_USER": "your_username",
                "SAP_PASSWORD": "your_password",
                "SAP_MANDANT": "100",
                "SAP_LANGUAGE": "EN"
            }
        }
    }
}
```

No Docker, no CDP proxy, no Python required.

````

**Step 2: Run formatting**

Run: `npm run format`

**Step 3: Commit**

```bash
git add README.md docs/plans/2026-02-18-exe-bundling-design.md docs/plans/2026-02-18-exe-bundling-plan.md
git commit -m "docs: add standalone executable setup instructions and design docs"
````

---

### Task 7: Push and create PR

**Step 1: Push**

```bash
git push -u origin feat/exe-bundling
```

**Step 2: Create PR**

Title: `feat: standalone Windows executable (no Docker required)`

Body should summarize: PyInstaller bundling, Chrome CDP check, CI smoke test, README docs.
