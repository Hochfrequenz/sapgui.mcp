---
description: Find and understand a function module's signature using SE37
---

# Explore a Function Module

## Overview

This recipe shows how to look up an SAP function module's complete signature -- its import, export, changing, and tables parameters plus exceptions.

## Prerequisites

- SAP session is logged in and ready
- Authorization for SE37 (Function Builder)

## Steps

### Step 1: Look Up the Function Module

Use the specialized SE37 tool:

```
sap_se37_lookup(function_modules="FUNCTION_MODULE_NAME")
```

This returns structured data including:

- **Import parameters** -- inputs you must/can provide
- **Export parameters** -- outputs the FM returns
- **Changing parameters** -- parameters passed by reference (input and output)
- **Tables parameters** -- table-type inputs/outputs
- **Exceptions** -- error conditions the FM can raise

### Step 2: Find Function Modules by Keyword

If you don't know the exact name, search the catalog:

```
search_function_modules("keyword")
```

Or search by partial name:

```
search_function_modules("RFC_READ")
```

### Step 3: Understand Parameter Details

For each parameter, the tool returns:

- Parameter name
- Associated type (data element, structure, or table type)
- Whether it's optional or required
- Default value (if any)
- Description

Use `sap_se11_lookup` to inspect complex parameter types (structures/tables):

```
sap_se11_lookup(names="STRUCTURE_NAME", object_type="structure")
```

## Error Handling

### "Function module not found"

- Check spelling (FM names are uppercase)
- Use `search_function_modules("keyword")` to find the correct name
- The FM might be in a different namespace (e.g., `/NAMESPACE/FM_NAME`)

### "No authorization"

- User needs S_DEVELOP authorization or display access to the function group
