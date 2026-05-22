# Standalone Executable Bundling

## Problem

Running the MCP server currently requires Docker, `docker login ghcr.io` with a GitHub account, and a CDP proxy container. This is too much friction for SAP consultants who are comfortable with SAP but not with Docker, git, or CLI tooling.

## Solution

Bundle the MCP server as a single Windows `.exe` using PyInstaller. The exe connects to the user's own Chrome browser via CDP (connect mode only). No Docker, no GHCR, no CDP proxy needed.

## User Experience (Target)

1. Download `sapgui_mcp_windows.exe` from GitHub Releases
2. Start Chrome: `chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug"`
3. Add to Claude config:

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/tools/sapgui_mcp_windows.exe",
            "env": {
                "SAP_URL": "https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "SAP_USER": "your_username",
                "SAP_PASSWORD": "your_password",
                "SAP_MANDANT": "100"
            }
        }
    }
}
```

No Docker, no GHCR login, no CDP proxy, no Python.

## Design Decisions

### Connect mode only

The exe does NOT bundle Playwright's Chromium browser (~150MB). It connects to the user's existing Chrome via `BROWSER_MODE=connect`. This keeps the exe small and avoids requiring `playwright install`.

The default `CDP_URL` is already `http://localhost:9222`, so users don't need to set it explicitly.

### Chrome CDP detection at startup

On startup (in `app_lifespan`), the server checks if `http://localhost:9222/json/version` responds. If not, it logs a clear message:

```
Chrome not detected on CDP port 9222.
Please start Chrome with remote debugging enabled:
  chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug"
```

This is a warning, not a fatal error -- the user might start Chrome after the server.

### Build tooling

Follows the existing Hochfrequenz pattern (lpex2csv, maus):

- `pyinstaller` added as optional dependency under `[project.optional-dependencies] build_executable`
- `tox -e build_executable` runs `pyinstaller --onefile --name sapgui_mcp_windows src/sapguimcp/server.py`
- CI workflow builds the exe on `windows-latest` and uploads to GitHub Releases

### CI smoke test

After building the exe, a smoke test verifies it works:

1. Start the exe as a subprocess
2. Send a minimal MCP `initialize` JSON-RPC request on stdin
3. Verify we get a valid JSON-RPC response on stdout
4. Kill the process

This proves all imports resolve and the bundling is correct, without needing a real SAP system or Chrome.

### Code signing

Use the existing Hochfrequenz code signing setup (as in mig_ahb_utility_stack). Unsigned exes trigger Windows SmartScreen warnings that SAP consultants may not be able to bypass without admin rights.

## What Changes

### pyproject.toml

Add optional dependency:

```toml
build_executable = [
    "pyinstaller>=6.0.0",
]
```

### tox.ini

Add environment:

```ini
[testenv:build_executable]
skip_install = true
deps =
    -r requirements.txt
    .[build_executable]
commands =
    pyinstaller --onefile --name sapgui_mcp_windows src/sapguimcp/server.py
```

### server.py

Add Chrome CDP check in `app_lifespan`:

```python
import httpx

try:
    async with httpx.AsyncClient() as client:
        await client.get(f"{_settings.cdp_url}/json/version", timeout=2.0)
        logger.info("Chrome CDP detected at %s", _settings.cdp_url)
except (httpx.ConnectError, httpx.TimeoutException):
    logger.warning(
        "Chrome not detected on CDP port. "
        'Start Chrome with: chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\temp\\chrome-debug"'
    )
```

### CI workflow (new or extend existing)

```yaml
build_standalone_executable:
    needs: tests
    strategy:
        matrix:
            python-version: ['3.12']
            os: [windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
        - uses: actions/checkout@v6
        - uses: actions/setup-python@v6
          with:
              python-version: ${{ matrix.python-version }}
        - name: Build Executable
          run: |
              pip install tox
              tox -e build_executable
        - name: Smoke Test
          run: |
              # send MCP initialize request and verify response
              python unittests/smoke_test_exe.py dist/sapgui_mcp_windows.exe
        - name: Upload to Release
          if: github.event_name == 'release'
          uses: softprops/action-gh-release@v2
          with:
              files: dist/sapgui_mcp_windows.exe
```

### smoke_test_exe.py (new)

A small script that:

1. Starts the exe as a subprocess (stdin/stdout pipes)
2. Sends `{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "smoke-test", "version": "0.1.0"}}}`
3. Reads stdout, verifies we get a valid JSON-RPC response with `"result"` containing server capabilities
4. Sends shutdown, kills process
5. Exits 0 on success, 1 on failure

## Out of Scope

- macOS/Linux builds (Windows only for now, matching the SAP consultant target)
- Auto-update mechanism
- Bundling Chrome/Chromium inside the exe
- Desktop shortcut creation for Chrome launch (nice-to-have for later)
- `launch` browser mode in the exe

## Risks

- **PyInstaller + Playwright**: Playwright has native bindings and internal browser management code. Even though we only use the CDP client, PyInstaller may try to bundle browser-related files. May need a `.spec` file with explicit excludes.
- **Antivirus false positives**: PyInstaller exes sometimes get flagged. VirusTotal submission after build helps.
- **Binary size**: Python + Playwright + Pydantic + httpx will likely produce a 50-100MB exe. Acceptable per user's input.
