# IS-U/S4 Utilities Function Module & Class Catalog

## Overview

Extend the existing catalog system (transactions, tables) to include Function Modules and Classes specific to IS-U and S/4 Utilities. Data is scraped once via SE16 (names) and SE37/SE24 (details), stored as JSON, and exposed as searchable MCP resources.

## Data Models

### FunctionModuleInfo

```python
class FunctionModuleInfo(BaseModel):
    name: str                           # e.g. "ISU_CONSUMPTION_DETERMINE"
    description: str                    # Short text
    function_group: str                 # Function group
    area: str | None                    # "ISU", "ISU-EDM", "FICA", etc.
    is_rfc_enabled: bool                # Remote-enabled
    # Details from SE37:
    import_params: list[ParameterInfo]
    export_params: list[ParameterInfo]
    changing_params: list[ParameterInfo]
    tables_params: list[ParameterInfo]
    exceptions: list[str]
    retrieved_at: datetime
```

### ClassInfo

```python
class ClassInfo(BaseModel):
    name: str                           # e.g. "CL_ISU_BILLING"
    description: str                    # Short text from SEOCLASSTX
    class_type: str                     # "class" | "interface"
    is_remote: bool                     # Remote flag
    area: str | None                    # "ISU", "FICA", "EDM"
    # Details from SE24:
    methods: list[MethodInfo]
    attributes: list[AttributeInfo]
    interfaces: list[str]
    retrieved_at: datetime
```

### Catalog Containers

```python
class FunctionModuleCatalog(BaseModel):
    function_modules: list[FunctionModuleInfo]
    source_system: str | None
    language: str | None
    last_updated: datetime | None
    total_count: int

class ClassCatalog(BaseModel):
    classes: list[ClassInfo]
    source_system: str | None
    language: str | None
    last_updated: datetime | None
    total_count: int
```

## File Structure

```
src/sapguimcp/
├── data/
│   ├── transactions.json      # (existing)
│   ├── tables.json            # (existing)
│   ├── function_modules.json  # NEW - scraped FMs
│   └── classes.json           # NEW - scraped classes
├── catalog/
│   ├── models.py              # + FunctionModuleInfo, ClassInfo
│   ├── loader.py              # + load_fm_catalog(), load_class_catalog()
│   ├── search.py              # + search_function_modules(), search_classes()
│   └── scraper.py             # + scrape_function_modules(), scrape_classes()
```

## Scraping Configuration

### Prefixes

**Function Modules:**

- `ISU_*` - Core IS-U (billing, device mgmt, meter reading)
- `FKK_*` - FICA (Contract Accounts Receivable/Payable)
- `BAPI_ISU*` - IS-U BAPIs (Partner, Account, POD, Move-in/out)
- `BAPI_CTRAC*` - Contract Account BAPIs
- `BAPI_FKK*` - FICA BAPIs
- `EDM_*` - Energy Data Management
- `IDEX*` - Intercompany Data Exchange (retail/distribution)

**Classes:**

- `CL_ISU_*` - IS-U classes
- `CL_FKK*` - FICA classes
- `CL_EDM_*` - EDM classes
- `CL_IDEX*` - IDEX classes
- `IF_ISU_*` - IS-U interfaces
- `IF_FKK*` - FICA interfaces
- `IF_EDM*` - EDM interfaces

### Area Detection

```python
def detect_fm_area(name: str) -> str | None:
    if name.startswith("ISU_EDM_"): return "ISU-EDM"
    if name.startswith("ISU_DM_"): return "ISU-DM"
    if name.startswith("ISU_"): return "ISU"
    if name.startswith("FKK_"): return "FICA"
    if name.startswith("BAPI_ISU"): return "ISU-BAPI"
    if name.startswith("BAPI_CTRAC"): return "FICA-BAPI"
    if name.startswith("EDM_"): return "EDM"
    if name.startswith("EM_"): return "EM"
    return None
```

## Scraping Workflow

### Two-Stage Process

1. **SE16 Query (fast)** - Get list of names
    - TFDIR with prefix filter → FM names
    - SEOCLASS with prefix filter → Class names

2. **Detail Lookup in Batches (slow, comprehensive)**
    - SE37 Tool: 10 FMs per call → full signatures
    - SE24 Tool: 10 classes per call → methods, attributes, interfaces

### Incremental Commits

```
for batch in chunks(fm_names, size=10):
    1. SE37 Lookup for 10 FMs
    2. Merge into function_modules.json
    3. git commit -m "catalog: add FMs {batch[0]}...{batch[-1]}"

for batch in chunks(class_names, size=10):
    1. SE24 Lookup for 10 classes
    2. Merge into classes.json
    3. git commit -m "catalog: add classes {batch[0]}...{batch[-1]}"
```

### Resume Logic

```python
def get_missing_fms(all_names: list[str], catalog: FMCatalog) -> list[str]:
    existing = {fm.name for fm in catalog.function_modules}
    return [n for n in all_names if n not in existing]
```

## MCP Integration

### New Tools

```python
@mcp.tool()
def search_function_modules(query: str, area: str | None = None, limit: int = 10):
    """Search IS-U/FICA function modules by name or description."""

@mcp.tool()
def search_classes(query: str, area: str | None = None, limit: int = 10):
    """Search IS-U/FICA classes by name or description."""
```

### Area Filter Values

- `ISU` - Core IS-U
- `ISU-EDM` - Energy Data Management
- `ISU-DM` - Device Management
- `FICA` - Contract Accounts
- `BAPI` - BAPIs

## Sources

- [SAP IS-U Function Modules](https://www.tcodesearch.com/sap-fms/FI-CA/list)
- [SAP IS-U BAPIs](https://www.se80.co.uk/sapfms/b/bapi/bapi_isupartner_getlist.htm)
- [SAP EDM Documentation](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/021b182b0c47416c8fafed67ebfd78a9/de8ace53118d4308e10000000a174cb4.html)
