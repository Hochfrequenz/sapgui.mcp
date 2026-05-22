# README Desktop Backend Documentation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update README.md to document the desktop (SAP GUI COM) backend alongside the existing WebGUI backend, focused on the .exe setup path.

**Architecture:** Pure documentation change — edit a single file (README.md) in 4 tasks: intro text, .exe section restructure, config table, architecture diagram.

**Tech Stack:** Markdown

**Spec:** `docs/superpowers/specs/2026-03-18-readme-desktop-backend-design.md`

---

## File Structure

```
README.md    # The only file modified
```

---

## Task 1: Update intro text and heading

**Files:**
- Modify: `README.md:1-9`

- [ ] **Step 1: Update heading and tagline**

Change lines 1 and 8-9 from:

```markdown
# SAP Web GUI MCP Server

An MCP (Model Context Protocol) server for SAP Web GUI browser automation.
Control SAP through Claude Desktop or Claude Code with persistent browser sessions.
```

To:

```markdown
# SAP MCP Server

An MCP (Model Context Protocol) server for SAP automation.
Control SAP through Claude Desktop or Claude Code — via **SAP GUI desktop** (COM) or **SAP Web GUI** (browser).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README heading and tagline for dual-backend support"
```

---

## Task 2: Restructure .exe section with desktop + WebGUI options

**Files:**
- Modify: `README.md:28-102` (the `<details>` block for Standalone Executable)

- [ ] **Step 1: Replace the .exe section content**

Replace the entire content inside the `<details>` block (lines 28-102) with:

````markdown
<details>
<summary><strong>📦 Standalone Executable (recommended — no Docker, no Python)</strong></summary>
<br>

