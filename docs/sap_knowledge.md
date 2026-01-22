# SAP WebGUI MCP Knowledge Base

## Multi-Agent Session Management

When running parallel agents (subagents), bind sessions to prevent interference.

### Why Session Binding Matters

When multiple agents work in parallel, each accessing SAP through this MCP server:

- **Without binding:** Agents can accidentally use each other's sessions, corrupting data
- **With binding:** Each agent claims its own session, and warnings are logged if boundaries are crossed

### For Orchestrating Agents (Parent/Controller)

If you're dispatching subagents to work in parallel:

1. **Open dedicated sessions for each subagent:**

    ```
    sap_session_open(agent_id="subagent-orders")  # Returns session_id="s2"
    sap_session_open(agent_id="subagent-materials")  # Returns session_id="s3"
    ```

2. **Tell each subagent its session and agent_id:**
   When dispatching a subagent, include in its instructions:
    - "Use session='s2' and agent_id='subagent-orders' for all SAP tool calls"
    - The subagent MUST pass both parameters on every tool call

3. **Clean up when done:**
    ```
    sap_session_close(session="s2")  # Or sap_session_release to just unbind
    ```

### For Subagents (Worker Agents)

If you're a subagent working on an SAP task:

1. **You should have been given a session and agent_id by your parent**
    - Example: "Use session='s2' and agent_id='subagent-orders'"

2. **Pass BOTH parameters on EVERY SAP tool call:**

    ```
    sap_transaction("VA01", session="s2", agent_id="subagent-orders")
    sap_fill_form({"Customer": "12345"}, session="s2", agent_id="subagent-orders")
    sap_keyboard("Enter", session="s2", agent_id="subagent-orders")
    ```

3. **When finished, release your session:**
    ```
    sap_session_release(session="s2")
    ```

### Checking Session State

```
# See all sessions and who owns them
sap_session_list()
# Returns: [
#   SessionInfo(session_id="s1", agent_id=None),      # Primary, unbound
#   SessionInfo(session_id="s2", agent_id="subagent-orders"),
#   SessionInfo(session_id="s3", agent_id="subagent-materials")
# ]
```

### What Happens If You Make a Mistake

If an agent accesses a session bound to another agent:

- A WARNING is logged: "Session 's2' bound to 'subagent-orders' accessed by 'subagent-materials' via sap_fill_form"
- The operation STILL PROCEEDS (warnings don't block)
- This helps debug cross-talk issues

### Tools That Support agent_id

ALL session-aware tools support the agent_id parameter:

- sap_transaction, sap_keyboard, sap_fill_form, sap_set_field
- sap_get_screen_text, sap_get_form_fields, sap_read_table
- sap_se11_lookup, sap_se16_query, sap_se24_lookup, sap_se37_lookup, sap_se93_lookup
- browser_click, browser_fill, browser_navigate, etc.

### Best Practices

1. **Always bind sessions** when working with parallel agents
2. **Use descriptive agent_ids** like "order-processor" not "agent1"
3. **Pass agent_id on EVERY call** - don't skip it
4. **Release when done** to allow session reuse
5. **Check sap_session_list()** if unsure about session state
