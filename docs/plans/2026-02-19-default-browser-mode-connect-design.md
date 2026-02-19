# Design: Change Default BROWSER_MODE to `connect`

## Problem

The PyInstaller exe distribution fails on `sap_login` because `BROWSER_MODE` defaults to `launch`. Playwright's `chromium.launch()` requires browser binaries (~400MB) that are not bundled in the exe and not installed on the user's machine via `playwright install`.

Meanwhile, Chrome with CDP on port 9222 is already a documented prerequisite — users start it before using the MCP server.

## Solution

Change the default `BROWSER_MODE` from `launch` to `connect`.

With `connect_over_cdp()`, Playwright connects via WebSocket to an already-running Chrome. It does **not** need Playwright's browser binaries. This eliminates the entire error category.

## Changes

1. **`models/config.py`** — Change `BrowserMode` default from `LAUNCH` to `CONNECT`. Update docstring to document that `launch` is opt-in for development.
2. **`models/browser.py`** — Add comments explaining CDP expectations and why `connect` is the default.
3. **README.md** — Update the example `.env` snippet to reflect the new default.
4. **Tests** — Update any tests that assert `LAUNCH` as the default.

## Assumptions

- Chrome with `--remote-debugging-port=9222` is running before the MCP server starts.
- `CDP_URL` defaults to `http://localhost:9222` (standard Chrome debugging port).
- `launch` mode remains available for developers who want Playwright-managed browsers.
