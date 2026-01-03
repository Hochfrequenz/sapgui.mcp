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
| ------------------ | ---------------------------------------------------- | ----------------------- |
| `SAP_URL`          | Default SAP Web GUI URL (can be overridden per call) | (empty)                 |
| `SAP_USER`         | SAP username for automatic login                     | (empty)                 |
| `SAP_PASSWORD`     | SAP password for automatic login                     | (empty)                 |
| `SAP_MANDANT`      | SAP client/mandant (3-digit, e.g., "100")            | (empty)                 |
| `SAP_LANGUAGE`     | SAP login language (`DE` or `EN`)                    | `EN`                    |
| `BROWSER_MODE`     | `launch` (start new) or `connect` (use existing)     | `launch`                |
| `BROWSER_TYPE`     | `chromium`, `firefox`, or `webkit`                   | `chromium`              |
| `BROWSER_HEADLESS` | Run headless (`true`/`false`)                        | `false`                 |
| `CDP_URL`          | CDP URL for connecting to existing browser           | `http://localhost:9222` |
| `AUDIT_LOG_DIR`    | Directory for intent audit logs (JSONL files)        | (empty, no file output) |

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
                "run",
                "-i",
                "--rm",
                "--network",
                "sapwebguimcp_default",
                "-e",
                "BROWSER_MODE=connect",
                "-e",
                "CDP_URL=http://cdp-proxy:9222",
                "-e",
                "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "-e",
                "SAP_USER=your_username",
                "-e",
                "SAP_PASSWORD=your_password",
                "-e",
                "SAP_MANDANT=100",
                "ghcr.io/hochfrequenz/sapwebgui.mcp:latest"
            ]
        }
    }
}
```

> **Note**: The `--network sapwebguimcp_default` connects the container to the same Docker network as the CDP proxy, allowing it to reach Chrome via `cdp-proxy:9222`.

### Step 4: Restart Claude Desktop and start chatting

Ask Claude things like:

- "Log me into SAP"
- "Run transaction VA01"
- "Take a screenshot of the current screen"

### Optional: Auto-approve SAP tools

By default, Claude Desktop asks for confirmation before running MCP tools. To auto-approve SAP tools, add an `alwaysAllow` section to your config:

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
                "sapwebguimcp_default",
                "-e",
                "BROWSER_MODE=connect",
                "-e",
                "CDP_URL=http://cdp-proxy:9222",
                "-e",
                "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "-e",
                "SAP_USER=your_username",
                "-e",
                "SAP_PASSWORD=your_password",
                "-e",
                "SAP_MANDANT=100",
                "ghcr.io/hochfrequenz/sapwebgui.mcp:latest"
            ],
            "alwaysAllow": [
                "sap_login",
                "sap_transaction",
                "sap_keyboard",
                "sap_session_status",
                "sap_keepalive_start",
                "sap_keepalive_stop",
                "sap_get_screen_text",
                "sap_read_table",
                "sap_read_status_bar",
                "sap_get_screen_info",
                "log_intent",
                "browser_snapshot",
                "browser_screenshot",
                "browser_click",
                "browser_fill",
                "browser_keyboard",
                "browser_navigate",
                "browser_wait",
                "browser_get_html",
                "browser_select_option"
            ]
        }
    }
}
```

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

# 3. Run the MCP server on the same Docker network as the proxy
docker run -i --rm \
  --network sapwebguimcp_default \
  -e BROWSER_MODE=connect \
  -e CDP_URL=http://cdp-proxy:9222 \
  -e SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui \
  -e SAP_USER=your_username \
  -e SAP_PASSWORD=your_password \
  -e SAP_MANDANT=100 \
  ghcr.io/hochfrequenz/sapwebgui.mcp:latest
```

The `--network sapwebguimcp_default` flag connects the container to the same Docker network as the CDP proxy, so it can reach the proxy via `cdp-proxy:9222`.

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

**Docker Desktop (Windows/macOS)** - connects via Docker network to CDP proxy:

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
                "sapwebguimcp_default",
                "-e",
                "BROWSER_MODE=connect",
                "-e",
                "CDP_URL=http://cdp-proxy:9222",
                "-e",
                "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "-e",
                "SAP_USER=your_username",
                "-e",
                "SAP_PASSWORD=your_password",
                "-e",
                "SAP_MANDANT=100",
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
                "run",
                "--network",
                "host",
                "-i",
                "--rm",
                "-e",
                "BROWSER_MODE=connect",
                "-e",
                "CDP_URL=http://localhost:9222",
                "-e",
                "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "-e",
                "SAP_USER=your_username",
                "-e",
                "SAP_PASSWORD=your_password",
                "-e",
                "SAP_MANDANT=100",
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

3. Configure the MCP server with the appropriate settings:
    - **Native Python or Linux Docker**: `CDP_URL=http://localhost:9222`
    - **Docker Desktop (Windows/macOS)**: Use `--network sapwebguimcp_default` with `CDP_URL=http://cdp-proxy:9222`

