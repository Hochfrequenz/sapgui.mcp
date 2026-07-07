# SAP GUI MCP Server

[![Unittests](https://github.com/Hochfrequenz/sapgui.mcp/workflows/Unittests/badge.svg)](https://github.com/Hochfrequenz/sapgui.mcp/actions)
[![Coverage](https://github.com/Hochfrequenz/sapgui.mcp/workflows/Coverage/badge.svg)](https://github.com/Hochfrequenz/sapgui.mcp/actions)
[![Linting](https://github.com/Hochfrequenz/sapgui.mcp/workflows/Linting/badge.svg)](https://github.com/Hochfrequenz/sapgui.mcp/actions)
[![Formatting](https://github.com/Hochfrequenz/sapgui.mcp/workflows/Formatting/badge.svg)](https://github.com/Hochfrequenz/sapgui.mcp/actions)

An MCP (Model Context Protocol) server for SAP automation.
Control SAP through Claude Desktop, Claude Code, or [opencode](https://opencode.ai) - via **SAP GUI desktop** or **SAP Web GUI** (browser).
Because it drives the real SAP UI (not a headless API), it is especially well-suited for **end-to-end testing**, **visual validation**, and **capturing screenshots for documentation** - tasks a pure REST-API client cannot do.
The MCP works with both SAP R/3 and S/4.

> [!NOTE]
> **Pairs with [`aibap.mcp`](https://github.com/Hochfrequenz/aibap.mcp).** The two servers complement each other in a two-agent vibe-coding setup: one agent writes ABAP via `aibap.mcp` (ADT REST), while a second agent drives this server to test the generated code in the real SAP UI, capture screenshots, and report failures back. See [`AIBAP_TEMPLATE_REPOSITORY`](https://github.com/Hochfrequenz/AIBAP_TEMPLATE_REPOSITORY) for a template that documents this workflow end-to-end.

> [!TIP]
> **Save tokens with `sap_run_script`!** 🚀 Instead of dozens of back-and-forth tool calls, the AI agent can write and execute a single Python script that loops, branches, and collects results - all in one shot. You just describe what you need; the agent generates the script automatically. Perfect for repetitive workflows like reading 50 table rows or bulk-updating fields. Runs in a secure sandbox against the SAP GUI COM API. Desktop backend only. See [Desktop COM Tools](#desktop-com-tools-desktop-backend-only).

> **Developer?** See [ARCHITECTURE.md](ARCHITECTURE.md) for codebase structure, request flow diagrams, and how to add new transaction tools. The **Development Setup** section at the bottom of this page covers running from source.

## Setup

Pick an installation method below - each one walks you through two things: creating your SAP credentials file (`systems.json`) and registering the MCP server with your AI client.

> [!NOTE]
> **Why a separate credentials file?** Most MCP servers put SAP credentials directly in the per-project MCP config (`env` block), which means re-entering them for every tool. Here, credentials live in a single shared file (`systems.json`) that all Hochfrequenz SAP MCP servers read automatically - so this server and [`aibap.mcp`](https://github.com/Hochfrequenz/aibap.mcp) both work with the same credentials without duplication.

Choose one of these three approaches:

**Where to register the MCP server:**

- **Claude Code** - add to `.mcp.json` in your project root (per-project config)
- **Claude Desktop** - add to `claude_desktop_config.json` (global config, path varies by OS - shown in each section below)
- **[opencode](https://opencode.ai)** - add to `opencode.json` in your project root. Each section below includes a ready-to-use `opencode.json` snippet alongside the Claude Code snippet.

> [!WARNING]
> **Special characters in passwords:** If your SAP password contains `"` or `\` characters, you must escape them in the JSON config files: `"` becomes `\"` and `\` becomes `\\`. For example, `pass"word` becomes `"pass\"word"` and `do\main` becomes `"do\\main"`. Unescaped special characters will silently break the JSON and the MCP server will fail to start.

> [!TIP]
> **Windows file extensions:** If file extensions are hidden in Windows Explorer, creating `.mcp.json` via right-click → New → Text File will produce `.mcp.json.txt` (or `.mcp.json.json` if you rename). Make sure "File name extensions" is checked in Explorer's View tab, then rename the file.

<details>
<summary><strong>📦 Standalone Executable (recommended - no Docker, no Python)</strong></summary>
<br>

Download the binary for your platform from
[GitHub Releases](https://github.com/Hochfrequenz/sapgui.mcp/releases/latest):

| Platform         | Binary                                    |
| ---------------- | ----------------------------------------- |
| Windows (x64)    | `sapgui_mcp_windows_<version>.exe`        |
| macOS (Apple Silicon) | `sapgui_mcp_macos_arm64_<version>` |

> [!NOTE]
> The macOS binary supports the **WebGUI backend only** (browser automation). The desktop backend requires SAP GUI for Windows (COM Scripting) and is not available on macOS.
>
> **macOS Gatekeeper:** If macOS refuses to run the binary, clear the quarantine attribute: `xattr -c sapgui_mcp_macos_arm64_<version>`

Choose a backend:

|              | Desktop Backend (SAP GUI)            | WebGUI Backend (Browser)                     |
| ------------ | ------------------------------------ | -------------------------------------------- |
| **Platform** | Windows only                         | Windows, macOS, Linux                        |
| **Requires** | SAP GUI for Windows                  | Chrome browser                               |
| **Speed**    | Faster (works directly with SAP GUI) | Slower (works through a web browser)         |
| **Setup**    | Simpler (just SAP GUI + this tool)   | More steps (also needs Chrome browser setup) |

### Option A: Desktop Backend (SAP GUI) - recommended for Windows users

Automates SAP GUI directly - no browser needed. Windows only.
Uses [sapsucker](https://github.com/Hochfrequenz/sapsucker) for typed SAP GUI Scripting access.

**Prerequisites:**

- SAP GUI for Windows installed (standard path - the server finds it automatically via Windows registry)
- SAP GUI Scripting enabled (one-time setup, see below)

<details>
<summary>Enable SAP GUI Scripting (one-time)</summary>

**Server side** (requires admin/basis team):

- Transaction `RZ11` → parameter `sapgui/user_scripting` → set to `TRUE`
- Dynamic parameter - no server restart needed, but users must re-login (close and reopen SAP GUI)

**Client side** (your PC):

1. Open SAP Logon or any SAP GUI session
2. Go to **Options** (via menu bar, tray icon, or press **Alt+F12** in a session)
3. Navigate to **Accessibility & Scripting → Scripting** (DE: **Barrierefreiheit & Skripting → Skripting**)
4. Check **"Enable Scripting"** (DE: **"Skripting aktivieren"**)
5. Uncheck **"Notify when a script attaches to SAP GUI"**
6. Uncheck **"Notify when a script opens a connection"**

> [!IMPORTANT]
> The two notification checkboxes **must** be unchecked. If left checked, every COM connection triggers a modal popup that blocks automation.

</details>

#### Step 1: Create the SAP config file (`systems.json`)

This file holds your SAP credentials and is shared with [aibap.mcp](https://github.com/Hochfrequenz/aibap.mcp) - configure it once and all Hochfrequenz SAP MCP servers will use it.

On **Windows**, open Windows Explorer and paste this into the address bar:

```
%USERPROFILE%\.config\sap-mcp
```

Create the folder if it doesn't exist, then create a file called `systems.json` inside it. On **macOS/Linux**, the path is `~/.config/sap-mcp/systems.json`.

There are two distinct identifiers per system - don't mix them up:

| Concept | Example | Where it's used |
| --- | --- | --- |
| **System key** (dictionary key) | `"dev"`, `"qa"` | `sap_login(system_key="qa")` - selects which system to log into |
| **SAP Logon entry** (`connection_name` field) | `"HF S/4"`, `"DEV - ERP Development"` | Must match the **bold description** in the SAP Logon pad exactly |

The SAP Logon entry is _not_ the 3-character System ID (SID):

| What you see in SAP Logon | `connection_name` value     | NOT this (SID) |
| ------------------------- | --------------------------- | -------------- |
| **HF S/4**                | `"HF S/4"`                  | ~~`"HFQ"`~~    |
| **DEV - ERP Development** | `"DEV - ERP Development"`   | ~~`"DEV"`~~    |

If the `connection_name` doesn't match exactly, you'll get _"SAP Logon connection entry not found"_.

```json
{
    "default_system": "dev",
    "systems": {
        "dev": {
            "connection_name": "HF S/4",
            "host": "https://your-sap-system:44300",
            "client": "100",
            "user": "your_username",
            "password": "your_password",
            "language": "DE"
        }
    }
}
```

> [!NOTE]
> If your SAP system uses a self-signed or internally-signed certificate (common for VPN/intranet systems), add `"tls_skip_verify": true` to the system entry. Leave it out if your system has a publicly-trusted certificate.

> [!IMPORTANT]
> After editing `systems.json`, restart Claude Desktop, Claude Code, or opencode for the changes to take effect.

See [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) for the complete field reference - all optional fields, validation rules, YAML support, and a visual guide to finding your `connection_name` in SAP Logon.

#### Step 2: Configure your MCP client

> [!TIP]
> Note the full path to the downloaded `.exe`. For example, if you saved `sapgui_mcp_windows_1.5.0.exe` to your Downloads folder, the path is `C:/Users/YourName/Downloads/sapgui_mcp_windows_1.5.0.exe`. Always use forward slashes (`/`) in JSON, not backslashes (`\`).

##### Claude Desktop

Add to `claude_desktop_config.json`. To open the file: press **Win+R**, type `%APPDATA%\Claude`, press Enter. If `claude_desktop_config.json` does not exist, create a new text file with that exact name (make sure it ends in `.json`, not `.json.txt`).

```json
{
    "mcpServers": {
        "sap-desktop": {
            "command": "C:/path/to/sapgui_mcp_windows_<version>.exe",
            "env": {
                "BACKEND_TYPE": "desktop"
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
        "sap-desktop": {
            "command": "C:/path/to/sapgui_mcp_windows_<version>.exe",
            "env": {
                "BACKEND_TYPE": "desktop"
            }
        }
    }
}
```

##### opencode

Add to `opencode.json` in your project root:

```json
{
    "$schema": "https://opencode.ai/config.json",
    "mcp": {
        "sap-desktop": {
            "type": "local",
            "command": ["C:/path/to/sapgui_mcp_windows_<version>.exe"],
            "enabled": true,
            "environment": {
                "BACKEND_TYPE": "desktop"
            }
        }
    }
}
```

> [!TIP]
> In `opencode.json`, you can use either forward slashes (`C:/path/to/...`) or double-escaped backslashes (`C:\\path\\to\\...`) in the `command` path. Single backslashes will break the JSON silently.

#### Multi-system access (desktop backend only)

Multi-system support is built into `systems.json` - add multiple systems and the LLM can switch between them:

**How it works:**

1. `sap_list_connections` returns both configured systems (from `systems.json`) and SAP Logon entries (from `SAPUILandscape.xml`).
2. `sap_login(system_key="qa")` logs into a specific system using credentials from `systems.json`.

**Configuration:** Add multiple systems to your `systems.json`. The **dictionary key** (e.g. `"dev"`, `"qa"`) is the `system_key` you pass to `sap_login`. The `connection_name` field must match the SAP Logon entry description exactly:

```json
{
    "default_system": "dev",
    "systems": {
        "dev": {
            "connection_name": "HF S/4",
            "host": "https://dev-sap:44300",
            "client": "100",
            "user": "dev_user",
            "password": "dev_pass",
            "language": "DE"
        },
        "qa": {
            "connection_name": "QA System",
            "host": "https://qa-sap:44300",
            "client": "200",
            "user": "qa_user",
            "password": "qa_pass",
            "language": "EN"
        }
    }
}
```

When `sap_login(system_key="qa")` is called, it looks up `"qa"` in `systems.json`, reads the credentials, and uses the `connection_name` field (`"QA System"`) to open the matching SAP Logon entry. If the system key is not found, an error is returned listing the available keys.

No Chrome, no browser setup required.

#### Verify the setup

Before your first prompt, check that the MCP server starts correctly. Open PowerShell and run:

**Claude Code:**
```
claude mcp list
```
Expected output:
```
sap-desktop: C:/path/to/sapgui_mcp_windows_<version>.exe ✓ Connected
```

**opencode:**
```
opencode mcp list
```
Expected output:
```
● ✓ sap-desktop connected
```

If you see `✗ Failed` or `✗ failed`, the most common cause is a wrong path to the `.exe` in your config file. Double-check the path and that the file exists there. Run `opencode mcp debug sap-desktop` for more detail.

> [!TIP]
> **Getting started:** Restart Claude Desktop, Claude Code, or opencode, then try: _"Log me into SAP"_ or _"Run transaction SE16"_. SAP GUI will open automatically if it is not already running.

### Option B: WebGUI Backend (Browser)

Automates SAP Web GUI through Chrome browser automation. Works on all platforms. This is the default - if you don't set `BACKEND_TYPE`, the server uses WebGUI.

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

#### Step 2: Create `systems.json`

Create the SAP config file if you haven't already (Windows: `%USERPROFILE%\.config\sap-mcp\systems.json`, macOS/Linux: `~/.config/sap-mcp/systems.json`). See [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) for the full field reference and YAML support.

```json
{
    "default_system": "dev",
    "systems": {
        "dev": {
            "host": "https://your-sap-server:44300",
            "client": "100",
            "user": "your_username",
            "password": "your_password",
            "language": "DE"
        }
    }
}
```

> [!NOTE]
> If your SAP system uses a self-signed or internally-signed certificate (common for VPN/intranet systems), add `"tls_skip_verify": true` to the system entry. Leave it out if your system has a publicly-trusted certificate.

> [!NOTE]
> The WebGUI backend connects directly to the `host` URL - there is no SAP Logon application involved, so `connection_name` is not needed here (unlike the Desktop backend).

> [!NOTE]
> The WebGUI URL is derived automatically from `host` as `{host}/sap/bc/gui/sap/its/webgui`. If your SAP system uses a non-standard WebGUI path, set `SAP_URL` in the MCP config below.

#### Step 3: Configure your MCP client

##### Claude Desktop

Add to `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`, macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/sapgui_mcp_windows_<version>.exe",
            "env": {}
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
            "env": {}
        }
    }
}
```

##### opencode

Add to `opencode.json` in your project root:

```json
{
    "$schema": "https://opencode.ai/config.json",
    "mcp": {
        "sap-webgui": {
            "type": "local",
            "command": ["C:/path/to/sapgui_mcp_windows_<version>.exe"],
            "enabled": true,
            "environment": {}
        }
    }
}
```

> [!TIP]
> In `opencode.json`, you can use either forward slashes (`C:/path/to/...`) or double-escaped backslashes (`C:\\path\\to\\...`) in the `command` path. Single backslashes will break the JSON silently.

> [!NOTE]
> `GITHUB_PAT` is optional - only needed for `log_feedback` (creates GitHub issues) and abapGit operations with private repos. Add it to the `env` / `environment` block only if you need those features.

No Docker, no CDP proxy, no Python required.

#### Verify the setup

Before your first prompt, check that the MCP server starts correctly. Open a terminal (PowerShell on Windows, Terminal on macOS/Linux) and run:

**Claude Code:**
```
claude mcp list
```
Expected output:
```
sap-webgui: C:/path/to/sapgui_mcp_windows_<version>.exe ✓ Connected
```

**opencode:**
```
opencode mcp list
```
Expected output:
```
● ✓ sap-webgui connected
```

If you see `✗ Failed`, the most common cause is a wrong path to the `.exe`. Run `opencode mcp debug sap-webgui` for more detail.

> [!TIP]
> **Getting started:** Restart Claude Desktop, Claude Code, or opencode, then try: _"Log me into SAP"_ or _"Take a screenshot of the current SAP screen"_.

</details>

<details>
<summary><strong>🐳 Docker</strong></summary>
<br>

This guide gets you running with Docker on Windows - no Python or cloning required.

<details>
<summary><strong>macOS users: click here for differences</strong></summary>

The setup is similar on macOS, with these differences:

**Chrome command:**

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" --ignore-certificate-errors
```

**Verify Chrome:**

```bash
curl http://localhost:9222/json/version
```

**Config file location:**

- Claude Desktop: `~/Library/Application Support/Claude/claude_desktop_config.json`

Everything else (Docker setup, CDP proxy, MCP config) is identical.

</details>

### Prerequisites

- **Docker Desktop** for Windows ([download](https://www.docker.com/products/docker-desktop/))
- **Chrome** browser
- **VPN client** connected (if your SAP system is on an internal network)

Verify Docker is running:

```powershell
docker --version
```

### Step 1: Start Chrome with remote debugging

Chrome must be started with special flags to allow automation. Run in PowerShell:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
```

> [!NOTE]
> **Chrome path may differ.** If Chrome was installed only for your user, replace the path:
>
> ```powershell
> & "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
> ```
>
> See [Finding your Chrome path](#finding-your-chrome-path) below if the command fails.

Verify it's working:

```powershell
Invoke-WebRequest -Uri 'http://localhost:9222/json/version' -UseBasicParsing
```

You should see a JSON response. If you get a connection error, make sure you included the `--user-data-dir` flag.

### Step 2: Set up the CDP proxy

Docker containers can't connect directly to Chrome on your host. The CDP proxy solves this.

Create a folder (e.g., `C:\sap-mcp\`) and add these two files:

**docker-compose.yml**

```yaml
services:
    cdp-proxy:
        image: nginx:alpine
        ports:
            - '9223:9222'
        volumes:
            - ./nginx-cdp-proxy.conf:/etc/nginx/conf.d/default.conf:ro
        restart: unless-stopped

networks:
    default:
        name: sap-mcp-network
```

**nginx-cdp-proxy.conf**

```nginx
server {
    listen 9222;

    resolver 127.0.0.11 valid=30s;

    location / {
        set $backend "host.docker.internal:9222";
        proxy_pass http://$backend;
        proxy_set_header Host localhost;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;

        sub_filter 'ws://localhost/' 'ws://host.docker.internal:9223/';
        sub_filter 'ws://localhost:9222/' 'ws://host.docker.internal:9223/';
        sub_filter_once off;
        sub_filter_types application/json;
    }
}
```

Then start the proxy:

```powershell
cd C:\sap-mcp
docker compose up -d
```

Verify it's running:

```powershell
docker ps --filter "name=cdp-proxy" --format "table {{.Names}}\t{{.Status}}"
```

### Step 3: Configure your MCP client

**Required:** `systems.json` with your SAP credentials (see [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) and [Configuration Reference](#configuration-reference) for the default path per OS). All other env variables are optional. See [Configuration Reference](#configuration-reference) for the full list.

> [!NOTE]
> `GITHUB_PAT` is only needed for `log_feedback` (creates GitHub issues) or abapGit operations. Remove the `-e GITHUB_PAT=...` line if you don't need these features.

Choose **one** of the following options based on which Claude client you use.

#### Option A: Claude Desktop

Open `%APPDATA%\Claude\claude_desktop_config.json` and add:

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "docker",
            "args": [
                "run",
                "-i",
                "--rm",
                "--network",
                "sap-mcp-network",
                "-e",
                "BROWSER_MODE=connect",
                "-e",
                "CDP_URL=http://cdp-proxy:9222",
                "-e",
                "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "-v",
                "~/.config/sap-mcp/systems.json:/home/appuser/.config/sap-mcp/systems.json:ro",
                "-e",
                "GITHUB_PAT=your_github_pat",
                "ghcr.io/hochfrequenz/sapgui.mcp:latest"
            ]
        }
    }
}
```

Replace:

- `your-sap-server` with your SAP server hostname
- `your_github_pat` with a [GitHub Personal Access Token](https://github.com/settings/tokens) (optional - see note above)
- SAP credentials (user, password, mandant, language) are read from `~/.config/sap-mcp/systems.json` which is volume-mounted into the container

#### Option B: Claude Code

Add to `.mcp.json` in your project root:

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "docker",
            "args": [
                "run",
                "-i",
                "--rm",
                "--network",
                "sap-mcp-network",
                "-e",
                "BROWSER_MODE=connect",
                "-e",
                "CDP_URL=http://cdp-proxy:9222",
                "-e",
                "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "-v",
                "~/.config/sap-mcp/systems.json:/home/appuser/.config/sap-mcp/systems.json:ro",
                "-e",
                "GITHUB_PAT=your_github_pat",
                "ghcr.io/hochfrequenz/sapgui.mcp:latest"
            ]
        }
    }
}
```

### Step 4: Start chatting

Restart Claude Desktop/Code and try:

- "Log me into SAP"
- "Run transaction VA01"
- "Take a screenshot"

If it tries e.g. to start a dev-browser or _install_ Chrome, cancel and try to be explicit "log me into sap using the sap web gui mcp".
If Docker Desktop isn't running or you're not logged in (`docker login ghcr.io`) and never pulled the image, you might get a nonspecific error "1 MCP server failed · /mcp".

> [!WARNING]
> You need to be logged in to the GitHub Container Registry (`ghcr.io`). Being logged in to Docker (for example Docker Hub) alone is _not_ sufficient; you must run `docker login ghcr.io`.

Try pulling manually if you run into errors:

```powershell
docker pull ghcr.io/hochfrequenz/sapgui.mcp:latest
```

If the containers started but Chrome (in browser automation mode with CDP enabled) is missing, Claude will likely understand how to login but fail on the first tool call.

</details>

<details>
<summary><strong>🛠️ Development Setup (from source)</strong></summary>
<br>

For contributors who want to run from source.

### Prerequisites

- Python 3.11+
- Chrome browser with remote debugging (see Step 1 above)

### Clone and install

```bash
git clone https://github.com/Hochfrequenz/sapgui.mcp.git
cd sapgui.mcp
pip install -e ".[dev]"
playwright install chromium
```

### Run tests

```bash
tox -e unit_tests   # unit tests only
tox -e linting      # code quality
tox -e formatting   # check formatting
```

### Run the MCP server locally

```bash
# Set environment variables
$env:SAP_URL = "https://your-sap-server/sap/bc/gui/sap/its/webgui"
$env:BROWSER_MODE = "connect"
$env:CDP_URL = "http://localhost:9222"

# Start the server
run-sapgui-mcp-server
```

### Configure your MCP client

**Required:** `systems.json` with your SAP credentials (see [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) and [Configuration Reference](#configuration-reference) for the default path per OS). All other env variables are optional.

> [!NOTE]
> `GITHUB_PAT` is only needed for `log_feedback` (creates GitHub issues) or abapGit operations. Remove it if you don't need these features.

When running Python directly (not in Docker), you don't need the CDP proxy - Python can connect to Chrome on localhost.

#### Claude Desktop

Add to `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`, macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/your/venv/Scripts/run-sapgui-mcp-server.exe",
            "args": [],
            "env": {
                "BROWSER_MODE": "connect",
                "CDP_URL": "http://localhost:9222",
                "GITHUB_PAT": "your_github_pat"
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
        "sap-webgui": {
            "command": "C:/path/to/your/venv/Scripts/run-sapgui-mcp-server.exe",
            "args": [],
            "env": {
                "BROWSER_MODE": "connect",
                "CDP_URL": "http://localhost:9222",
                "GITHUB_PAT": "your_github_pat"
            }
        }
    }
}
```

</details>

## Available Tools

### Core SAP Tools

| Tool | Description |
| --- | --- |
| `sap_login` | Log into SAP (WebGUI: opens login page; Desktop: connects via SAP Logon) |
| `sap_transaction` | Enter and execute a transaction code |
| `sap_list_connections` | List configured SAP systems and SAP Logon entries |
| `sap_screenshot` | Take a screenshot of the current SAP screen |
| `sap_keepalive_start` | Prevent session timeout (pings every 5 minutes) |
| `sap_keepalive_stop` | Stop the keepalive task |
| `sap_get_capabilities` | Query which features the current backend supports |

### Screen Interaction Tools

| Tool | Description |
| --- | --- |
| `sap_get_screen_text` | Get all readable text from the current screen |
| `sap_get_screen_info` | Get technical screen info (program, dynpro, title) |
| `sap_get_form_fields` | Get all form fields and their current values |
| `sap_fill_form` | Fill multiple form fields at once |
| `sap_set_field` | Set a single field by selector or label |
| `sap_set_checkbox` | Toggle a checkbox |
| `sap_set_radio_button` | Select a radio button |
| `sap_click_button` | Click a button by label text |
| `sap_select_tab` | Select a tab by label text |
| `sap_select_dropdown` | Select a dropdown option by label and value |
| `sap_press_key` | Send keyboard shortcuts (F-keys, Ctrl+S, etc.) |
| `sap_close_popup` | Close modal popups and dialogs |
| `sap_read_status_bar` | Read status bar messages |
| `sap_read_table` | Read data from ALV grids and tables |
| `sap_click_table_cell` | Click a cell in an ALV grid table |
| `sap_session_status` | Check SAP session status |
| `sap_lookup_fields` | Look up known field selectors for a transaction |
| `sap_discover_fields` | Discover input fields on current screen |
| `sap_discover_buttons` | Discover available buttons on current screen |
| `sap_get_shortcuts` | Get available keyboard shortcuts |

### Transaction-Specific Tools

| Tool | Description |
| --- | --- |
| `sap_se09_lookup` | Search transports (SE09/SE10) |
| `sap_se11_lookup` | Look up Data Dictionary objects (tables, structures, data elements) |
| `sap_se16_query` | Query table contents via SE16/SE16N |
| `sap_se24_lookup` | Look up ABAP class definitions |
| `sap_se24_edit` | Edit ABAP class source code |
| `sap_se37_lookup` | Look up function module definitions |
| `sap_se37_edit` | Edit function module source code |
| `sap_se38_edit` | Edit ABAP report source code |
| `sap_se93_lookup` | Look up transaction code definitions |
| `sap_slg1_lookup` | Query application logs (SLG1) |
| `sap_sm30_lookup` | Display/maintain table views (SM30) |
| `sap_sm37_lookup` | Search background jobs (SM37) |
| `sap_spro_search` | Search customizing activities (SPRO) |
| `sap_st22_lookup` | Look up ABAP short dumps |
| `sap_quick_report` | Run SAP Quick Reports (SQVI) |

### Session Management Tools (Desktop backend)

| Tool | Description |
| --- | --- |
| `sap_session_list` | List all active SAP sessions |
| `sap_session_bind` | Bind to a specific SAP session (for parallel agents) |
| `sap_session_release` | Release a bound session |
| `sap_session_close` | Close an SAP session |
| `sap_session_reset_to_primary` | Reset to primary session |

### Catalog Search Tools (offline, no SAP connection needed)

| Tool | Description |
| --- | --- |
| `search_transactions` | Search bundled transaction catalog by keyword |
| `search_tables` | Search bundled SAP table catalog by name or field |
| `search_classes` | Search bundled ABAP class catalog |
| `search_function_modules` | Search bundled function module catalog |

### abapGit Tools

| Tool | Description |
| --- | --- |
| `sap_abapgit_list_repos` | List all registered abapGit repos (names, Git URLs, packages, branches, last pull) |
| `sap_abapgit_pull` | Pull a registered abapGit repo (uses the `Z_ABAPGIT_PULL_MCP_SHORTCUT` SAP-side report) |
| `sap_read_se38_source` | Read ABAP report source code via SE38 |

`sap_abapgit_pull` and `sap_abapgit_list_repos` require the [`Z_ABAPGIT_PULL_MCP_SHORTCUT`](https://github.com/Hochfrequenz/Z_ABAPGIT_PULL_MCP_SHORTCUT) ABAP report installed on the SAP system.
The report calls the abapGit ABAP API directly instead of automating the UI, which makes pulls much more reliable.
If the tools fail with `"transaction not found"` or similar, install the report from that repo first.
For private git repositories, set `GITHUB_PAT` or `ABAPGIT_PAT` (the latter overrides the former) in the MCP server's environment - without a PAT, pulls from private repos will fail.

### Desktop COM Tools (Desktop backend only)

| Tool | Description |
| --- | --- |
| `sap_com_snapshot` | Dump the SAP GUI control tree (object hierarchy) |
| `sap_com_evaluate` | Execute raw COM operations on SAP GUI objects |
| `sap_run_script` | 🚀 Run a sandboxed Python script against the SAP GUI COM API - loops, branches, and bulk reads in one call instead of many. Great token saver! |
| `sap_tree_context_menu` | Open and interact with tree context menus |
| `sap_breakpoint_set` | Set an ABAP breakpoint — ask the human first; there's no tool to drive the resulting debugger, only a human at the SAP GUI can dismiss it |
| `sap_breakpoint_delete` | Delete an ABAP breakpoint |
| `sap_breakpoint_list` | List active ABAP breakpoints |

### Logging Tools

| Tool | Description |
| --- | --- |
| `log_intent` | Log what you're doing for accountability |
| `log_feedback` | Report issues (creates GitHub issues if `GITHUB_PAT` is set) |

### Browser Tools (WebGUI backend only)

Low-level browser escape hatches available when using the WebGUI backend:

| Tool | Description |
| --- | --- |
| `browser_screenshot` | Capture a PNG of the current SAP Web GUI view |
| `browser_snapshot` | Get the accessibility tree of the current page |
| `browser_click` | Click an element by selector |
| `browser_fill` | Fill an input field |
| `browser_keyboard` | Send keyboard input |
| `browser_navigate` | Navigate to a URL |
| `browser_evaluate` | Execute JavaScript on the page |
| `browser_wait` | Wait for an element or a timeout |
| `browser_get_html` | Get HTML content of the page or an element |
| `browser_select_option` | Select a dropdown option |

The SAP-specific tools above handle most interactions; reach for the browser tools when you need pixel-level control.

## Configuration Reference

### SAP Credentials (via `systems.json`)

SAP credentials (user, password, client, language, host) are configured in `systems.json` (or `systems.yaml`), **not** via environment variables. See [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) for the file format. Override the config file path with `SAP_CONFIG_FILE`.

| OS          | Default path                                 |
| ----------- | -------------------------------------------- |
| Windows     | `%USERPROFILE%\.config\sap-mcp\systems.json` |
| macOS/Linux | `~/.config/sap-mcp/systems.json`             |

### Environment Variables (server-specific)

| Variable             | Required                    | Description                                                            | Default                      |
| -------------------- | --------------------------- | ---------------------------------------------------------------------- | ---------------------------- |
| `BACKEND_TYPE`       | No                          | `webgui` (browser automation) or `desktop` (SAP GUI COM, Windows only) | `webgui`                     |
| `SAP_URL`            | No                          | Override WebGUI URL (default: derived from `host` in systems.json)     | `""`                         |
| `SAP_CONFIG_FILE`    | No                          | Path to systems.json (see table above for default per OS)              | (see above)                  |
| `BROWSER_MODE`       | No                          | `connect` (existing Chrome) or `launch` (Playwright). WebGUI only.     | `connect`                    |
| `BROWSER_TYPE`       | No                          | `chromium`, `firefox`, or `webkit`. WebGUI only.                       | `chromium`                   |
| `BROWSER_HEADLESS`   | No                          | Run browser in headless mode. WebGUI only.                             | `false`                      |
| `CDP_URL`            | When `BROWSER_MODE=connect` | Chrome DevTools Protocol URL. WebGUI only.                             | `http://localhost:9222`      |
| `CHROME_PATH`        | No                          | Explicit path to Chrome binary. If empty, auto-detected. WebGUI only.  | `""` (auto-detect)           |
| `CHROME_USER_DATA_DIR` | No                        | User data directory for auto-launched Chrome. WebGUI only.             | `<tempdir>/chrome-debug`     |
| `COM_MIN_INTERVAL_MS` | No                         | Minimum ms between COM calls (prevents overload). Desktop only.        | `100`                        |
| `GITHUB_PAT`         | No                          | GitHub PAT for `log_feedback` issues and abapGit auth                  | -                            |
| `GITHUB_USER`        | No                          | GitHub username for abapGit (falls back to `x-access-token`)           | -                            |
| `GITHUB_REPO`        | No                          | Repository for feedback issues                                         | `Hochfrequenz/sapgui.mcp` |
| `ABAPGIT_PAT`        | No                          | Separate PAT for abapGit (overrides `GITHUB_PAT` if set)               | -                            |
| `PAPERTRAIL_HOST`    | No                          | Papertrail syslog host (empty to disable)                              | `""` (off)                   |
| `PAPERTRAIL_PORT`    | No                          | Papertrail syslog port                                                 | `0` (off)                    |
| `LOG_FORMAT`         | No                          | Set to `json` for JSON log output                                      | `""` (human-readable)        |
| `LOG_LEVEL`          | No                          | `DEBUG`, `INFO`, `WARNING`, or `ERROR`                                 | `INFO`                       |

## Logging

The server logs to **stdout** by default using a structured text format. Set `LOG_FORMAT=json` for machine-readable JSON output.

### Papertrail (remote logging)

Remote logging to [Papertrail](https://www.papertrail.com/) is **disabled by default**. No telemetry is sent unless you explicitly opt in.

To enable it, set both `PAPERTRAIL_HOST` and `PAPERTRAIL_PORT` in your `.env` file or environment:

```
PAPERTRAIL_HOST=logs.example.com
PAPERTRAIL_PORT=12345
```

When enabled, tool call names, SAP hostnames, and operational metadata are sent to the configured Papertrail endpoint for monitoring and debugging. No SAP credentials or business data are transmitted.

Each release publishes binaries for Windows and macOS:

| Binary | Papertrail default | Intended audience |
|---|---|---|
| `sapgui_mcp_windows.exe` | **off** - no defaults bundled | Public / external users |
| `sapgui_mcp_windows_with_remote_logging.exe` | Hochfrequenz endpoint baked in at build time | Hochfrequenz-internal use |
| `sapgui_mcp_macos_arm64` | **off** - no defaults bundled | Public / macOS (Apple Silicon) users |

Both binaries honour user overrides via `.env` or environment variables.

## Troubleshooting

### Finding your Chrome path

The Chrome startup commands in this guide use `C:\Program Files\Google\Chrome\Application\chrome.exe` - the default path for a **system-wide** Chrome installation. If you get an error like _"The system cannot find the path specified"_, Chrome is likely installed in a different location.

**Common Chrome paths on Windows:**

| Installation type       | Path                                                                     |
| ----------------------- | ------------------------------------------------------------------------ |
| System-wide (all users) | `C:\Program Files\Google\Chrome\Application\chrome.exe`                  |
| Per-user (current user) | `C:\Users\<YourName>\AppData\Local\Google\Chrome\Application\chrome.exe` |

**How to find your Chrome path (step by step):**

1. Find your Chrome shortcut (on your desktop or in the Start menu)
2. **Right-click** the Chrome shortcut → click **Properties**
3. In the Properties window, look at the **Target** field
4. Copy the path from that field (everything before any `--` flags)

For example, if the Target field shows:

```
"C:\Users\JaneDoe\AppData\Local\Google\Chrome\Application\chrome.exe"
```

Then your Chrome startup command is:

```powershell
& "C:\Users\JaneDoe\AppData\Local\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
```

**Quick check in PowerShell** - this command finds Chrome automatically:

```powershell
Get-Item "C:\Program Files\Google\Chrome\Application\chrome.exe","$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
```

### "network sap-mcp-network not found"

The CDP proxy isn't running or was never started. Start it:

```powershell
cd C:\sap-mcp
docker compose up -d
```

### Chrome connection errors

1. Make sure Chrome is running with `--remote-debugging-port=9222`
2. Make sure you used `--user-data-dir` (required, otherwise Chrome joins existing instance)
3. Verify with: `Invoke-WebRequest -Uri 'http://localhost:9222/json/version' -UseBasicParsing`

### "Cannot connect to CDP proxy"

Check if the proxy is running:

```powershell
docker ps | Select-String cdp-proxy
```

Check proxy logs:

```powershell
docker logs sap-mcp-cdp-proxy-1
```

### SAP login fails

- Check `SAP_URL` is correct and accessible from your browser
- If using auto-login, verify credentials are configured in `systems.json` (see [Configuration Reference](#configuration-reference))
- **Desktop backend:** Make sure the `connection_name` field in `systems.json` matches the SAP Logon pad **description** exactly (the bold text, not the SID). Open SAP Logon and compare.
- Try logging in manually first to verify credentials

### Transaction input field (OK-Code field) not visible

On first use of SAP Web GUI, the transaction input field (called "OK-Code field" in SAP) may be hidden. The MCP server tries to enable it automatically, but if that fails, you can enable it manually:

1. Click the gear icon in the toolbar ("GUI-Aktionen und -Einstellungen" / "GUI Actions and Settings")
2. Select "Einstellungen..." / "Settings..."
3. Enable "OK-Code-Feld anzeigen" (Show OK-Code Field)

![SAP Web GUI Settings - Enable OK-Code Field](https://github.com/user-attachments/assets/9ec83ed4-28fd-4712-af88-f90d515ccd7a)

This is a one-time setting that is saved for subsequent logins.

### Tools timeout or hang

SAP Web GUI can be slow. If operations timeout:

1. Check the Chrome window - is SAP responding?
2. Try `sap_keepalive_start` to prevent session timeouts
3. Check Docker container logs: `docker logs <container-id>`

### "Port 9223 already in use"

Another service is using port 9223. Stop it or change the port in docker-compose.yml:

```yaml
ports:
    - '9224:9222' # Use 9224 instead
```

### Docker image pull fails

If you see "unauthorized" or "access denied" when pulling the image, you need to authenticate with GitHub Container Registry.

**Step 1: Create a GitHub Personal Access Token**

1. Go to [GitHub Token Settings](https://github.com/settings/tokens)
2. Click "Generate new token" → **"Generate new token (classic)"**
    > You must use "classic" tokens. Fine-grained tokens don't support container registry access.
3. Give it a name like "Docker GHCR read"
4. Set expiration: Choose "Custom" and set to 1 year. You'll need to create a new token and re-login when it expires
5. Select scope: `read:packages` (only this one is needed)
6. Click "Generate token"
7. **Copy the token immediately** (starts with `ghp_`) - you won't see it again!

**Step 2: Login to GitHub Container Registry**

```powershell
docker login ghcr.io -u YOUR_GITHUB_USERNAME
```

When prompted for password:

- Paste your Personal Access Token (not your GitHub password)
- The password won't show as you type - this is normal
- In PowerShell, **right-click to paste** (Ctrl+V may not work)

You should see: `Login Succeeded`

**Step 3: Pull the image**

```powershell
docker pull ghcr.io/hochfrequenz/sapgui.mcp:latest
```

> [!NOTE]
> You only need to do this once per machine. Docker stores your credentials.

**Still having issues?**

- Verify the token starts with `ghp_`
- Try: `docker logout ghcr.io` then repeat Step 2

## Architecture

The server supports two backends. Choose one via `BACKEND_TYPE`.

**WebGUI Backend** (`BACKEND_TYPE=webgui`, default):

```mermaid
graph BT
    Claude["Claude Desktop / Claude Code"]
    MCP["MCP Server (sapguimcp)\nPlaywright for browser automation\nSAP-specific tools"]
    CDP["CDP Proxy (nginx)\nOnly needed for Docker"]
    Chrome["Chrome\nSAP Web GUI loaded\nPersistent session"]

    Claude -- "MCP (stdio)" --> MCP
    MCP -- "HTTP / WebSocket" --> CDP
    CDP -- "CDP (Chrome DevTools Protocol)" --> Chrome
```

**Desktop Backend** (`BACKEND_TYPE=desktop`, Windows only):

```mermaid
graph BT
    Claude["Claude Desktop / Claude Code"]
    MCP["MCP Server (sapguimcp)\nDesktop backend with COM thread\nSAP-specific tools"]
    SAP["SAP GUI for Windows\nCOM Scripting API\nPersistent session(s)"]

    Claude -- "MCP (stdio)" --> MCP
    MCP -- "COM (pywin32)" --> SAP
```

## Related projects

This server is part of a small ecosystem of SAP + AI tooling:

- **[`aibap.mcp`](https://github.com/Hochfrequenz/aibap.mcp)** - complementary MCP server that talks to SAP via the ADT REST API (read/write source, activate, syntax-check, run unit tests, manage transports). Where `sapgui.mcp` drives SAP through its UI, `aibap.mcp` talks directly to the ABAP Development Tools HTTP API. The two are designed to coexist and share `~/.config/sap-mcp/systems.json`.
- **[`AIBAP_TEMPLATE_REPOSITORY`](https://github.com/Hochfrequenz/AIBAP_TEMPLATE_REPOSITORY)** - GitHub template for AI-driven ABAP vibe-coding projects. Documents the two-agent pattern (dev via `aibap.mcp`, test / documentation / screenshots via `sapgui.mcp`) end-to-end.
- **[`Z_ABAPGIT_PULL_MCP_SHORTCUT`](https://github.com/Hochfrequenz/Z_ABAPGIT_PULL_MCP_SHORTCUT)** - SAP-side ABAP report that `sap_abapgit_pull` calls to pull abapGit repos through the ABAP API. Install it on any SAP system where you want the abapGit pull tools to work.
- **[`sap-mcp-config`](https://github.com/Hochfrequenz/sap-mcp-config)** - shared config schema for `systems.json`, consumed by both `sapgui.mcp` (Python) and `aibap.mcp` (Go).

**Hochfrequenz colleagues:** internal setup docs - including combined `.mcp.json` / `opencode.json` examples that register both MCPs together in one project - live at <https://brain.hochfrequenz.de/books/ki-tools-bei-hochfrequenz/chapter/sap-mcps>.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and coding standards.
