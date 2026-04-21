# SAP MCP Server

[![Unittests](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Unittests/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)
[![Coverage](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Coverage/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)
[![Linting](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Linting/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)
[![Formatting](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Formatting/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)

An MCP (Model Context Protocol) server for SAP automation.
Control SAP through Claude Desktop, Claude Code, or [opencode](https://opencode.ai) — via **SAP GUI desktop** or **SAP Web GUI** (browser).
Because it drives the real SAP UI (not a headless API), it is especially well-suited for **end-to-end testing**, **visual validation**, and **capturing screenshots for documentation** — tasks a pure REST-API client cannot do.
The MCP works with both SAP R/3 and S/4 (because some might even say "they are the same system" with just some different names and labels).

> [!TIP]
> **Pairs with [`mcp-server-abap`](https://github.com/Hochfrequenz/mcp-server-abap).** The two servers complement each other in a two-agent vibe-coding setup: one agent writes ABAP via `mcp-server-abap` (ADT REST), while a second agent drives this server to test the generated code in the real SAP UI, capture screenshots, and report failures back. See [`AIBAP_TEMPLATE_REPOSITORY`](https://github.com/Hochfrequenz/AIBAP_TEMPLATE_REPOSITORY) for a template that documents this workflow end-to-end.

> **Developer?** See [ARCHITECTURE.md](ARCHITECTURE.md) for how the codebase is structured, request flow diagrams, and how to add new transaction tools.

## Setup

Choose one of these three approaches:

**Where to register the MCP server:**

- **Claude Code** — add to `.mcp.json` in your project root (per-project config)
- **Claude Desktop** — add to `claude_desktop_config.json` (global config, path varies by OS — shown in each section below)
- **[opencode](https://opencode.ai)** — add to `opencode.json` in your project root. opencode's schema differs slightly from Claude's (`"mcp"` instead of `"mcpServers"`, plus `"type": "local"`, `"command"` as an array, and `"environment"` instead of `"env"`) — see [opencode's MCP docs](https://opencode.ai/docs/mcp-servers) and adapt the Claude Code snippets below.

All three setup approaches below show Claude Desktop and Claude Code snippets; opencode users translate the schema as described.

> [!WARNING]
> **Special characters in passwords:** If your SAP password contains `"` or `\` characters, you must escape them in the JSON config files: `"` becomes `\"` and `\` becomes `\\`. For example, `pass"word` becomes `"pass\"word"` and `do\main` becomes `"do\\main"`. Unescaped special characters will silently break the JSON and the MCP server will fail to start.

> [!TIP]
> **Windows file extensions:** If file extensions are hidden in Windows Explorer, creating `.mcp.json` via right-click → New → Text File will produce `.mcp.json.txt` (or `.mcp.json.json` if you rename). Make sure "File name extensions" is checked in Explorer's View tab, then rename the file.

<details>
<summary><strong>📦 Standalone Executable (recommended — no Docker, no Python)</strong></summary>
<br>

Download `sapwebgui_mcp_windows_<version>.exe` from
[GitHub Releases](https://github.com/Hochfrequenz/sapwebgui.mcp/releases/latest).

Choose a backend:

|              | Desktop Backend (SAP GUI)            | WebGUI Backend (Browser)                     |
| ------------ | ------------------------------------ | -------------------------------------------- |
| **Platform** | Windows only                         | Windows, macOS, Linux                        |
| **Requires** | SAP GUI for Windows                  | Chrome browser                               |
| **Speed**    | Faster (works directly with SAP GUI) | Slower (works through a web browser)         |
| **Setup**    | Simpler (just SAP GUI + this tool)   | More steps (also needs Chrome browser setup) |

### Option A: Desktop Backend (SAP GUI) — recommended for Windows users

Automates SAP GUI directly — no browser needed. Windows only.
Uses [sapsucker](https://github.com/Hochfrequenz/sapsucker) for typed SAP GUI Scripting access.

**Prerequisites:**

- SAP GUI for Windows installed (standard path — the server finds it automatically via Windows registry)
- SAP GUI Scripting enabled (one-time setup, see below)

<details>
<summary>Enable SAP GUI Scripting (one-time)</summary>

**Server side** (requires admin/basis team):

- Transaction `RZ11` → parameter `sapgui/user_scripting` → set to `TRUE`
- Dynamic parameter — no server restart needed, but users must re-login (close and reopen SAP GUI)

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

#### Claude Desktop

Add to `claude_desktop_config.json`. To open the file: press **Win+R**, type `%APPDATA%\Claude`, press Enter. If `claude_desktop_config.json` does not exist, create a new text file with that exact name (make sure it ends in `.json`, not `.json.txt`).

> [!TIP]
> After downloading the `.exe`, note the full path. For example, if you saved `sapwebgui_mcp_windows_1.5.0.exe` to your Downloads folder, the path is `C:/Users/YourName/Downloads/sapwebgui_mcp_windows_1.5.0.exe`. Always use forward slashes (`/`) in the JSON, not backslashes (`\`).

**Step 1:** Create the SAP config file (shared with [mcp-server-abap](https://github.com/Hochfrequenz/mcp-server-abap) — configure once, use everywhere).

On **Windows**, open Windows Explorer and paste this into the address bar:

```
%USERPROFILE%\.config\sap-mcp
```

Create the folder if it doesn't exist, then create a file called `systems.json` inside it. On **macOS/Linux**, the path is `~/.config/sap-mcp/systems.json`.

There are two distinct identifiers per system — don't mix them up:

| Concept | Example | Where it's used |
| --- | --- | --- |
| **System key** (dictionary key) | `"dev"`, `"qa"` | `sap_login(system_key="qa")` — selects which system to log into |
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

See [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) for the full config format reference (JSON and YAML supported).

**Step 2:** Add to `claude_desktop_config.json`:

```json
{
    "mcpServers": {
        "sap-desktop": {
            "command": "C:/path/to/sapwebgui_mcp_windows_<version>.exe",
            "env": {
                "BACKEND_TYPE": "desktop"
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
            "command": "C:/path/to/sapwebgui_mcp_windows_<version>.exe",
            "env": {
                "BACKEND_TYPE": "desktop"
            }
        }
    }
}
```

#### Multi-system access (desktop backend only)

Multi-system support is built into `systems.json` — add multiple systems and the LLM can switch between them:

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

> **Getting started:** Save the config file, then restart Claude Desktop. Try asking: _"Log me into SAP"_ or _"Run transaction SE16"_. SAP GUI will open automatically if it is not already running.

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

#### Step 2: Create `systems.json`

Create the SAP config file if you haven't already (Windows: `%USERPROFILE%\.config\sap-mcp\systems.json`, macOS/Linux: `~/.config/sap-mcp/systems.json`). See [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) for details.

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

> The WebGUI URL is derived automatically from `host` as `{host}/sap/bc/gui/sap/its/webgui`. If your SAP system uses a non-standard WebGUI path, set `SAP_URL` in the MCP config below.

#### Step 3: Configure your MCP client

##### Claude Desktop

Add to `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`, macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/sapwebgui_mcp_windows_<version>.exe",
            "env": {
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
            "command": "C:/path/to/sapwebgui_mcp_windows_<version>.exe",
            "env": {
                "GITHUB_PAT": "your_github_pat"
            }
        }
    }
}
```

No Docker, no CDP proxy, no Python required.

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
                "ghcr.io/hochfrequenz/sapwebgui.mcp:latest"
            ]
        }
    }
}
```

Replace:

- `your-sap-server` with your SAP server hostname
- `your_github_pat` with a [GitHub Personal Access Token](https://github.com/settings/tokens) (optional — see note above)
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
                "ghcr.io/hochfrequenz/sapwebgui.mcp:latest"
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
docker pull ghcr.io/hochfrequenz/sapwebgui.mcp:latest
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
git clone https://github.com/Hochfrequenz/sapwebgui.mcp.git
cd sapwebgui.mcp
pip install -e ".[dev]"
playwright install chromium
```

### Run tests

```bash
tox -e py312        # unit tests
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
run-sapwebgui-mcp-server
```

### Configure your MCP client

**Required:** `systems.json` with your SAP credentials (see [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) and [Configuration Reference](#configuration-reference) for the default path per OS). All other env variables are optional.

> `GITHUB_PAT` is only needed for `log_feedback` (creates GitHub issues) or abapGit operations. Remove it if you don't need these features.

When running Python directly (not in Docker), you don't need the CDP proxy — Python can connect to Chrome on localhost.

#### Claude Desktop

Add to `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`, macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/your/venv/Scripts/run-sapwebgui-mcp-server.exe",
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
            "command": "C:/path/to/your/venv/Scripts/run-sapwebgui-mcp-server.exe",
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

### SAP Tools

| Tool                     | Description                                                                            |
| ------------------------ | -------------------------------------------------------------------------------------- |
| `sap_login`              | Logs into SAP (WebGUI: opens login page; Desktop: connects via SAP Logon)              |
| `sap_transaction`        | Enters and executes a transaction code                                                 |
| `sap_keepalive_start`    | Prevents session timeout (pings every 5 minutes)                                       |
| `sap_keepalive_stop`     | Stops the keepalive task                                                               |
| `sap_abapgit_list_repos` | List all registered abapGit repos (names, Git URLs, packages, branches, last pull)    |
| `sap_abapgit_pull`       | Pull a registered abapGit repo (uses the `Z_ABAPGIT_PULL_MCP_SHORTCUT` SAP-side report) |
| `log_intent`             | Log what you're doing for accountability                                               |
| `log_feedback`           | Report issues (creates GitHub issues if `GITHUB_PAT` is set)                           |

#### abapGit integration

`sap_abapgit_pull` and `sap_abapgit_list_repos` require the [`Z_ABAPGIT_PULL_MCP_SHORTCUT`](https://github.com/Hochfrequenz/Z_ABAPGIT_PULL_MCP_SHORTCUT) ABAP report installed on the SAP system.
The report calls the abapGit ABAP API directly instead of automating the UI, which makes pulls much more reliable.
If the tools fail with `"transaction not found"` or similar, install the report from that repo first.
For private git repositories, set `GITHUB_PAT` or `ABAPGIT_PAT` (the latter overrides the former) in the MCP server's environment — without a PAT, pulls from private repos will fail.

### Browser Tools (WebGUI only)

Low-level browser escape hatches available when using the WebGUI backend:

- **`browser_screenshot`** — capture a PNG of the current SAP Web GUI view. Useful for documentation, visual validation, and showing reviewers what a workflow actually looks like on screen.
- **`browser_snapshot`**, **`browser_click`**, **`browser_fill`**, **`browser_keyboard`**, etc. — fallbacks for SAP screens the typed SAP tools above do not yet cover.

The SAP-specific tools above handle most interactions; reach for the browser tools when you need pixel-level control.

## Configuration Reference

### SAP Credentials (via `systems.json`)

SAP credentials (user, password, client, language, host) are configured in `systems.json` (or `systems.yaml`), **not** via environment variables. See [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) for the file format. Override the config file path with `SAP_CONFIG_FILE`.

| OS          | Default path                                 |
| ----------- | -------------------------------------------- |
| Windows     | `%USERPROFILE%\.config\sap-mcp\systems.json` |
| macOS/Linux | `~/.config/sap-mcp/systems.json`             |

### Environment Variables (server-specific)

| Variable           | Required                    | Description                                                            | Default                      |
| ------------------ | --------------------------- | ---------------------------------------------------------------------- | ---------------------------- |
| `BACKEND_TYPE`     | No                          | `webgui` (browser automation) or `desktop` (SAP GUI COM, Windows only) | `webgui`                     |
| `SAP_URL`          | No                          | Override WebGUI URL (default: derived from `host` in systems.json)     | `""`                         |
| `SAP_CONFIG_FILE`  | No                          | Path to systems.json (see table above for default per OS)              | (see above)                  |
| `BROWSER_MODE`     | No                          | `connect` (existing Chrome) or `launch` (Playwright). WebGUI only.     | `connect`                    |
| `BROWSER_TYPE`     | No                          | `chromium`, `firefox`, or `webkit`. WebGUI only.                       | `chromium`                   |
| `BROWSER_HEADLESS` | No                          | Run browser in headless mode. WebGUI only.                             | `false`                      |
| `CDP_URL`          | When `BROWSER_MODE=connect` | Chrome DevTools Protocol URL. WebGUI only.                             | `http://localhost:9222`      |
| `GITHUB_PAT`       | No                          | GitHub PAT for `log_feedback` issues and abapGit auth                  | —                            |
| `GITHUB_USER`      | No                          | GitHub username for abapGit (falls back to `x-access-token`)           | —                            |
| `GITHUB_REPO`      | No                          | Repository for feedback issues                                         | `Hochfrequenz/sapwebgui.mcp` |
| `ABAPGIT_PAT`      | No                          | Separate PAT for abapGit (overrides `GITHUB_PAT` if set)               | —                            |
| `PAPERTRAIL_HOST`  | No                          | Papertrail syslog host (empty to disable)                              | `""` (off) <sup>1</sup>      |
| `PAPERTRAIL_PORT`  | No                          | Papertrail syslog port                                                 | `0` (off) <sup>1</sup>       |
| `LOG_FORMAT`       | No                          | Set to `json` for JSON log output                                      | `""` (human-readable)        |
| `LOG_LEVEL`        | No                          | `DEBUG`, `INFO`, `WARNING`, or `ERROR`                                 | `INFO`                       |

<sup>1</sup> Two Windows binaries are published per release. `sapwebgui_mcp_windows.exe` has remote logging **off by default** — this is the variant external users want. `sapwebgui_mcp_windows_with_remote_logging.exe` bundles Papertrail defaults at build time and streams logs to Hochfrequenz's log collector. Either binary can be overridden by your own `.env` / environment variables. See the [Papertrail section](#papertrail-remote-logging).

## Logging

The server logs to **stdout** by default using a structured text format. Set `LOG_FORMAT=json` for machine-readable JSON output.

### Papertrail (remote logging)

Remote logging is **off by default** in the public build and when running from source / pip install. Set both `PAPERTRAIL_HOST` and `PAPERTRAIL_PORT` in your `.env` file or environment to opt in.

Each release publishes two Windows binaries:

| Binary | Papertrail default | Intended audience |
|---|---|---|
| `sapwebgui_mcp_windows.exe` | **off** — no defaults bundled | Public / external users |
| `sapwebgui_mcp_windows_with_remote_logging.exe` | Hochfrequenz endpoint baked in at build time | Hochfrequenz-internal use |

Both binaries honour user overrides. To disable remote logging in the `_with_remote_logging` build, create a `.env` next to the executable containing `PAPERTRAIL_HOST=`. To enable it in the public build, set both variables.

## Troubleshooting

### Finding your Chrome path

The Chrome startup commands in this guide use `C:\Program Files\Google\Chrome\Application\chrome.exe` — the default path for a **system-wide** Chrome installation. If you get an error like _"The system cannot find the path specified"_, Chrome is likely installed in a different location.

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

**Quick check in PowerShell** — this command finds Chrome automatically:

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

![SAP Web GUI Settings — Enable OK-Code Field](https://github.com/user-attachments/assets/9ec83ed4-28fd-4712-af88-f90d515ccd7a)

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
docker pull ghcr.io/hochfrequenz/sapwebgui.mcp:latest
```

> **Note:** You only need to do this once per machine. Docker stores your credentials.

**Still having issues?**

- Verify the token starts with `ghp_`
- Try: `docker logout ghcr.io` then repeat Step 2

## Architecture

The server supports two backends. Choose one via `BACKEND_TYPE`.

**WebGUI Backend** (`BACKEND_TYPE=webgui`, default):

```mermaid
graph BT
    Claude["Claude Desktop / Claude Code"]
    MCP["MCP Server (sapwebguimcp)\nPlaywright for browser automation\nSAP-specific tools"]
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
    MCP["MCP Server (sapwebguimcp)\nDesktop backend with COM thread\nSAP-specific tools"]
    SAP["SAP GUI for Windows\nCOM Scripting API\nPersistent session(s)"]

    Claude -- "MCP (stdio)" --> MCP
    MCP -- "COM (pywin32)" --> SAP
```

## Related projects

This server is part of a small ecosystem of SAP + AI tooling:

- **[`mcp-server-abap`](https://github.com/Hochfrequenz/mcp-server-abap)** — complementary MCP server that talks to SAP via the ADT REST API (read/write source, activate, syntax-check, run unit tests, manage transports). Where `sapwebgui.mcp` drives SAP through its UI, `mcp-server-abap` talks directly to the ABAP Development Tools HTTP API. The two are designed to coexist and share `~/.config/sap-mcp/systems.json`.
- **[`AIBAP_TEMPLATE_REPOSITORY`](https://github.com/Hochfrequenz/AIBAP_TEMPLATE_REPOSITORY)** — GitHub template for AI-driven ABAP vibe-coding projects. Documents the two-agent pattern (dev via `mcp-server-abap`, test / documentation / screenshots via `sapwebgui.mcp`) end-to-end.
- **[`Z_ABAPGIT_PULL_MCP_SHORTCUT`](https://github.com/Hochfrequenz/Z_ABAPGIT_PULL_MCP_SHORTCUT)** — SAP-side ABAP report that `sap_abapgit_pull` calls to pull abapGit repos through the ABAP API. Install it on any SAP system where you want the abapGit pull tools to work.
- **[`sap-mcp-config`](https://github.com/Hochfrequenz/sap-mcp-config)** — shared config schema for `systems.json`, consumed by both `sapwebgui.mcp` (Python) and `mcp-server-abap` (Go).

**Hochfrequenz colleagues:** internal setup docs — including combined `.mcp.json` / `opencode.json` examples that register both MCPs together in one project — live at <https://brain.hochfrequenz.de/books/ki-tools-bei-hochfrequenz/chapter/sap-mcps>.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and coding standards.
