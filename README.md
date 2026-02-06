# SAP Web GUI MCP Server

[![Unittests](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Unittests/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)
[![Coverage](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Coverage/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)
[![Linting](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Linting/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)
[![Formatting](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Formatting/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)

An MCP (Model Context Protocol) server for SAP Web GUI browser automation.
Control SAP through Claude Desktop or Claude Code with persistent browser sessions.

## Quick Start (End Users)

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

Choose **one** of the following options based on which Claude client you use.

#### Option A: Claude Desktop

First, create the audit logs directory:

```powershell
mkdir $env:USERPROFILE\sap-audit-logs
```

Then open `%APPDATA%\Claude\claude_desktop_config.json` and add:

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
                "-v",
                "C:/Users/YourUsername/sap-audit-logs:/audit-logs",
                "-e",
                "BROWSER_MODE=connect",
                "-e",
                "CDP_URL=http://cdp-proxy:9222",
                "-e",
                "SAP_URL=https://srvhfuhana.sap.msp.local:44300/sap/bc/gui/sap/its/webgui",
                "-e",
                "SAP_USER=your_username",
                "-e",
                "SAP_PASSWORD=your_password",
                "-e",
                "SAP_MANDANT=100",
                "-e",
                "SAP_LANGUAGE=DE",
                "-e",
                "AUDIT_LOG_DIR=/audit-logs",
                "-e",
                "GITHUB_PAT=your_github_pat",
                "ghcr.io/hochfrequenz/sapwebgui.mcp:latest"
            ]
        }
    }
}
```

Replace:

- `YourUsername` with your Windows username
- `your_username` / `your_password` with your SAP credentials. Make sure the password contains now characters that cause problems (quotes, backslashes...) or address them by properly escaping them (tbh: I don't know how).
- `your_github_pat` with a [GitHub Personal Access Token](https://github.com/settings/tokens) with `repo` scope (optional - only needed for `log_feedback` to create issues)

#### Option B: Claude Code

Add this to the `.mcp.json` configuration file that Claude Code uses for this project (typically in your project root or workspace; JSON config is easier to read and compare than `claude mcp add` with many env vars):

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
                "-v",
                "C:/Users/YourUsername/sap-audit-logs:/audit-logs",
                "-e",
                "BROWSER_MODE=connect",
                "-e",
                "CDP_URL=http://cdp-proxy:9222",
                "-e",
                "SAP_URL=https://srvhfuhana.sap.msp.local:44300/sap/bc/gui/sap/its/webgui",
                "-e",
                "SAP_USER=your_username",
                "-e",
                "SAP_PASSWORD=your_password",
                "-e",
                "SAP_MANDANT=100",
                "-e",
                "SAP_LANGUAGE=DE",
                "-e",
                "AUDIT_LOG_DIR=/audit-logs",
                "-e",
                "GITHUB_PAT=your_github_pat",
                "ghcr.io/hochfrequenz/sapwebgui.mcp:latest"
            ]
        }
    }
}
```

Then start Claude code:

```powershell
claude
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

## Development Setup

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
$env:SAP_URL = "https://srvhfuhana.sap.msp.local:44300/sap/bc/gui/sap/its/webgui"
$env:BROWSER_MODE = "connect"
$env:CDP_URL = "http://localhost:9222"

# Start the server
run-sapwebgui-mcp-server
```

### Configure Claude Desktop for local development

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/your/venv/Scripts/run-sapwebgui-mcp-server.exe",
            "args": [],
            "env": {
                "SAP_URL": "https://srvhfuhana.sap.msp.local:44300/sap/bc/gui/sap/its/webgui",
                "BROWSER_MODE": "connect",
                "CDP_URL": "http://localhost:9222"
            }
        }
    }
}
```

When running Python directly (not in Docker), you don't need the CDP proxy - Python can connect to Chrome on localhost.

## Available Tools

### SAP Tools

| Tool                  | Description                                                  |
| --------------------- | ------------------------------------------------------------ |
| `sap_login`           | Opens SAP Web GUI login page                                 |
| `sap_transaction`     | Enters and executes a transaction code                       |
| `sap_keepalive_start` | Prevents session timeout (pings every 5 minutes)             |
| `sap_keepalive_stop`  | Stops the keepalive task                                     |
| `log_intent`          | Log what you're doing for audit trail                        |
| `log_feedback`        | Report issues (creates GitHub issues if `GITHUB_PAT` is set) |

### Browser Tools

| Tool                    | Description            |
| ----------------------- | ---------------------- |
| `browser_snapshot`      | Get accessibility tree |
| `browser_screenshot`    | Take a screenshot      |
| `browser_click`         | Click an element       |
| `browser_fill`          | Fill an input field    |
| `browser_keyboard`      | Send keyboard input    |
| `browser_navigate`      | Navigate to URL        |
| `browser_evaluate`      | Execute JavaScript     |
| `browser_wait`          | Wait for element state |
| `browser_get_html`      | Get HTML content       |
| `browser_select_option` | Select dropdown option |

### Workflow Tools (Bulk Operations)

For repetitive tasks like "create 100 business partners":

| Tool              | Description                                          |
| ----------------- | ---------------------------------------------------- |
| `workflow_list`   | List saved workflows                                 |
| `workflow_save`   | Save a workflow                                      |
| `workflow_run`    | Run workflow in bulk (requires MCP Sampling support) |
| `workflow_submit` | Submit workflow step result                          |
| `workflow_delete` | Delete a workflow                                    |

> **Note:** `workflow_run` requires MCP Sampling support. As of January 2026, Claude Desktop and Claude Code do NOT support this yet ([tracking issue](https://github.com/anthropics/claude-code/issues/1785)).

## Configuration Reference

| Variable        | Description                       | Default                      |
| --------------- | --------------------------------- | ---------------------------- |
| `SAP_URL`       | SAP Web GUI URL                   | (empty)                      |
| `SAP_USER`      | SAP username for auto-login       | (empty)                      |
| `SAP_PASSWORD`  | SAP password for auto-login       | (empty)                      |
| `SAP_MANDANT`   | SAP client (3-digit, e.g., "100") | (empty)                      |
| `SAP_LANGUAGE`  | Login language (`DE` or `EN`)     | `EN`                         |
| `BROWSER_MODE`  | `launch` or `connect`             | `launch`                     |
| `CDP_URL`       | Chrome DevTools Protocol URL      | `http://localhost:9222`      |
| `AUDIT_LOG_DIR` | Directory for audit logs          | (empty)                      |
| `GITHUB_PAT`    | GitHub PAT for feedback issues    | (empty)                      |
| `GITHUB_REPO`   | Repository for feedback issues    | `Hochfrequenz/sapwebgui.mcp` |

## Troubleshooting

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
- If using auto-login, verify `SAP_USER`, `SAP_PASSWORD`, and `SAP_MANDANT` are set
- Try logging in manually first to verify credentials

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
│  MCP Server (sapwebguimcp)                              │
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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and coding standards.