Download `sapgui_mcp_windows_<version>.exe` from
[GitHub Releases](https://github.com/Hochfrequenz/sapgui.mcp/releases/latest).

Choose a backend:

| | Desktop Backend (SAP GUI) | WebGUI Backend (Browser) |
|---|---|---|
| **Platform** | Windows only | Windows, macOS, Linux |
| **Requires** | SAP GUI for Windows | Chrome browser |
| **Speed** | Faster (direct COM) | Slower (browser automation) |
| **Setup** | Simpler (no Chrome/CDP) | More steps |

### Option A: Desktop Backend (SAP GUI)

**Windows-only.** Automates SAP GUI directly via COM — no browser needed.

**Prerequisites:**
- SAP GUI for Windows installed (standard path — the server finds it automatically via Windows registry)
- SAP GUI Scripting enabled (one-time setup, see below)

<details>
<summary>Enable SAP GUI Scripting (one-time)</summary>

**Server side** (requires admin/basis team):
- Transaction `RZ11` → parameter `sapgui/user_scripting` → set to `TRUE`
- Dynamic parameter — no server restart needed, but users must re-login (close and reopen SAP GUI)

**Client side** (your PC):
1. Open SAP GUI → go to Options (menu bar or tray icon)
2. Navigate to **Accessibility & Scripting → Scripting**
3. Check **"Enable Scripting"**
4. Uncheck **"Notify when a script attaches to SAP GUI"**
5. Uncheck **"Notify when a script opens a connection"**

> [!IMPORTANT]
> The two notification checkboxes **must** be unchecked. If left checked, every COM connection triggers a modal popup that blocks automation.

</details>

#### Claude Desktop

Add to `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "sap-desktop": {
            "command": "C:/path/to/sapgui_mcp_windows_<version>.exe",
            "env": {
                "BACKEND_TYPE": "desktop",
                "SAP_CONNECTION_NAME": "Your SAP Logon Entry",
                "SAP_USER": "your_username",
                "SAP_PASSWORD": "your_password",
                "SAP_MANDANT": "100",
                "SAP_LANGUAGE": "DE"
            }
        }
    }
}
```

#### Claude Code

Add to `.mcp.json` in your project root:

```json
{
    "mcpServers": {
        "sap-desktop": {
            "command": "C:/path/to/sapgui_mcp_windows_<version>.exe",
            "env": {
                "BACKEND_TYPE": "desktop",
                "SAP_CONNECTION_NAME": "Your SAP Logon Entry",
                "SAP_USER": "your_username",
                "SAP_PASSWORD": "your_password",
                "SAP_MANDANT": "100",
                "SAP_LANGUAGE": "DE"
            }
        }
    }
}
```

Replace:
- `Your SAP Logon Entry` with the connection name from SAP Logon pad (e.g. `"HF S/4"`)
- `your_username` / `your_password` with your SAP credentials

No Chrome, no CDP proxy required.

### Option B: WebGUI Backend (Browser)

Automates SAP Web GUI through Chrome browser automation. Works on all platforms. This is the default — if you don't set `BACKEND_TYPE`, the server uses WebGUI.

#### Step 1: Start Chrome with remote debugging

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
```

> [!NOTE]
> **Chrome path may differ.** The path above is for a system-wide Chrome installation. If Chrome was installed only for your user, the path is typically:
>
> ```powershell
> & "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
> ```
>
> Not sure where Chrome is installed? See [Finding your Chrome path](#finding-your-chrome-path) in the Troubleshooting section below.

#### Step 2: Configure your MCP client

**Required:** `SAP_URL`, `SAP_USER`, `SAP_PASSWORD`, `SAP_MANDANT`. All other variables are optional — remove any you don't need. See [Configuration Reference](#configuration-reference) for the full list.

> `GITHUB_PAT` is only needed for `log_feedback` (creates GitHub issues) or abapGit operations. Remove it if you don't need these features.

##### Claude Desktop

Add to `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`, macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/sapgui_mcp_windows_<version>.exe",
            "env": {
                "SAP_URL": "https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "SAP_USER": "your_username",
                "SAP_PASSWORD": "your_password",
                "SAP_MANDANT": "100",
                "SAP_LANGUAGE": "DE",
                "GITHUB_PAT": "your_github_pat"
            }
        }
    }
}
```

##### Claude Code

Add to `.mcp.json` in your project root:

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/sapgui_mcp_windows_<version>.exe",
            "env": {
                "SAP_URL": "https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "SAP_USER": "your_username",
                "SAP_PASSWORD": "your_password",
                "SAP_MANDANT": "100",
                "SAP_LANGUAGE": "DE",
                "GITHUB_PAT": "your_github_pat"
            }
        }
    }
}
```

No Docker, no CDP proxy, no Python required.

</details>
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: restructure .exe section with desktop and WebGUI backend options"
```

---

## Task 3: Update Configuration Reference table

**Files:**
- Modify: `README.md` — the Configuration Reference table and footnotes

- [ ] **Step 1: Add BACKEND_TYPE and SAP_CONNECTION_NAME rows, update SAP_URL**

Replace the Configuration Reference table with:

