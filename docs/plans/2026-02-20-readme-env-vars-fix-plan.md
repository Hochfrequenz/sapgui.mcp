# README Environment Variables Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix README.md so every deployment section has complete, accurate environment variable documentation with clear required/optional distinction.

**Architecture:** Pure documentation change — edit README.md in 5 sequential steps, each targeting a specific section. No code changes.

**Tech Stack:** Markdown

---

### Task 1: Add MCP Registration Intro

**Files:**

- Modify: `README.md:13` (after "Choose one of these three approaches:")

**Step 1: Add the intro block**

Insert the following after line 13 (`Choose one of these three approaches:`) and before the first `<details>` tag:

```markdown
**Where to register the MCP server:**

- **Claude Code** — add to `.mcp.json` in your project root (per-project config)
- **Claude Desktop** — add to `claude_desktop_config.json` (global config, path varies by OS — shown in each section below)

All three setup approaches below show you how to configure both.
```

**Step 2: Verify visually**

Open README.md and confirm the new block appears between the "Choose one..." line and the first `<details>` section.

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add MCP registration intro to README Setup section"
```

---

### Task 2: Fix EXE Section

**Files:**

- Modify: `README.md` — the `<details>` block starting at line 15 ("Standalone Executable")

**Step 1: Replace the "Step 2: Configure your MCP client" content**

Replace everything from `### Step 2: Configure your MCP client` up to (but not including) `No Docker, no CDP proxy` with:

````markdown
### Step 2: Configure your MCP client

**Required:** `SAP_URL`, `SAP_USER`, `SAP_PASSWORD`, `SAP_MANDANT`. All other variables are optional — remove any you don't need. See [Configuration Reference](#configuration-reference) for the full list.

> `GITHUB_PAT` is only needed for `log_feedback` (creates GitHub issues) or abapGit operations. Remove it if you don't need these features.

#### Claude Desktop

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
````

#### Claude Code

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

````

Note: `BROWSER_MODE` defaults to `connect` and `CDP_URL` defaults to `http://localhost:9222`, so they don't need to be set for the EXE path. No `AUDIT_LOG_DIR` since there's no Docker volume mount.

**Step 2: Verify**

Read the modified section and confirm:
- Both Claude Desktop and Claude Code configs are shown
- 6 env vars: SAP_URL, SAP_USER, SAP_PASSWORD, SAP_MANDANT, SAP_LANGUAGE, GITHUB_PAT
- Language is `DE`
- No AUDIT_LOG_DIR
- Required/optional prose is present
- GITHUB_PAT note is present

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: expand EXE section with complete env vars and both client configs"
````

---

### Task 3: Fix Docker Section

**Files:**

- Modify: `README.md` — the Docker `<details>` block, specifically "Step 3: Configure your MCP client"

**Step 1: Replace the Docker Step 3 content**

Replace the `### Step 3: Configure your MCP client` section (from that heading through the end of the "Option B: Claude Code" JSON block, up to "Then start Claude code:") with:

````markdown
### Step 3: Configure your MCP client

**Required:** `SAP_URL`, `SAP_USER`, `SAP_PASSWORD`, `SAP_MANDANT`. All other variables are optional — remove any you don't need. See [Configuration Reference](#configuration-reference) for the full list.

> `GITHUB_PAT` is only needed for `log_feedback` (creates GitHub issues) or abapGit operations. Remove the `-e GITHUB_PAT=...` line if you don't need these features.

Choose **one** of the following options based on which Claude client you use.

#### Option A: Claude Desktop

First, create the audit logs directory:

```powershell
mkdir $env:USERPROFILE\sap-audit-logs
```
````

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
                "SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui",
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
                "ghcr.io/hochfrequenz/sapgui.mcp:latest"
            ]
        }
    }
}
```

Replace:

- `YourUsername` with your Windows username
- `your_username` / `your_password` with your SAP credentials
- `your_sap_server` with your SAP server hostname
- `your_github_pat` with a [GitHub Personal Access Token](https://github.com/settings/tokens) (optional — see note above)

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
                "-v",
                "C:/Users/YourUsername/sap-audit-logs:/audit-logs",
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
                "-e",
                "SAP_LANGUAGE=DE",
                "-e",
                "AUDIT_LOG_DIR=/audit-logs",
                "-e",
                "GITHUB_PAT=your_github_pat",
                "ghcr.io/hochfrequenz/sapgui.mcp:latest"
            ]
        }
    }
}
```

````

Key changes from current:
- SAP_LANGUAGE changed from DE to DE (keep — already DE in current)
- Actually current already has most vars; main change is adding required/optional prose, GITHUB_PAT note, and fixing the "Replace:" section to include SAP server
- Remove the sentence about password escaping (confusing, unhelpful)
- Remove the sentence describing `.mcp.json` location (already explained in the intro)

**Step 2: Verify**

Confirm:
- Required/optional prose is present
- GITHUB_PAT note is present
- Both Option A and Option B show the same env vars
- Language is `DE`
- "Replace:" list is updated
- No password-escaping warning

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: fix Docker section with required/optional distinction and GITHUB_PAT note"
````

---

### Task 4: Fix Dev/Python Section

**Files:**

- Modify: `README.md` — the Development Setup `<details>` block

**Step 1: Replace the "Configure Claude Desktop for local development" content**

Replace from `### Configure Claude Desktop for local development` through the end of the JSON block (before `</details>`) with:

````markdown
### Configure your MCP client

**Required:** `SAP_URL`, `SAP_USER`, `SAP_PASSWORD`, `SAP_MANDANT`. All other variables are optional — remove any you don't need. See [Configuration Reference](#configuration-reference) for the full list.

> `GITHUB_PAT` is only needed for `log_feedback` (creates GitHub issues) or abapGit operations. Remove it if you don't need these features.

