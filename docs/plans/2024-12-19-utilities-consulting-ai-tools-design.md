# Design: AI Agent Tools for Utilities Consulting

**Date:** 2024-12-19
**Status:** Approved for implementation

## Overview

This document describes the MCP tools and skills architecture for AI agents supporting
SAP IS-U and S/4HANA Utilities consulting work. The design enables AI agents to:

1. Create test data (business partners, contracts, devices, meter readings)
2. Verify configuration (customizing settings, cross-system comparison)
3. Execute repetitive transactions (mass changes, batch operations)
4. Generate documentation (screen captures, configuration exports)

## Design Principles

### Thin Tools, Rich Skills

Since consultants typically only have SAP GUI access (no direct API/BAPI calls),
tools are thin wrappers around GUI actions. Domain knowledge lives in skills
(markdown documentation) that guide how to use tools together.

### Adaptive Field Discovery

SAP screens vary by system configuration, customizing, and language. Skills use
adaptive discovery patterns:

1. Call `sap_get_screen_text()` to read all visible labels
2. Match fields by proximity to known label patterns (DE/EN)
3. Fall back to `browser_snapshot()` for element IDs when needed

### German Utilities Focus

Primary focus on German energy market requirements:

- IDEX/IDXGC framework for market communication
- GPKE, MaBiS, WiM, GeLi Gas processes
- Market partner roles (LF, NB, MSB, BKV)
- MaLo/MeLo (Markt-/Messlokation) structures

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  SKILLS (Domain Knowledge - Markdown files)               │
│  - Adaptive workflows with DE/EN label discovery          │
│  - German utilities frameworks (IDXGC, GPKE, MaBiS)       │
│  - Error handling and recovery patterns                   │
│  - Transaction sequences and field mappings               │
└────────────────────────────────────────────────────────────┘
                            ↓ guides
┌────────────────────────────────────────────────────────────┐
│  SAP TOOLS (New - to be implemented)                      │
│  Session:    sap_session_status                           │
│  Navigation: sap_press_key                                 │
│  Reading:    sap_get_screen_text, sap_read_table,         │
│              sap_read_status_bar, sap_get_screen_info     │
└────────────────────────────────────────────────────────────┘
                            ↓ uses
┌────────────────────────────────────────────────────────────┐
│  EXISTING TOOLS                                           │
│  SAP:     sap_login, sap_transaction, sap_keepalive_*     │
│  Browser: browser_snapshot, browser_click, browser_fill,  │
│           browser_keyboard, browser_get_html, etc.        │
└────────────────────────────────────────────────────────────┘
```

## New MCP Tools

### Session Management

#### `sap_session_status`

Check if SAP session is still active before performing actions.

```python
async def sap_session_status() -> str:
    """
    Check the current SAP session status.

    Returns:
        Status message containing one of:
        - "active": Session is alive and responsive
        - "timed_out": Session has timed out
        - "logged_off": User has been logged off
        - "unknown": Cannot determine status
    """
```

**Use case:** Agent pauses to ask user a question, then checks session before continuing.

### Navigation & Actions

#### `sap_press_key`

Send keyboard shortcuts to SAP Web GUI.

```python
async def sap_press_key(key: str) -> str:
    """
    Send a keyboard shortcut to SAP Web GUI.

    Args:
        key: Keyboard shortcut. Examples:
            - "F3" (Back)
            - "F4" (Search Help)
            - "F8" (Execute)
            - "Ctrl+S" (Save)
            - "Ctrl+Y" (Select text mode)
            - "Enter"
            - "Escape"

    Returns:
        Confirmation message or error description.
    """
```

**Use case:** Execute reports (F8), navigate back (F3), save (Ctrl+S).

### Reading Data

#### `sap_get_screen_text`

Extract all readable text from current screen for adaptive field discovery.

```python
async def sap_get_screen_text() -> str:
    """
    Get all readable text from the current SAP screen.

    Returns:
        Structured text content including:
        - Screen title
        - Field labels and values
        - Button labels
        - Status messages
        - Tab labels

    The agent can parse this to identify field positions
    and adapt to different system configurations.
    """
```

**Use case:** Discover field labels to fill forms adaptively across different SAP systems.

#### `sap_read_table`

Read data from ALV grids, step loops, and list displays.

```python
async def sap_read_table(
    start_row: int = 1,
    end_row: Optional[int] = None
) -> str:
    """
    Read rows from an ALV grid or table on the current screen.

    Args:
        start_row: First row to read (1-indexed)
        end_row: Last row to read (None = all visible rows)

    Returns:
        JSON-formatted table data with column headers and values.
        Returns error message if no table found.
    """
```

**Use case:** Extract job list from SM37, transaction codes from SE93, process documents from /IDXGC/PDOCMON01.

#### `sap_read_status_bar`

Read success/error/warning messages from SAP status bar.

```python
async def sap_read_status_bar() -> str:
    """
    Read the current message from SAP's status bar.

    Returns:
        JSON with:
        - type: "S" (success), "E" (error), "W" (warning), "I" (info)
        - message: The status bar text

    Returns empty/none if no message displayed.
    """
```

**Use case:** Verify save succeeded, capture error messages, get created document numbers.

#### `sap_get_screen_info`

Get technical information about current screen.

```python
async def sap_get_screen_info() -> str:
    """
    Get technical information about the current SAP screen.

    Returns:
        JSON with:
        - transaction: Current transaction code
        - program: ABAP program name
        - dynpro: Screen number
        - title: Window title
        - gui_status: GUI status name
    """