The MCP server will connect to your existing browser instead of launching a new one.

## Available Tools

### SAP Tools

| Tool                  | Description                                                                                                                       |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `sap_login`           | Opens SAP Web GUI login page. User enters credentials manually in the browser.                                                    |
| `sap_transaction`     | Enters and executes a transaction code. Automatically enables OK-Code field if not visible (via Settings → enable OK-Code Field). |
| `sap_keepalive_start` | Starts background task to prevent session timeout (default: ping every 5 minutes).                                                |
| `sap_keepalive_stop`  | Stops the keepalive background task.                                                                                              |
| `log_intent`          | Log a high-level intent for audit trail. Used by models to document what they're doing and why.                                   |

### Low-Level Browser Tools (Escape Hatches)

| Tool                    | Description                            |
| ----------------------- | -------------------------------------- |
| `browser_snapshot`      | Get accessibility tree of current page |
| `browser_screenshot`    | Take a screenshot                      |
| `browser_click`         | Click an element by selector           |
| `browser_fill`          | Fill an input field                    |
| `browser_keyboard`      | Send keyboard input                    |
| `browser_navigate`      | Navigate to URL                        |
| `browser_evaluate`      | Execute JavaScript                     |
| `browser_wait`          | Wait for element or timeout            |
| `browser_get_html`      | Get HTML content                       |
| `browser_select_option` | Select dropdown option                 |

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
│   │   ├── intent_tools.py  # Intent logging for audit trail
│   │   └── README.md        # Tools documentation
│   ├── loghandlers/         # Custom log handlers
│   │   └── audit_handler.py # JSONL file handler for intents
│   ├── resources/           # MCP resources
│   │   └── intent_resource.py # Intent log resource
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

### Running Tests with Tox

This project uses [tox](https://tox.wiki/) to run all tests and checks. The test suite includes:

- **Unit tests**: Offline tests using HTML snapshots (no SAP required)
- **Integration tests**: Tests against real SAP Web GUI (auto-skipped on non-SAP machines)

```bash
# Run all tests (integration tests auto-skip if SAP not accessible)
tox -e tests

# Run only unit tests (fast, no SAP needed)
tox -e unit_tests

# Run only SAP integration tests (requires SAP access)
tox -e integration_tests

# Run all checks (tests, linting, formatting, type checking)
tox
```

Language and credentials are loaded from your `.env` file.

**Other tox environments:**

```bash
tox -e coverage     # Run tests with coverage report
tox -e linting      # Run pylint
tox -e formatting   # Check black/isort formatting
tox -e type_check   # Run mypy type checking
tox -e spell_check  # Run codespell
```

### Running Tests in PyCharm

You can run tests directly in PyCharm. Settings are loaded from your `.env` file automatically.

1. **Unit tests**: Right-click `unittests/test_selectors.py` → Run
2. **Integration tests**: Right-click `unittests/test_sap_integration.py` → Run

To change language, edit `SAP_LANGUAGE` in your `.env` file.

**Tox vs PyCharm**: Tox creates isolated virtualenvs (good for CI), PyCharm uses your current interpreter (faster for development).

### HTML Snapshot Testing

We use HTML snapshots captured from real SAP Web GUI sessions to test CSS selectors offline. This approach:

1. **Captures real HTML** during integration tests (when SAP is available)
2. **Validates selectors** against snapshots in fast unit tests (no SAP needed)
3. **Supports multiple languages** (snapshots named `*_en.html`, `*_de.html`)

To capture new snapshots, set `SAP_LANGUAGE` in your `.env` file and run integration tests:

```bash
tox -e integration_tests   # Captures snapshots in configured language
tox -e unit_tests          # Run offline selector tests (no SAP needed)
```

Snapshots are stored in `unittests/testdata/html_snapshots/`.

#### Why Not Syrupy?

We considered [syrupy](https://github.com/tophat/syrupy) (a pytest snapshot testing library) but chose a simpler approach because:

1. **SAP HTML is huge** (~300KB per page) - syrupy's diff output would be unreadable
2. **We don't compare full HTML** - we only validate that specific selectors find elements
3. **Selector validation is the goal** - not detecting HTML changes
4. **BeautifulSoup is sufficient** - we parse HTML and test CSS selectors, no need for snapshot diffing
5. **Multi-language support** - we capture EN/DE variants; syrupy would create separate snapshot dirs

Our approach: capture HTML once, then write focused assertions about selector behavior. If SAP's HTML structure changes, the selector tests fail with clear messages about which selector broke.

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