When running Python directly (not in Docker), you don't need the CDP proxy — Python can connect to Chrome on localhost.

#### Claude Desktop

Add to `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`, macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/your/venv/Scripts/run-sapgui-mcp-server.exe",
            "args": [],
            "env": {
                "SAP_URL": "https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "SAP_USER": "your_username",
                "SAP_PASSWORD": "your_password",
                "SAP_MANDANT": "100",
                "SAP_LANGUAGE": "DE",
                "BROWSER_MODE": "connect",
                "CDP_URL": "http://localhost:9222",
                "GITHUB_PAT": "your_github_pat"
            }
        }
    }
}
```
````

#### Claude Code

Add to `.mcp.json` in your project root:

```json
{
    "mcpServers": {
        "sap-webgui": {
            "command": "C:/path/to/your/venv/Scripts/run-sapgui-mcp-server.exe",
            "args": [],
            "env": {
                "SAP_URL": "https://your-sap-server/sap/bc/gui/sap/its/webgui",
                "SAP_USER": "your_username",
                "SAP_PASSWORD": "your_password",
                "SAP_MANDANT": "100",
                "SAP_LANGUAGE": "DE",
                "BROWSER_MODE": "connect",
                "CDP_URL": "http://localhost:9222",
                "GITHUB_PAT": "your_github_pat"
            }
        }
    }
}
```

````

Key changes: heading renamed from "Configure Claude Desktop for local development" to "Configure your MCP client". Both clients shown. Full common env vars. Required/optional prose. GITHUB_PAT note. "No CDP proxy needed" note moved to prose above configs. No AUDIT_LOG_DIR.

**Step 2: Verify**

Confirm:
- Heading says "Configure your MCP client" (not just Claude Desktop)
- Both Claude Desktop and Claude Code configs shown
- 8 env vars: SAP_URL, SAP_USER, SAP_PASSWORD, SAP_MANDANT, SAP_LANGUAGE, BROWSER_MODE, CDP_URL, GITHUB_PAT
- No AUDIT_LOG_DIR
- Language is DE
- Required/optional prose present

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: expand Dev/Python section with both client configs and full env vars"
````

---

### Task 5: Update Configuration Reference Table

**Files:**

- Modify: `README.md` — the `## Configuration Reference` section (around line 409)

**Step 1: Replace the Configuration Reference table**

Replace the existing table with:

```markdown
## Configuration Reference

| Variable           | Required                    | Description                                                  | Default                      |
| ------------------ | --------------------------- | ------------------------------------------------------------ | ---------------------------- |
| `SAP_URL`          | **Yes**                     | SAP Web GUI URL                                              | —                            |
| `SAP_USER`         | **Yes**                     | SAP username for auto-login                                  | —                            |
| `SAP_PASSWORD`     | **Yes**                     | SAP password for auto-login                                  | —                            |
| `SAP_MANDANT`      | **Yes**                     | SAP client (3-digit, e.g., `100`)                            | —                            |
| `SAP_LANGUAGE`     | No                          | Login language (`DE` or `EN`)                                | `EN`                         |
| `BROWSER_MODE`     | No                          | `connect` (existing Chrome) or `launch` (Playwright)         | `connect`                    |
| `BROWSER_TYPE`     | No                          | `chromium`, `firefox`, or `webkit`                           | `chromium`                   |
| `BROWSER_HEADLESS` | No                          | Run browser in headless mode                                 | `false`                      |
| `CDP_URL`          | When `BROWSER_MODE=connect` | Chrome DevTools Protocol URL                                 | `http://localhost:9222`      |
| `AUDIT_LOG_DIR`    | No                          | Directory for audit logs (JSONL)                             | —                            |
| `GITHUB_PAT`       | No                          | GitHub PAT for `log_feedback` issues and abapGit auth        | —                            |
| `GITHUB_USER`      | No                          | GitHub username for abapGit (falls back to `x-access-token`) | —                            |
| `GITHUB_REPO`      | No                          | Repository for feedback issues                               | `Hochfrequenz/sapgui.mcp` |
| `ABAPGIT_PAT`      | No                          | Separate PAT for abapGit (overrides `GITHUB_PAT` if set)     | —                            |
| `PAPERTRAIL_HOST`  | No                          | Papertrail syslog host (empty to disable)                    | `logs5.papertrailapp.com`    |
| `PAPERTRAIL_PORT`  | No                          | Papertrail syslog port                                       | `35329`                      |
| `LOG_FORMAT`       | No                          | Set to `json` for JSON log output                            | human-readable               |
| `LOG_LEVEL`        | No                          | `DEBUG`, `INFO`, `WARNING`, or `ERROR`                       | `INFO`                       |
```

**Step 2: Verify**

Confirm:

- 18 rows (all env vars from `config.py` + `logging_config.py`)
- Required column present with **Yes** for SAP credentials
- CDP_URL shows conditional requirement
- Defaults match `config.py` exactly
- No duplicate or missing vars

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: expand Configuration Reference with all env vars and required column"
```

---

### Summary of All Changes

| Task | Section          | Key Changes                                                                            |
| ---- | ---------------- | -------------------------------------------------------------------------------------- |
| 1    | Setup intro      | Add MCP registration explanation (`.mcp.json` vs `claude_desktop_config.json`)         |
| 2    | EXE              | Add Claude Code config, expand to 6 env vars, required/optional prose, GITHUB_PAT note |
| 3    | Docker           | Add required/optional prose, GITHUB_PAT note, clean up "Replace:" list                 |
| 4    | Dev/Python       | Add Claude Code config, expand to 8 env vars, rename heading, required/optional prose  |
| 5    | Config Reference | Add 8 missing vars, add Required column, verify all defaults                           |
