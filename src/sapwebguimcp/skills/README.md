# Skills

Skills are **reusable workflows and best practices** that help Claude perform complex SAP operations effectively. Unlike
tools (which are callable functions), skills are **documentation and patterns** that guide how to use tools together.

## What are Skills?

Skills provide:

1. **Step-by-step workflows** for complex operations
2. **Best practices** for handling common SAP scenarios
3. **Error recovery patterns** for when things go wrong
4. **Domain knowledge** about SAP transactions and screens

## Directory Structure

```
skills/
├── __init__.py           # Package definition
├── README.md             # This file (skill creation guide)
└── examples/             # Example skill files
    ├── create_sales_order.md
    ├── vendor_master_data.md
    └── ...
```

## Creating a Skill

### 1. Create a Markdown File

Skills are written as Markdown files that Claude can read and follow:

```markdown
# Skill: Create Sales Order (VA01)

## Overview

This skill describes how to create a sales order in SAP using transaction VA01.

## Prerequisites

- User must be logged into SAP
- User needs authorization for transaction VA01

## Workflow

### Step 1: Start Transaction

Use `sap_transaction` with tcode "VA01" to open the sales order creation screen.

### Step 2: Enter Header Data

Fill in the required fields:

- Order Type (AUART)
- Sales Organization (VKORG)
- Distribution Channel (VTWEG)
- Division (SPART)

Use `browser_fill` or `browser_click` if the standard fields don't work.

### Step 3: Enter Customer

- Sold-to Party (KUNNR)
- Ship-to Party (if different)

### Step 4: Enter Line Items

For each item:

- Material Number (MATNR)
- Quantity (KWMENG)
- Unit of Measure (VRKME)

### Step 5: Save

Use keyboard shortcut Ctrl+S or find the Save button.

## Error Handling

### "No authorization"

- Check user has VA01 authorization
- Try running SU53 to see missing authorizations

### "Material not found"

- Verify material number
- Check material is active for the sales organization

## Example Dialogue

User: Create a sales order for customer 1000 with 10 units of material ABC123

Claude:

1. [calls sap_transaction("VA01")]
2. [fills order type, sales org, etc.]
3. [enters customer and material]
4. [saves the order]
5. Reports the order number back to the user
```

### 2. Skill File Naming

Use descriptive names with transaction codes where applicable:

- `create_sales_order_va01.md`
- `display_material_mm03.md`
- `change_vendor_xk02.md`
- `general_navigation.md`

### 3. Skill Sections

Every skill should include:

| Section              | Purpose                           |
| -------------------- | --------------------------------- |
| **Overview**         | What the skill accomplishes       |
| **Prerequisites**    | What must be true before starting |
| **Workflow**         | Step-by-step instructions         |
| **Error Handling**   | Common errors and how to recover  |
| **Example Dialogue** | How a conversation might look     |

## Using Skills with Claude

Claude can read skill files using the `browser_evaluate` or file system tools if available. In practice, skills are most
useful when:

1. **Included in system prompts** - Add relevant skills to the MCP server's context
2. **Referenced by users** - "Follow the sales order creation skill"
3. **Discovered dynamically** - Claude can search for relevant skills

## Example Skills to Create

### Transaction-Specific Skills

| Skill                 | Transaction | Description                   |
| --------------------- | ----------- | ----------------------------- |
| Create Sales Order    | VA01        | Standard sales order creation |
| Display Material      | MM03        | View material master data     |
| Create Purchase Order | ME21N       | Purchase order creation       |
| Create Vendor         | XK01        | Vendor master creation        |
| User Administration   | SU01        | Create/modify users           |

### Cross-Transaction Skills

| Skill             | Description                        |
| ----------------- | ---------------------------------- |
| Navigation Basics | How to navigate SAP Web GUI        |
| Table Handling    | Working with ALV grids and tables  |
| Search Help       | Using F4 search help               |
| Error Messages    | Understanding and resolving errors |
| Print/Export      | Getting data out of SAP            |

## Best Practices for Skills

### 1. Be Specific About Selectors

```markdown
## Step 2: Fill Sales Organization

The sales organization field is typically found at:

- ID: `M0_R1_C2_txt` (varies by SAP version)
- Label: "Sales Org." or "Verkaufsorg."
- Use `browser_fill` with selector `input[id*="VKORG"]`
```

### 2. Include Recovery Steps

```markdown
## Error Recovery

If the OK-Code field is not visible:

1. Use `browser_snapshot` to see current page state
2. Look for settings/gear icon
3. Enable "Transaction Field" or "OK-Code Field"
4. Retry the transaction
```

### 3. Provide Visual Cues

```markdown
## Identifying the Screen

After entering VA01, you should see:

- Title bar: "Create Sales Order: Initial Screen"
- Fields for Order Type, Sales Org, Dist. Channel
- Empty grid for line items (not visible yet)
```

### 4. Handle Variants

```markdown
## Screen Variants

Different SAP configurations may show different fields:

### Standard View

- Order Type
- Sales Organization
- Distribution Channel
- Division

### Custom View (Company XYZ)

- Order Type
- Customer (pre-filled)
- Reference Document

Use `browser_snapshot` to identify which view is active.
```

## Skill Discovery

To help Claude find relevant skills:

1. **Index file** - Create `skills/index.md` listing all skills with keywords
2. **Tags** - Add tags at the top of each skill file
3. **Cross-references** - Link related skills

Example index:

```markdown
# Skill Index

## Sales (SD)

- [Create Sales Order](./create_sales_order_va01.md) - VA01, order, customer
- [Sales Order Display](./display_sales_order_va03.md) - VA03, lookup

## Materials (MM)

- [Material Display](./display_material_mm03.md) - MM03, material, product

## Keywords

| Keyword  | Skills                              |
| -------- | ----------------------------------- |
| customer | create_sales_order, customer_master |
| material | display_material, create_material   |
```

## Contributing Skills

When creating skills for this project:

1. Follow the template structure
2. Test with actual SAP systems when possible
3. Include real selector examples
4. Document error cases you encounter
5. Submit via pull request with tests if applicable
