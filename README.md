# SAP Web GUI MCP Server

[![Unittests](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Unittests/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)
[![Coverage](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Coverage/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)
[![Linting](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Linting/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)
[![Formatting](https://github.com/Hochfrequenz/sapwebgui.mcp/workflows/Formatting/badge.svg)](https://github.com/Hochfrequenz/sapwebgui.mcp/actions)

An MCP (Model Context Protocol) server for SAP Web GUI browser automation.
Built on the [dev-browser](https://github.com/anthropics/dev-browser) philosophy: persistent browser sessions with incremental exploration.

## Features

- **SAP Login**: Opens SAP Web GUI for user to enter credentials manually
- **Smart Transaction Entry**: Automatically enables OK-Code field if not visible, then enters transaction
- **Low-level browser tools**: Click, fill, snapshot for edge cases when SAP tools don't work
- **Persistent sessions**: Login once, stay authenticated across tool calls
- **Browser choice**: Use your own browser (VPN/Citrix) or let the server launch one
- **Python 3.11-3.14 support**: Tested on latest Python versions

## Installation

### Install as Python Package

```bash
pip install sapwebguimcp
```

Or with uv:

```bash
uv pip install sapwebguimcp
```

After installation, install Playwright browsers:

```bash
playwright install chromium
```

### Install as Docker Image

```bash
docker pull ghcr.io/hochfrequenz/sapwebgui.mcp:latest
```

## Configuration

Configure via environment variables:

| Variable           | Description                                          | Default                 |
|--------------------|------------------------------------------------------|-------------------------|
| `SAP_URL`          | Default SAP Web GUI URL (can be overridden per call) | (empty)                 |
| `SAP_USER`         | SAP username for automatic login                     | (empty)                 |
| `SAP_PASSWORD`     | SAP password for automatic login                     | (empty)                 |
| `SAP_MANDANT`      | SAP client/mandant (3-digit, e.g., "100")            | (empty)                 |
| `SAP_LANGUAGE`     | SAP login language (`DE` or `EN`)                    | `EN`                    |
| `BROWSER_MODE`     | `launch` (start new) or `connect` (use existing)     | `launch`                |
| `BROWSER_TYPE`     | `chromium`, `firefox`, or `webkit`                   | `chromium`              |
| `BROWSER_HEADLESS` | Run headless (`true`/`false`)                        | `false`                 |
| `CDP_URL`          | CDP URL for connecting to existing browser           | `http://localhost:9222` |

If `SAP_USER`, `SAP_PASSWORD`, and `SAP_MANDANT` are set, the server will automatically fill in the login form.
Otherwise, the login page opens for manual credential entry.

## Quick Start (End Users)

The easiest way to use this server is with **Claude Desktop**:

### Step 1: Start Chrome with remote debugging

Chrome needs to be started with special flags:
- `--remote-debugging-port=9222` - Enables the Chrome DevTools Protocol
- `--user-data-dir` - Uses a separate profile (required, otherwise Chrome joins an existing instance)
- `--ignore-certificate-errors` - Skips SSL certificate warnings (useful for SAP systems with self-signed certs)

**Windows** (run in PowerShell):
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
```

**macOS**:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" --ignore-certificate-errors
```

**Linux**:
```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" --ignore-certificate-errors
```

**Verify it's working** (the debugging port should respond):
```bash
# Windows (PowerShell)
Invoke-WebRequest -Uri 'http://localhost:9222/json/version' -UseBasicParsing

# macOS/Linux
curl http://localhost:9222/json/version
```

If you get a connection error, Chrome isn't listening on port 9222. Make sure you used the `--user-data-dir` flag.

### Step 2: Start the CDP proxy (Docker Desktop on Windows/macOS)

When running in Docker Desktop on Windows or macOS, we need a proxy because:
1. Chrome's DevTools Protocol rejects HTTP requests where the Host header isn't `localhost`
2. Chrome returns WebSocket URLs pointing to `localhost`, which doesn't work inside Docker containers

The proxy rewrites these headers/URLs so Docker containers can connect to Chrome.

```bash
# Clone the repository (if you haven't already)
git clone https://github.com/Hochfrequenz/sapwebgui.mcp.git
cd sapwebgui.mcp

# Start the CDP proxy
docker compose up -d cdp-proxy
```

> **Note**: On native Linux with Docker, you can skip this step and use `--network host` with `CDP_URL=http://localhost:9222` instead.

### Step 3: Configure Claude Desktop

Find your Claude Desktop config file:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add this configuration (replace the SAP values with your own):

```json
{
  "mcpServers": {
    "sap-webgui": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "BROWSER_MODE=connect",
        "-e", "CDP_URL=http://host.docker.internal:9223",
        "-e", "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
        "-e", "SAP_USER=your_username",
        "-e", "SAP_PASSWORD=your_password",
        "-e", "SAP_MANDANT=100",
        "ghcr.io/hochfrequenz/sapwebgui.mcp:latest"
      ]
    }
  }
}
```

### Step 4: Restart Claude Desktop and start chatting

Ask Claude things like:
- "Log me into SAP"
- "Run transaction VA01"
- "Take a screenshot of the current screen"

---

## Start the Server (Advanced)

### Python

```bash
run-sapwebgui-mcp-server
```

### Docker

Docker requires `BROWSER_MODE=connect` to control a browser running on the host. The setup differs between native Linux and Docker Desktop (Windows/macOS).

#### Native Linux (--network host works)

```bash
# 1. Start Chrome with remote debugging
google-chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" --ignore-certificate-errors

# 2. Run the MCP server with --network host
docker run --network host -i --rm \
  -e BROWSER_MODE=connect \
  -e CDP_URL=http://localhost:9222 \
  -e SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui \
  -e SAP_USER=your_username \
  -e SAP_PASSWORD=your_password \
  -e SAP_MANDANT=100 \
  ghcr.io/hochfrequenz/sapwebgui.mcp:latest
```

#### Docker Desktop on Windows/macOS (requires CDP proxy)

On Docker Desktop, `--network host` doesn't work properly, and Chrome rejects connections from `host.docker.internal`. You need the CDP proxy:

```bash
# 1. Start Chrome with remote debugging
# Windows:
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
# macOS:
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" --ignore-certificate-errors

# 2. Start the CDP proxy (from the repository root)
docker compose up -d cdp-proxy

# 3. Run the MCP server connecting via the proxy (port 9223)
docker run -i --rm \
  -e BROWSER_MODE=connect \
  -e CDP_URL=http://host.docker.internal:9223 \
  -e SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui \
  -e SAP_USER=your_username \
  -e SAP_PASSWORD=your_password \
  -e SAP_MANDANT=100 \
  ghcr.io/hochfrequenz/sapwebgui.mcp:latest
```

## Register in Claude Desktop / Claude Code

### If installed via pip

Modify your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sap-webgui": {
      "command": "/path/to/your/venv/bin/run-sapwebgui-mcp-server",
      "args": [],
      "env": {
        "SAP_URL": "https://your-sap-server/sap/bc/gui/sap/its/webgui"
      }
    }
  }
}
```

### If installed via Docker

First start Chrome with remote debugging and the CDP proxy (see Quick Start above), then configure Claude:

**Docker Desktop (Windows/macOS)** - uses CDP proxy on port 9223:
```json
{
  "mcpServers": {
    "sap-webgui": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "BROWSER_MODE=connect",
        "-e", "CDP_URL=http://host.docker.internal:9223",
        "-e", "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
        "-e", "SAP_USER=your_username",
        "-e", "SAP_PASSWORD=your_password",
        "-e", "SAP_MANDANT=100",
        "ghcr.io/hochfrequenz/sapwebgui.mcp:latest"
      ]
    }
  }
}
```

**Native Linux** - uses `--network host`:
```json
{
  "mcpServers": {
    "sap-webgui": {
      "command": "docker",
      "args": [
        "run", "--network", "host", "-i", "--rm",
        "-e", "BROWSER_MODE=connect",
        "-e", "CDP_URL=http://localhost:9222",
        "-e", "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
        "-e", "SAP_USER=your_username",
        "-e", "SAP_PASSWORD=your_password",
        "-e", "SAP_MANDANT=100",
        "ghcr.io/hochfrequenz/sapwebgui.mcp:latest"
      ]
    }
  }
}
```

## Connecting to Your Own Browser (VPN/Citrix)

If you need to use a browser that's already connected to VPN or Citrix:

1. Launch your browser with remote debugging enabled:

```bash
# Chrome/Edge (Linux)
google-chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" --ignore-certificate-errors

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" --ignore-certificate-errors

# Windows (PowerShell)
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug" --ignore-certificate-errors
```

2. If using Docker Desktop (Windows/macOS), start the CDP proxy:

```bash
cd sapwebgui.mcp
docker compose up -d cdp-proxy
```

3. Configure the MCP server with the appropriate CDP URL:
   - **Native Python or Linux Docker**: `CDP_URL=http://localhost:9222`
   - **Docker Desktop (Windows/macOS)**: `CDP_URL=http://host.docker.internal:9223`

The MCP server will connect to your existing browser instead of launching a new one.

## Available Tools

### SAP Tools

| Tool | Description |
|------|-------------|
| `sap_login` | Opens SAP Web GUI login page. User enters credentials manually in the browser. |
| `sap_transaction` | Enters and executes a transaction code. Automatically enables OK-Code field if not visible (via Settings → enable OK-Code Field). |
| `sap_keepalive_start` | Starts background task to prevent session timeout (default: ping every 5 minutes). |
| `sap_keepalive_stop` | Stops the keepalive background task. |

### Low-Level Browser Tools (Escape Hatches)

| Tool | Description |
|------|-------------|
| `browser_snapshot` | Get accessibility tree of current page |
| `browser_screenshot` | Take a screenshot |
| `browser_click` | Click an element by selector |
| `browser_fill` | Fill an input field |
| `browser_keyboard` | Send keyboard input |
| `browser_navigate` | Navigate to URL |
| `browser_evaluate` | Execute JavaScript |
| `browser_wait` | Wait for element or timeout |
| `browser_get_html` | Get HTML content |
| `browser_select_option` | Select dropdown option |

## Usage Example

```
User: Please log me in to SAP

Claude: [calls sap_login(url="https://your-sap.com/webgui")]
        SAP login page opened. Please enter your credentials in the browser window.

User: Done, I'm logged in. Now run transaction VA01

Claude: [calls sap_transaction(tcode="VA01")]
        Transaction VA01 executed. Current page: Create Sales Order.
        Check the browser window for the transaction screen.
```

### Preventing Session Timeout

If you need to step away or have long pauses between actions, enable keepalive:

```
User: I need to take a break, keep my SAP session alive

Claude: [calls sap_keepalive_start(interval_seconds=300)]
        Keepalive started. Will ping every 300 seconds (5 minutes) to prevent session timeout.

... (30 minutes later) ...

User: I'm back, you can stop the keepalive

Claude: [calls sap_keepalive_stop()]
        Keepalive stopped.
```

## How sap_transaction Works

The `sap_transaction` tool is smart about the OK-Code field:

1. **Check**: First looks for the OK-Code input field
2. **Enable if needed**: If not found, attempts to enable it:
   - Expands menu (if collapsed)
   - Clicks settings/gear button
   - Finds and enables the "OK-Code Field" checkbox
   - Saves settings
3. **Verify**: Confirms the field is now visible
4. **Execute**: Enters the transaction code and presses Enter

This handles SAP Web GUI installations where the OK-Code field is hidden by default.

## Project Structure

```
sap-webgui-mcp/
├── src/sapwebguimcp/
│   ├── __init__.py          # Package version and exports
│   ├── server.py            # MCP server entry point
│   ├── models/              # Data models
│   │   ├── config.py        # Settings (pydantic-settings)
│   │   ├── browser.py       # Browser manager
│   │   └── README.md        # Models documentation
│   ├── tools/               # MCP tools
│   │   ├── __init__.py      # Tool registration exports
│   │   ├── sap_tools.py     # SAP-specific tools
│   │   ├── browser_tools.py # Browser escape hatches
│   │   └── README.md        # Tools documentation
│   └── skills/              # Reusable workflows
│       └── README.md        # Skills documentation
├── unittests/               # Test suite
├── .github/workflows/       # CI/CD pipelines
├── pyproject.toml           # Package metadata
├── tox.ini                  # Test environments
├── Dockerfile               # Container build
├── docker-compose.yml       # Docker Compose for CDP proxy
├── nginx-cdp-proxy.conf     # Nginx config for CDP proxy
└── README.md                # This file
```

## Development

This project uses [tox](https://tox.wiki/) for testing and development.

### Setup

```bash
# Clone the repository
git clone https://github.com/Hochfrequenz/sapwebgui.mcp.git
cd sapwebgui.mcp

# Create development environment
tox -e dev

# Activate the environment
source .tox/dev/bin/activate  # Linux/macOS
# or
.tox\dev\Scripts\activate  # Windows

# Install Playwright browsers
playwright install chromium
```

### Running Tests

```bash
tox -e tests        # Run unit tests
tox -e coverage     # Run tests with coverage (80% minimum)
tox -e linting      # Run pylint
tox -e formatting   # Check black/isort
tox -e type_check   # Run mypy
tox -e spell_check  # Run codespell
```

### Code Style

This project uses:
- [Black](https://github.com/psf/black) for code formatting
- [isort](https://pycqa.github.io/isort/) for import sorting
- [pylint](https://pylint.org/) for linting
- [mypy](https://mypy.readthedocs.io/) for type checking
- [codespell](https://github.com/codespell-project/codespell) for spell checking

## Extending the Server

### Adding New Tools

See [src/sapwebguimcp/tools/README.md](src/sapwebguimcp/tools/README.md) for detailed instructions on creating new tools.

### Adding New Models

See [src/sapwebguimcp/models/README.md](src/sapwebguimcp/models/README.md) for information about the data models.

### Creating Skills

See [src/sapwebguimcp/skills/README.md](src/sapwebguimcp/skills/README.md) for how to create reusable workflows.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Browser (Chromium/Firefox/Your Browser)                │
│  - Persistent session                                   │
│  - SAP Web GUI loaded                                   │
│  - User logs in manually                                │
└─────────────────────────────────────────────────────────┘
            ↑
            │ Playwright
            ↓
┌─────────────────────────────────────────────────────────┐
│  MCP Server (sapwebguimcp)                              │
│  - Manages browser connection                           │
│  - SAP tools + browser escape hatches                   │
└─────────────────────────────────────────────────────────┘
            ↑
            │ MCP (stdio)
            ↓
┌─────────────────────────────────────────────────────────┐
│  Claude Desktop / Claude Code                           │
│  - Calls tools to interact with SAP                     │
└─────────────────────────────────────────────────────────┘
```

## Publishing to PyPI

This repository uses trusted publishing workflow:

1. Create a release environment in GitHub repository settings
2. Set up trusted publisher in PyPI account
3. Uncomment the publish job in `.github/workflows/python-publish.yml`
4. Create a GitHub release to trigger publishing

## License

MIT
