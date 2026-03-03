# Bulk Operations Performance Analysis

Analysis of performance optimization options for running bulk SAP operations with parallel agents.

## Current Architecture

When running bulk operations (e.g., creating 300+ business partners), the recommended approach is:

```
Main Agent
  ├── Sub-Agent 1 (session s1) → MCP calls → Browser Tab 1
  ├── Sub-Agent 2 (session s2) → MCP calls → Browser Tab 2
  ├── Sub-Agent 3 (session s3) → MCP calls → Browser Tab 3
  └── ... (up to N parallel agents)
```

**Observed throughput:** ~6-9 records/minute with 6 parallel agents.

### Session Isolation

Each session maps to a separate browser tab (Playwright `Page`):

| Aspect               | Isolation Level                |
| -------------------- | ------------------------------ |
| DOM                  | Fully isolated per tab         |
| JavaScript context   | Fully isolated per tab         |
| SAP session state    | Separate SAP session per tab   |
| Cookies/localStorage | Shared (same BrowserContext)   |
| Browser process      | Shared (one Chromium instance) |

This means parallel agents operating on different sessions are safe and won't interfere with each other.

---

## Optimization Options Evaluated

### 1. Batched Tool Calls (sap_execute_sequence)

**Proposal:** Combine multiple operations into a single MCP call:

```json
{
    "steps": [
        { "action": "keyboard", "key": "F5" },
        { "action": "fill", "fields": { "Name": "Test" } },
        { "action": "keyboard", "key": "Ctrl+S" },
        { "action": "read_status_bar" }
    ]
}
```

**Analysis:**

| Factor              | Impact                                                    |
| ------------------- | --------------------------------------------------------- |
| MCP round-trips     | Reduced from N to 1                                       |
| Theoretical speedup | ~1.8x (not 5x, because SAP operations are the bottleneck) |
| Error handling      | Complex - which step failed?                              |
| Observability       | Lost - agent can't see intermediate states                |
| Adaptability        | Lost - can't react to popups or errors mid-sequence       |

**Verdict: Not recommended.**

The fundamental problem is **blind execution**. SAP Web GUI is timing-sensitive and state-dependent. If an unexpected popup appears or a field validation fails mid-sequence, the batch continues blindly, likely corrupting the operation.

The ~1.8x speed gain doesn't justify the stability risk.

### 2. Parallel Field Fills Within Session

**Proposal:** Fill multiple form fields concurrently since they target different DOM elements:

```json
{
    "parallel": [
        { "tool": "sap_set_field", "label": "Vorname", "value": "Kiwi" },
        { "tool": "sap_set_field", "label": "Nachname", "value": "Kirsche" }
    ]
}
```

**Analysis:**

| Factor               | Impact                                             |
| -------------------- | -------------------------------------------------- |
| Time savings         | ~50-100ms per form (~2% overall)                   |
| SAP JS compatibility | Risk - SAP may not handle concurrent field updates |
| Focus conflicts      | Risk - browser input depends on element focus      |
| Validation races     | Risk - concurrent validations may conflict         |

**Verdict: Not recommended.**

The MCP round-trip (~200-500ms) is the bottleneck, not DOM operations (~50ms each). Parallelizing the cheap part while the expensive part stays sequential yields minimal gains (~2%) with significant stability risk.

---

## Recommendations

### For Maximum Throughput

Continue using **parallel sub-agents with separate sessions**. This is the optimal approach given current constraints:

1. Each agent gets its own browser tab (session s1, s2, s3...)
2. Sessions are fully isolated at the DOM level
3. Agents can react to errors and adapt in real-time
4. Linear scaling with agent count

### What NOT To Do

1. **Don't batch tool calls** - Blind execution is fragile in SAP
2. **Don't parallelize field fills** - Minimal gain (~2%), stability risk
3. **Don't fight the architecture** - The MCP round-trip is inherent; work around it with parallelism, not batching

---

## Appendix: Timing Breakdown

Typical per-record timing:

| Operation                               | Time    |
| --------------------------------------- | ------- |
| SAP UI operations (fills, waits, saves) | ~2000ms |
| MCP round-trips (10 calls × 250ms)      | ~2500ms |
| **Total per record**                    | ~4500ms |

With 6 parallel agents: ~4500ms / 6 = ~750ms effective per record = ~80 records/minute theoretical max.

Observed: ~6-9 records/minute suggests other factors (agent thinking time, error handling, SAP server response variability).

---

_Document created: 2026-01-25_
_Last reviewed: 2026-01-25 (verified against codebase)_
_Based on brainstorming session analyzing bulk operation performance options._
