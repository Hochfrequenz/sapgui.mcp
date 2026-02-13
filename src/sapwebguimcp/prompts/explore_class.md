---
description: Look up an ABAP class or interface with methods, attributes, and events using SE24
---

# Explore a Class or Interface

## Overview

This recipe shows how to look up an ABAP class or interface to understand its methods, attributes, and events.

## Prerequisites

- SAP session is logged in and ready
- Authorization for SE24 (Class Builder)

## Steps

### Step 1: Look Up the Class or Interface

Use the specialized SE24 tool:

```
sap_se24_lookup(classes="CLASS_OR_INTERFACE_NAME")
```

This returns structured data including:

- **Methods** -- with parameters, visibility, and descriptions
- **Attributes** -- instance and static attributes with types
- **Events** -- events the class can raise
- **Interfaces** -- interfaces the class implements

### Step 2: Find Classes by Keyword

If you don't know the exact name, search the catalog:

```
search_classes("keyword")
```

Naming conventions (standard SAP, same in every system):

- `CL_*` -- SAP-delivered classes
- `IF_*` -- SAP-delivered interfaces
- `ZCL_*` / `ZIF_*` -- customer-developed classes/interfaces (Z namespace)

### Step 3: Inspect Method Parameters

The tool returns method signatures with parameter details. For complex parameter types (structures, tables), use `sap_se11_lookup` to inspect the type definition:

```
sap_se11_lookup(names="TYPE_NAME", object_type="structure")
```

## Error Handling

### "Class/interface not found"

- Check spelling (names are uppercase)
- Use `search_classes("keyword")` to find the correct name
- Distinguish between classes (`CL_*`) and interfaces (`IF_*`)

### "No authorization"

- User needs display access to the class or its development package