```markdown
| Variable              | Required                          | Description                                                  | Default                      |
| --------------------- | --------------------------------- | ------------------------------------------------------------ | ---------------------------- |
| `BACKEND_TYPE`        | No                                | `webgui` (browser automation) or `desktop` (SAP GUI COM, Windows only) | `webgui`           |
| `SAP_CONNECTION_NAME` | When `BACKEND_TYPE=desktop`       | SAP Logon pad connection entry name (e.g. `"HF S/4"`)       | —                            |
| `SAP_URL`             | When `BACKEND_TYPE=webgui` <sup>1</sup> | SAP Web GUI URL                                        | `""`                         |
| `SAP_USER`            | **Yes** <sup>1</sup>             | SAP username for auto-login                                  | `""`                         |
| `SAP_PASSWORD`        | **Yes** <sup>1</sup>             | SAP password for auto-login                                  | `""`                         |
| `SAP_MANDANT`         | **Yes** <sup>1</sup>             | SAP client (3-digit, e.g., `100`)                            | `""`                         |
| `SAP_LANGUAGE`        | No                                | Login language (`DE` or `EN`)                                | `EN`                         |
| `BROWSER_MODE`        | No                                | `connect` (existing Chrome) or `launch` (Playwright). WebGUI only. | `connect`              |
| `BROWSER_TYPE`        | No                                | `chromium`, `firefox`, or `webkit`. WebGUI only.             | `chromium`                   |
| `BROWSER_HEADLESS`    | No                                | Run browser in headless mode. WebGUI only.                   | `false`                      |
| `CDP_URL`             | When `BROWSER_MODE=connect`       | Chrome DevTools Protocol URL. WebGUI only.                   | `http://localhost:9222`      |
| `GITHUB_PAT`          | No                                | GitHub PAT for `log_feedback` issues and abapGit auth        | —                            |
| `GITHUB_USER`         | No                                | GitHub username for abapGit (falls back to `x-access-token`) | —                            |
| `GITHUB_REPO`         | No                                | Repository for feedback issues                               | `Hochfrequenz/sapgui.mcp` |
| `ABAPGIT_PAT`         | No                                | Separate PAT for abapGit (overrides `GITHUB_PAT` if set)     | —                            |
| `PAPERTRAIL_HOST`     | No                                | Papertrail syslog host (empty to disable)                    | `""` (off) <sup>2</sup>      |
| `PAPERTRAIL_PORT`     | No                                | Papertrail syslog port                                       | `0` (off) <sup>2</sup>       |
| `LOG_FORMAT`          | No                                | Set to `json` for JSON log output                            | `""` (human-readable)        |
| `LOG_LEVEL`           | No                                | `DEBUG`, `INFO`, `WARNING`, or `ERROR`                       | `INFO`                       |
```

Footnote 1 stays the same. No change to footnote 2.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add BACKEND_TYPE and SAP_CONNECTION_NAME to config reference"
```

---

## Task 4: Update Architecture diagram

**Files:**
- Modify: `README.md` — the Architecture section

- [ ] **Step 1: Add desktop architecture diagram and label the existing one**

Replace the Architecture section with:

````markdown
## Architecture

The server supports two backends. Choose one via `BACKEND_TYPE`.

**WebGUI Backend** (`BACKEND_TYPE=webgui`, default):

```
┌─────────────────────────────────────────────────────────┐
│  Chrome (with --remote-debugging-port=9222)             │
│  - SAP Web GUI loaded                                   │
│  - Persistent session                                   │
└─────────────────────────────────────────────────────────┘
            ↑
            │ CDP (Chrome DevTools Protocol)
            ↓
┌─────────────────────────────────────────────────────────┐
│  CDP Proxy (nginx) - only needed for Docker             │
│  - Rewrites Host header for Chrome                      │
│  - Rewrites WebSocket URLs                              │
└─────────────────────────────────────────────────────────┘
            ↑
            │ HTTP/WebSocket
            ↓
┌─────────────────────────────────────────────────────────┐
│  MCP Server (sapguimcp)                              │
│  - Playwright for browser automation                    │
│  - SAP-specific tools                                   │
└─────────────────────────────────────────────────────────┘
            ↑
            │ MCP (stdio)
            ↓
┌─────────────────────────────────────────────────────────┐
│  Claude Desktop / Claude Code                           │
└─────────────────────────────────────────────────────────┘
```

**Desktop Backend** (`BACKEND_TYPE=desktop`, Windows only):

```
┌─────────────────────────────────────────────────────────┐
│  SAP GUI for Windows                                    │
│  - COM Scripting API                                    │
│  - Persistent session(s)                                │
└─────────────────────────────────────────────────────────┘
            ↑
            │ COM (pywin32)
            ↓
┌─────────────────────────────────────────────────────────┐
│  MCP Server (sapguimcp)                              │
│  - Desktop backend with COM thread                      │
│  - SAP-specific tools                                   │
└─────────────────────────────────────────────────────────┘
            ↑
            │ MCP (stdio)
            ↓
┌─────────────────────────────────────────────────────────┐
│  Claude Desktop / Claude Code                           │
└─────────────────────────────────────────────────────────┘
```
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add desktop backend architecture diagram"
```
