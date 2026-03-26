# Test Plan: Compact sap_knowledge.md (Issue #326)

## Context

This PR reduces `sap_knowledge.md` from ~4,900 tokens to ~2,830 tokens (-42%) by removing
detailed setup instructions, code examples, and implementation details while preserving
all core behavioral guidance.

Combined with PR #327 (tool description compaction), the total `sap_get_capabilities`
response should drop from ~10.7k tokens to approximately **8.6k tokens**.

## What Was Removed

| Section | Removed Content | Preserved |
|---------|----------------|-----------|
| **abapGit** (was 96 lines) | Setup steps, finding abapGit in SAP, file naming examples with error messages, development workflow steps, known issues, performance tips, scope explanation, transaction table | Core rule (Git preferred, lowercase filenames, workflow summary, avoid SE80) |
| **Multi-Session** (was 93 lines) | Workflow code examples, full tool-supporting-session lists, sub-agent instruction examples, cross-agent access details, new_window code example | Session management tools table, core rules (pass session+agent_id, check for None, release sessions, session limit) |
| **ALV Pagination** (was 13 lines) | Implementation techniques (focus grid, deduplication, stuck counter, performance stats) | Problem description + "use sap_se16_query" guidance |

## Test Scenarios

### 1. Baseline: Standard SAP Operations (LOW RISK)

**Hypothesis:** Unchanged sections (shortcuts, state bleeding, catalog, selection screens) work identically.

| Test | How | Pass Criteria |
|------|-----|---------------|
| Transaction navigation | `sap_transaction("SE16")` after login | LLM uses shortcuts (F8, F3) instead of clicking buttons |
| Catalog search | Ask LLM to find a transaction | Uses `search_transactions` before guessing |
| State bleeding recovery | Navigate SE16 → SE11 → SE16, fill fields | LLM uses `reset_first=True` when fields don't respond |
| Selection screen handling | Open SM37 with non-default checkboxes | LLM reads form state before assuming defaults |

### 2. abapGit Workflows (MEDIUM RISK)

**Hypothesis:** LLM still knows Git is preferred and filenames must be lowercase, but may need
more guidance on setup steps and edge cases.

| Test | How | Pass Criteria |
|------|-----|---------------|
| ABAP edit preference | Ask to modify a Z-report in a Git-tracked package | LLM suggests local edit + Git push, not SE38 direct edit |
| Filename convention | Ask to create new ABAP class file | LLM uses lowercase filenames |
| abapGit pull | Ask to deploy ABAP changes | LLM uses `sap_abapgit_pull` |
| **REGRESSION: Setup guidance** | Ask "how do I set up abapGit?" | LLM may not have detailed steps — acceptable if it refers to docs |
| **REGRESSION: Known issues** | `sap_abapgit_pull` returns "Pull status unknown" | LLM should still retry (info preserved in compact form) |

### 3. Multi-Session / Parallel Agents (MEDIUM-HIGH RISK)

**Hypothesis:** LLM knows parallel sessions exist and core mechanics, but may struggle with
detailed workflow orchestration without code examples.

| Test | How | Pass Criteria |
|------|-----|---------------|
| Session awareness | Ask to create 5 business partners efficiently | LLM suggests parallel sessions, not sequential |
| Session parameter passing | Sub-agent SAP task | Sub-agent passes `session` and `agent_id` on every call |
| Session creation | Open new session | LLM uses `new_window=True` and checks for `None` |
| Session cleanup | After parallel work completes | LLM calls `sap_session_release` |
| **REGRESSION: Tool list** | Sub-agent unsure which tools accept `session` | May not know all session-aware tools without full list |
| **REGRESSION: Orchestration** | Parent agent setting up 3 sub-agents | May need more trial-and-error without workflow example |

### 4. ALV Grid Operations (LOW RISK)

| Test | How | Pass Criteria |
|------|-----|---------------|
| SE16 query | Read table with >20 rows | LLM uses `sap_se16_query` (handles pagination) |
| Other ALV grid | Read ALV in non-SE16 transaction | LLM uses `log_feedback` to report need |

## How to Measure

### Token Count (Automated)

Add a unit test that calls `sap_get_capabilities()` and measures the JSON response size:

```python
def test_capabilities_response_size():
    result = await sap_get_capabilities()
    json_str = result.model_dump_json()
    char_count = len(json_str)
    # Approximate tokens: chars / 4
    approx_tokens = char_count / 4
    print(f"Capabilities response: {char_count} chars, ~{approx_tokens:.0f} tokens")
    # Target: < 9000 tokens (down from ~10,700)
    assert approx_tokens < 9000
```

### Behavioral Quality (Manual, against SAP)

For each test scenario above:

1. Start fresh Claude Code session with MCP server
2. Login to SAP
3. Let LLM call `sap_get_capabilities()` (will happen automatically via login guidance)
4. Execute the test scenario
5. Document: Did the LLM make correct decisions? Did it need extra prompting?

### Comparison Protocol

Run each MEDIUM/HIGH risk scenario **twice**:
1. Once with the **original** `sap_knowledge.md` (baseline)
2. Once with the **compacted** version

Compare: number of tool calls, success rate, need for human intervention.

## Acceptance Criteria

- [ ] All LOW RISK tests pass without regression
- [ ] MEDIUM RISK tests: LLM makes correct high-level decisions (Git preferred, parallel sessions exist)
- [ ] Acceptable regressions: LLM may need 1-2 extra prompts for detailed abapGit setup or multi-session orchestration
- [ ] Token count of `sap_get_capabilities` response < 9,000 tokens
- [ ] No functional breakage in existing unit tests
