# Transaction Catalog Feature Plan

This document describes the plan to scrape SAP transaction codes and expose them as MCP resources for AI-assisted SAP navigation.

## Progress (Updated 2026-01-12)

| Phase                            | Status      | Notes                                 |
| -------------------------------- | ----------- | ------------------------------------- |
| Phase 1: Scrape Transaction Data | ✅ Complete | `scrape_tstc()`, `enrich_with_se93()` |
| Phase 2: Create MCP Resource     | ✅ Complete | `search_transactions` tool registered |
| Phase 3: Search Implementation   | ✅ Complete | Keyword matching with scoring         |
| Phase 4: Integration & Testing   | ✅ Complete | Unit tests added, tools verified      |

### Files Created

```
src/sapguimcp/catalog/
├── __init__.py      # Module exports
├── models.py        # TransactionInfo, TransactionCatalog
├── scraper.py       # scrape_tstc(), enrich_with_se93()
├── loader.py        # load_catalog(), get_catalog()
└── search.py        # search_transactions()

src/sapguimcp/tools/
└── catalog_tools.py # MCP tool registration

unittests/
└── test_catalog.py  # 50 unit tests for catalog module
```

### Catalog Status

**Catalog populated with 3,884 transactions** from the following prefixes:

- VA*, VL*, VF\* (Sales & Distribution)
- ME*, MM*, MB\* (Materials Management)
- FI*, FB* (Financial Accounting)
- CO\* (Controlling)
- SE*, SM* (Basis/Development)
- SU\* (User Administration)
- SD*, XD*, XK\* (Master Data)
- PP*, WE* (Production/Warehouse)
- /US4G*, E* (Utilities/General)
- BP*, MR* (Business Partner/Material)

### Usage

Claude can now use the following tools:

- `search_transactions("VA01")` - Find by exact transaction code
- `search_transactions("create order")` - Find by description keywords
- `search_transactions("VA")` - Find by code prefix
- `search_transactions("purchase", area="MM")` - Filter by SAP module
- `get_transaction_catalog_status()` - Check catalog statistics

### Future Enhancements

1. **SE93 Enrichment**: Run `enrich_with_se93()` to add full transaction metadata
2. **More Prefixes**: Add additional transaction code ranges as needed
3. **English Descriptions**: Re-scrape with English login for better search

## Background

The goal is to build a transaction catalog that helps Claude (and other LLMs) understand which SAP transactions exist and what they do, so it can suggest appropriate transactions for user tasks.

### Current State

We already have:

- `sap_se93_lookup` tool that fetches individual transaction metadata (program, screen, description)
- `sap_se16_query` tool that can query TSTC table (transaction codes table)
- Parsers for SE93 screens in both EN and DE

### Target Outcome

1. **A static transaction catalog** stored as an MCP resource (JSON file)
2. **A Python search wrapper** that allows Claude to find relevant transactions by keyword/description
3. **Optional: periodic refresh capability** to update the catalog from live SAP

## Implementation Plan

### Phase 1: Scrape Transaction Data

**Goal:** Use SE16 + SE93 to collect transaction metadata and store in a JSON file.

#### Step 1.1: Query TSTC table via SE16N

- Use `sap_se16_query(table="TSTC", max_hits=9999)` to get all transaction codes
- TSTC columns: TCODE, PGMNA (program), DESSION (screen), etc.
- Save raw output to `data/tstc_raw.json`

#### Step 1.2: Enrich with SE93 descriptions

- For each transaction in TSTC, call `sap_se93_lookup(tcode)` to get:
    - Transaction description (human-readable)
    - Transaction type (dialog, report, etc.)
    - GUI support flags
- This is slow (~5-10 sec per transaction), so:
    - Implement batch processing with progress tracking
    - Cache results incrementally
    - Consider running overnight

#### Step 1.3: Merge and deduplicate

- Combine TSTC data with SE93 enrichments
- Create unified schema:

```python
class TransactionInfo:
    tcode: str           # e.g., "VA01"
    description: str     # e.g., "Create Sales Order"
    program: str         # e.g., "SAPMV45A"
    screen: int | None   # e.g., 100
    type: str            # "dialog", "report", "parameter", etc.
    gui_support: bool
    area: str | None     # Extracted from tcode prefix (MM, SD, FI, etc.)
```

