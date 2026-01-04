# Testing workflow_run with GitHub Copilot (JetBrains/VS Code)

## Background

The `workflow_run` tool uses MCP Sampling (`ctx.sample()`) to execute bulk SAP operations server-side, saving ~90% context compared to manual iteration.

### The Problem with Claude Desktop/Code

**Neither Claude Desktop nor Claude Code support MCP sampling** (as of January 2026).

- Anthropic created the MCP spec but hasn't implemented sampling in their clients
- Error: "Client does not support sampling"
- Tracking issue: https://github.com/anthropics/claude-code/issues/1785

### Clients That DO Support Sampling

| Client | Sampling | Local MCP | Status |
|--------|----------|-----------|--------|
| VS Code + Copilot | Yes | Yes | Works |
| JetBrains + Copilot | Yes | Yes | Works |
| ChatGPT Desktop | Yes | No (remote only) | Won't work for local servers |
| Claude Desktop | No | Yes | Doesn't support sampling |
| Claude Code | No | Yes | Doesn't support sampling |

---

## Setup Instructions for JetBrains (PyCharm/IntelliJ)

### Prerequisites

1. JetBrains IDE 2025.1 or newer
2. GitHub Copilot plugin v1.5.57 or newer
3. Docker running with `sapwebgui-mcp:test` image built
4. CDP proxy running: `docker-compose up -d cdp-proxy`

### Step 1: Enable MCP Server in JetBrains

1. Go to **Settings → Tools → MCP Server**
2. Click **Enable MCP Server**
3. If the UI is stuck/spinning, try restarting the IDE

### Step 2: Configure the SAP MCP Server

Add to your MCP configuration (location varies, check Settings → Tools → MCP Server → Open Config):

```json
{
  "mcpServers": {
    "sap-webgui-mcp": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--network", "sapwebguimcp_default",
        "-e", "BROWSER_MODE=connect",
        "-e", "CDP_URL=http://cdp-proxy:9222",
        "-e", "SAP_URL=<your-sap-url>",
        "-e", "SAP_USER=<your-user>",
        "-e", "SAP_PASSWORD=<your-password>",
        "-e", "SAP_MANDANT=<your-mandant>",
        "sapwebgui-mcp:test"
      ]
    }
  }
}
```

### Step 3: Enable Sampling for the Server

In VS Code, add to `settings.json`:
```json
{
  "chat.mcp.serverSampling": {
    "sap-webgui-mcp": {
      "allowedModels": ["*"]
    }
  }
}
```

For JetBrains, check if there's a similar setting in Copilot preferences.

---

## Testing workflow_run

### Test 1: Verify Tools Are Available

In Copilot Chat, ask:
```
List all available SAP workflow tools from the sap-webgui-mcp server.
```

Expected: Should show `workflow_list`, `workflow_save`, `workflow_run`, `workflow_submit`, `workflow_delete`

### Test 2: List Workflows

```
Use workflow_list to show me all available workflows.
```

Expected: Should show at least `bp-person-creation` (bundled workflow)

### Test 3: Test workflow_run with Sampling

```
I want to test the workflow system. Please:

1. Login to SAP with sap_login
2. Use workflow_run to create 2 test business partners:
   - name: "bp-person-creation"
   - items: [
       {"vorname": "Test1", "nachname": "User1", "strasse": "Teststr. 1", "plz": "10115", "ort": "Berlin"},
       {"vorname": "Test2", "nachname": "User2", "strasse": "Teststr. 2", "plz": "20095", "ort": "Hamburg"}
     ]

Report the results including success/failure counts.
```

### What Success Looks Like

- Progress updates: "Processing 1/2...", "Processing 2/2..."
- Single tool call in context (not 20+ individual calls)
- Aggregated result with `succeeded` and `failed` counts

### What Failure Looks Like

- Error: "Client does not support sampling" → Client doesn't support MCP sampling
- Error: "Client does not support sampling with tools" → Client supports basic sampling but not with tools
- No progress updates, just immediate failure

---

## Troubleshooting

### "Client does not support sampling"

Your MCP client doesn't advertise the `sampling` capability. Options:
1. Use VS Code + Copilot instead
2. Use JetBrains + Copilot instead
3. Wait for Claude Desktop/Code to add support

### MCP Server Not Connecting

1. Check Docker is running: `docker ps`
2. Check CDP proxy: `docker-compose up -d cdp-proxy`
3. Check image exists: `docker images sapwebgui-mcp:test`
4. Rebuild if needed: `docker-compose build sapwebgui-mcp`

### JetBrains MCP Settings Spinning Forever

1. Restart the IDE
2. Check for plugin updates
3. Try configuring via the JSON file directly

---

## Context Savings Verification

After successful test, compare:

| Metric | Manual (without workflow_run) | With workflow_run |
|--------|------------------------------|-------------------|
| Tool calls visible in context | ~10 per item | 1 total |
| Tokens consumed | ~5,000 per item | ~2,000 total |
| For 100 items | ~500,000 tokens | ~2,000 tokens |

The whole point is that `workflow_run` executes iterations **server-side** using the client's LLM via sampling, so your context only sees the final summary.

---

## Files Changed in This Implementation

- `src/sapwebguimcp/models/workflow_models.py` - Pydantic models
- `src/sapwebguimcp/models/workflow_storage.py` - Load/save workflows
- `src/sapwebguimcp/tools/workflow_tools.py` - MCP tools including workflow_run
- `src/sapwebguimcp/tools/sap_tool_impl.py` - Standalone impl functions for sampling
- `src/sapwebguimcp/workflows/bp-person-creation.md` - Bundled example workflow
- `docs/plans/2026-01-04-workflow-learning-design.md` - Design document

## Git Branch

All changes are on: `feat/workflow-learning`

Commits:
- `a045af5` feat(workflow): add workflow system for repetitive SAP task automation
- `c551161` test(workflow): add integration tests for workflow tools and EMMACL iteration
- `7acf66f` docs(design): update workflow design with ctx.sample() implementation details
- `67892e6` docs: add workflow sampling manual test and update README
- `e63bd44` fix(docs): remove incorrect mcpiuse.com references, clarify sampling limitation