```

**Use case:** Verify correct screen loaded, debug navigation issues.

## Skills Structure

### Directory Layout

```
src/sapguimcp/skills/
├── README.md                    # How to create skills
├── examples/
│   ├── general_navigation.md    # Basic SAP navigation (existing)
│   ├── create_business_partner_bp.md
│   ├── create_contract_account_caa1.md
│   └── monitor_process_documents_idxgc.md
└── (future skills organized by module)
```

### Skill Template

Each skill follows this structure:

1. **Overview** - What the skill accomplishes
2. **Prerequisites** - Required authorizations and master data
3. **Adaptive Field Discovery** - DE/EN label reference table
4. **Workflow** - Step-by-step with tool calls
5. **Error Handling** - Common errors and recovery
6. **German Utilities Specifics** - IS-U/IDXGC notes
7. **Related Transactions** - Links to other skills
8. **Example Dialogue** - How agent-user conversation looks
9. **Sources** - Documentation links

### Planned Skills

#### Test Data Creation

| Skill                   | Transaction | Priority |
| ----------------------- | ----------- | -------- |
| Create Business Partner | BP          | Done     |
| Create Contract Account | CAA1        | Done     |
| Create Contract         | EC50N/EC50E | High     |
| Create Installation     | ES30        | High     |
| Create Device           | EG30        | High     |
| Install Device          | EG35        | Medium   |
| Create Meter Reading    | EL28        | Medium   |

#### Configuration Verification

| Skill                  | Transaction | Priority |
| ---------------------- | ----------- | -------- |
| Display Table Contents | SE16/SE16N  | High     |
| Check Rate Category    | EC90        | Medium   |
| Display Customizing    | SPRO        | Medium   |

#### German Market Communication

| Skill                     | Transaction      | Priority |
| ------------------------- | ---------------- | -------- |
| Monitor Process Documents | /IDXGC/PDOCMON01 | Done     |
| Display Market Partner    | /IDXGC/BPM       | Medium   |
| Message Monitoring        | /IDXGC/MSG_MON   | Medium   |

## Testing Strategy

### Test Requirements

1. Tests must work on **any bare-metal SAP system** without specific customizing
2. Use universal transactions: SE16, SM37, SE93, SU3, SM21
3. Language-aware assertions using `SAP_LANGUAGE` environment variable
4. Build on existing `sap_mcp_client` fixture pattern

### Test Cases per Tool

#### `sap_session_status`

- Test 1: Status is "active" after login
- Test 2: Returns valid state value

#### `sap_press_key`

- Test 1: F3 navigates back from SE16
- Test 2: F8 triggers execution (error expected without input)

#### `sap_read_table`

- Test 1: Read jobs from SM37 (always has system jobs)
- Test 2: Read transaction codes from SE93 with "SE\*" filter

#### `sap_get_screen_text`

- Test 1: SE16 screen contains "Table" / "Tabelle" labels
- Test 2: Error message captured after invalid input

#### `sap_read_status_bar`

- Test 1: Returns structured message after navigation
- Test 2: Captures error type for invalid transaction

#### `sap_get_screen_info`

- Test 1: Returns transaction code for SE16
- Test 2: Returns different transaction code for SM37

## Implementation Plan

### Phase 1: Core Tools

1. `sap_press_key` - Extend navigation capabilities
2. `sap_get_screen_text` - Enable adaptive field discovery
3. `sap_read_status_bar` - Capture operation results

### Phase 2: Data Access

4. `sap_read_table` - Extract tabular data
5. `sap_get_screen_info` - Technical screen info
6. `sap_session_status` - Session health checks

### Phase 3: Skills & Testing

7. Integration tests for all tools
8. Additional skills for IS-U workflows
9. Documentation updates

## Consulting Use Cases

### Supervised Automation

Agent proposes actions, consultant reviews:

- Agent: "I'll create BP with these values: [shows data]"
- Consultant: "Approved" / "Change X to Y"
- Agent: Executes with tools, reports result

### Task Delegation

Consultant gives task, agent executes:

- Consultant: "Create 10 test customers in mandant 100"
- Agent: Uses skills to create BP, CA, Contract for each
- Agent: Reports summary of created objects

### Configuration Documentation

Agent extracts and documents:

- Consultant: "Document the billing schema configuration"
- Agent: Navigates SPRO, reads tables, captures screens
- Agent: Generates markdown documentation

## Future Considerations

### Scenario-Level Tools

Once domain tools are stable, consider higher-level tools:

```python
create_test_customer_scenario(
    scenario_type="residential_single_meter",
    customer_data={...}
)
```

These would compose multiple skill executions.

### SAP Help Portal Integration

Enrich skills with official documentation:

- Exact field technical names
- Screen numbers (dynpros)
- Required field indicators
- Field validation rules

### S/4HANA Cloud Adaptation

Current design targets on-premise SAP GUI. For S/4HANA Cloud:

- Fiori app navigation patterns
- OData service integration where available
- Different screen structures

## Sources

- [SAP Community: How to create a BP](https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-members/how-to-create-a-bp-business-partner/ba-p/13394450)
- [SAP Community: BP Complete Configuration Guide](https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-members/business-partner-bp-complete-configuration-guide-in-sap-s4-hana/ba-p/14021389)
- [SAP TCodes: CAA1 Create Contract Account](https://www.sap-tcodes.org/tcode/caa1.html)
- [SAP Learning: Market Communication Architecture](https://learning.sap.com/learning-journeys/transitioning-to-sap-s-4hana-for-utilities/analyzing-and-applying-sap-market-communication-architecture-for-utilities)
- [SAP Community: Introducing APE](https://community.sap.com/t5/sap-for-utilities-blog-posts/introducing-application-process-engine-ape-latest-sap-solution-for-choice/ba-p/13548853)