#### Step 1.4: Store as static JSON

- Write to `src/sapguimcp/data/transactions.json`
- Include metadata (last_updated, source_system, language)

### Phase 2: Create MCP Resource

**Goal:** Expose the transaction catalog as an MCP resource.

#### Step 2.1: Define resource endpoint

```python
@mcp.resource("sap://transactions")
async def get_transactions() -> list[TransactionInfo]:
    """Return all known SAP transactions."""
    return load_transaction_catalog()
```

#### Step 2.2: Add search capability as a tool

```python
@mcp.tool()
async def search_transactions(
    query: str,
    area: str | None = None,  # Filter by module (MM, SD, FI, etc.)
    limit: int = 10
) -> list[TransactionInfo]:
    """
    Search for SAP transactions by description or code.

    Use this when user asks things like:
    - "How do I create a purchase order?"
    - "What transaction displays customer master?"
    - "Show me material management transactions"
    """
    ...
```

### Phase 3: Search Implementation

**Goal:** Fast, fuzzy search over transaction catalog.

#### Step 3.1: Basic keyword matching

- Split query into tokens
- Match against tcode (exact/prefix) and description (contains)
- Score by match quality

#### Step 3.2: Area detection

- Parse tcode prefixes to identify SAP module:
    - MM\* = Materials Management
    - SD\* = Sales & Distribution
    - FI\* = Financial Accounting
    - VA\* = Sales documents
    - ME\* = Purchasing
    - etc.
- Store area in TransactionInfo for filtering

#### Step 3.3: Fuzzy matching (optional enhancement)

- Use rapidfuzz or similar for typo-tolerant matching
- Weight matches: exact tcode > prefix > description contains

### Phase 4: Integration & Testing

#### Step 4.1: Unit tests

- Test search with various queries
- Test area filtering
- Test edge cases (empty catalog, no matches)

#### Step 4.2: Integration tests

- Test resource endpoint returns valid data
- Test search tool with live SAP data

## File Structure

```
src/sapguimcp/
├── data/
│   └── transactions.json      # Static transaction catalog
├── catalog/
│   ├── __init__.py
│   ├── models.py              # TransactionInfo model
│   ├── loader.py              # Load catalog from JSON
│   ├── search.py              # Search implementation
│   └── scraper.py             # One-time scraping script
└── tools/
    └── catalog_tools.py       # MCP tool registration
```

## Scraping Strategy

Since we have ~thousands of transactions and SE93 lookup takes ~5-10 sec each:

1. **Start with a subset:** Scrape common modules first (VA*, ME*, MM*, SD*, FI*, CO*, HR\*)
2. **Incremental updates:** Store progress, allow resuming
3. **Prioritize by usage:** If usage data available, scrape most-used first
4. **Consider pre-built catalog:** SAP provides transaction lists in documentation

### Estimated Scraping Time

- 1000 transactions × 7 sec each = ~2 hours
- 5000 transactions × 7 sec each = ~10 hours
- Run overnight with output_file to avoid context overflow

## Open Questions

1. **Which transactions to include?**
    - All from TSTC? (could be 50,000+)
    - Only standard SAP (S\* prefix)?
    - Only commonly used (curated list)?

2. **Language handling?**
    - Store descriptions in multiple languages?
    - Use user's login language at scrape time?

3. **Refresh strategy?**
    - One-time scrape is simplest
    - Periodic refresh via CLI command?
    - On-demand via MCP tool?

## Quick Start for Next Session

```bash
# 1. Start from this branch
git checkout feat/transaction-catalog

# 2. First, test that SE16 query works
# (Run SAP, login, then test basic query)

# 3. Scrape initial data
# Create scraper.py, run it to collect transactions

# 4. Implement search tool
# Add MCP tool registration

# 5. Test
tox -e integration_tests
```

## Related Files

- `src/sapguimcp/tools/se16_tools.py` - SE16N query tool
- `src/sapguimcp/tools/se93_tools.py` - SE93 lookup tool
- `src/sapguimcp/parsers/se93_parser.py` - SE93 screen parser
- `src/sapguimcp/models.py` - Existing data models
