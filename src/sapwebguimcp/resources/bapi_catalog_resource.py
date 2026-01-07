"""MCP resource for IS-U / S/4 Utilities object catalog.

Provides searchable resources for:
- BAPIs and Function Modules
- ABAP Classes
- Reports and Transactions
- Tables
- Namespaces

All objects are marked as either 'verified_in_system' (extracted from SAP) or
from 'source: online_research' (unverified, from documentation).
"""

import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

__all__ = ["register_bapi_catalog_resources"]

# Load catalog from data directory
DATA_DIR = Path(__file__).parent.parent / "data"
CATALOG_FILE = DATA_DIR / "bapi_catalog.json"


def _load_catalog() -> dict[str, Any]:
    """Load the utilities catalog from JSON file."""
    if not CATALOG_FILE.exists():
        return {"error": "Catalog file not found", "bapis": [], "categories": {}}
    with open(CATALOG_FILE, encoding="utf-8") as f:
        return json.load(f)


def register_bapi_catalog_resources(mcp: FastMCP) -> None:
    """Register IS-U/S4U object catalog resources with the MCP server."""

    @mcp.resource("bapi://catalog")
    def get_full_catalog() -> dict[str, Any]:
        """
        Get the complete IS-U / S/4 Utilities object catalog.

        Returns the full catalog including:
        - metadata (version, extraction statistics, how_to_update)
        - namespaces (SAP namespaces like /IDXGC/, /APE/, etc.)
        - tables (IS-U tables grouped by domain)
        - categories (functional areas with key BAPIs/FMs)
        - bapis (verified and unverified BAPIs)
        - function_modules (non-BAPI function modules)
        - classes (ABAP classes with counts and important classes)
        - reports (grouped by functional area)
        - transactions (grouped by functional area)
        - workflows (common SAP workflow patterns)

        NOTE: Objects with 'verified_in_system: true' were extracted from SAP.
        Objects with 'source: online_research' are unverified and may not exist
        in your specific system.
        """
        return _load_catalog()

    @mcp.resource("bapi://catalog/categories")
    def get_categories() -> dict[str, Any]:
        """
        Get the list of functional categories.

        Each category includes:
        - name: Human-readable name
        - description: What this category covers
        - prefix_patterns: Naming patterns for objects in this category
        - related_tables: Key SAP tables
        - key_bapis/key_function_modules: Most important objects
        """
        catalog = _load_catalog()
        return catalog.get("categories", {})

    @mcp.resource("bapi://catalog/category/{category_id}")
    def get_category_details(category_id: str) -> dict[str, Any]:
        """
        Get all objects for a specific category.

        Args:
            category_id: The category ID (e.g., 'equipment', 'billing', 'meter_reading')

        Returns:
            Category info plus all BAPIs, function modules, and classes in that category.
        """
        catalog = _load_catalog()
        categories = catalog.get("categories", {})

        if category_id not in categories:
            return {
                "error": f"Category '{category_id}' not found",
                "available_categories": list(categories.keys())
            }

        category_info = categories[category_id]
        bapis = [b for b in catalog.get("bapis", []) if b.get("category") == category_id]
        fms = [f for f in catalog.get("function_modules", []) if f.get("category") == category_id]

        return {
            "category": category_info,
            "bapis": bapis,
            "function_modules": fms,
            "total_count": len(bapis) + len(fms)
        }

    @mcp.resource("bapi://catalog/bapi/{bapi_name}")
    def get_bapi_details(bapi_name: str) -> dict[str, Any]:
        """
        Get details for a specific BAPI or function module by name.

        Args:
            bapi_name: The BAPI/FM name (e.g., 'BAPI_EQUI_CREATE', 'ISU_S_CONNOBJ_CREATE')

        Returns:
            Full details including parameters, usage notes, verification status.
            'verified_in_system: true' means extracted from SAP.
            'source: online_research' means unverified.
        """
        catalog = _load_catalog()
        name_upper = bapi_name.upper()

        # Search in BAPIs
        for bapi in catalog.get("bapis", []):
            if bapi.get("name", "").upper() == name_upper:
                return {"found": True, "type": "bapi", "verified": bapi.get("verified_in_system", False), "object": bapi}

        # Search in function modules
        for fm in catalog.get("function_modules", []):
            if fm.get("name", "").upper() == name_upper:
                return {"found": True, "type": "function_module", "verified": fm.get("verified_in_system", False), "object": fm}

        return {
            "found": False,
            "error": f"Object '{bapi_name}' not found in catalog",
            "hint": "Use SE37 in SAP to search for function modules not in the catalog"
        }

    @mcp.resource("bapi://catalog/search/{pattern}")
    def search_all_objects(pattern: str) -> dict[str, Any]:
        """
        Search across ALL object types by name or description pattern.

        Args:
            pattern: Search pattern (case-insensitive, partial match)
                     Examples: 'equi', 'meter', 'partner', 'billing'

        Returns:
            Matching objects from all categories:
            - bapis, function_modules, classes, reports, tables, namespaces
        """
        catalog = _load_catalog()
        pattern_lower = pattern.lower()

        results = {
            "pattern": pattern,
            "bapis": [],
            "function_modules": [],
            "classes": [],
            "reports": [],
            "tables": [],
            "namespaces": [],
            "categories": []
        }

        # Search BAPIs
        results["bapis"] = [
            b for b in catalog.get("bapis", [])
            if pattern_lower in b.get("name", "").lower()
            or pattern_lower in b.get("description", "").lower()
        ]

        # Search function modules
        results["function_modules"] = [
            f for f in catalog.get("function_modules", [])
            if pattern_lower in f.get("name", "").lower()
            or pattern_lower in f.get("description", "").lower()
        ]

        # Search classes (from important_classes list)
        classes_data = catalog.get("classes", {})
        important_classes = classes_data.get("important_classes", [])
        results["classes"] = [
            c for c in important_classes
            if pattern_lower in c.get("name", "").lower()
            or pattern_lower in c.get("description", "").lower()
        ]

        # Search reports
        reports = catalog.get("reports", {})
        for area, area_reports in reports.items():
            for report_name, report_info in area_reports.items():
                if pattern_lower in report_name.lower() or pattern_lower in report_info.get("description", "").lower():
                    results["reports"].append({"name": report_name, "area": area, **report_info})

        # Search tables
        tables = catalog.get("tables", {})
        for domain, domain_tables in tables.items():
            for table_name, table_info in domain_tables.items():
                if isinstance(table_info, dict):
                    if pattern_lower in table_name.lower() or pattern_lower in table_info.get("description", "").lower():
                        results["tables"].append({"name": table_name, "domain": domain, **table_info})

        # Search namespaces
        namespaces = catalog.get("namespaces", {})
        for ns_name, ns_info in namespaces.items():
            if pattern_lower in ns_name.lower() or pattern_lower in ns_info.get("description", "").lower() or pattern_lower in ns_info.get("name", "").lower():
                results["namespaces"].append({"namespace": ns_name, **ns_info})

        # Search categories
        categories = catalog.get("categories", {})
        for cat_id, cat_info in categories.items():
            if pattern_lower in cat_id.lower() or pattern_lower in cat_info.get("description", "").lower() or pattern_lower in cat_info.get("name", "").lower():
                results["categories"].append({"id": cat_id, **cat_info})

        # Calculate totals
        results["total_matches"] = sum(len(v) for k, v in results.items() if isinstance(v, list))

        return results

    @mcp.resource("bapi://catalog/classes")
    def get_classes() -> dict[str, Any]:
        """
        Get ABAP class information from the catalog.

        Returns:
        - verified_counts: Number of classes found in SAP per pattern
        - important_classes: Key classes with methods and descriptions

        NOTE: The catalog contains 3,161 verified classes from SAP extraction:
        - CL_ISU_*: 1,634 classes
        - CL_FKK_*: 1,265 classes
        - CL_BUPA_*: 262 classes

        Only a subset of important classes is documented in detail.
        """
        catalog = _load_catalog()
        return catalog.get("classes", {})

    @mcp.resource("bapi://catalog/reports")
    def get_reports() -> dict[str, Any]:
        """
        Get IS-U/FI-CA report information.

        Reports are grouped by functional area:
        - billing: EA* transactions for billing
        - meter_reading: EL* transactions for meter reading
        - device: EG*, IE* for device management
        - fica: RFKK* for FI-CA operations
        - market_communication: /IDXGC/*, /APE/* for market processes

        NOTE: Report details are from online research and may need
        verification in your SAP system via SE38.
        """
        catalog = _load_catalog()
        return catalog.get("reports", {})

    @mcp.resource("bapi://catalog/tables")
    def get_tables() -> dict[str, Any]:
        """
        Get IS-U/FI-CA table information organized by domain.

        Domains include:
        - contracts: EVER, EVERH, EVERU
        - installations: EANL, EANLH, EASTL, EASTS
        - point_of_delivery: EUIINSTLN, EUITRANS, EUIHEAD, EUIGRID, EGRID
        - meter_reading: EABL, EABLG, EABLC
        - billing: ERCH, DBERCHZ, DBERCHV, DBERCHR, DBERCHE, DBERCHT, ETRG
        - fica_documents: DFKKKO, DFKKOP, DFKKOPK, DFKKOPW
        - contract_account: FKKVK, FKKVKP
        - devices: EGERH, EGERS, EQUI, ETDZ, EZWG
        - premise: EVBS, EVBST
        - connection_object: IFLOT, EHAUISU, ILOA
        - business_partner: BUT000, BUT100, BUT050
        - tariffs: ETTA, ETRF, EPREI, ESCHS, EKDI
        - serviceanbieter: ESERVICE, ESERVPROV, ESERVICEDET (verified)
        - versorgungsszenarien: EVERSREASON, EVERSW (verified)
        - abrechnung_erweitert: ERCHARC, ERCHO, ERCHP, ERCHR, ERCHT (verified)
        - customizing_isu: TE069, TE221, TE835, TE810
        - customizing_fica: TFK001G, TFK047A, TFK056A, TFKCOD

        NOTE: Tables marked (verified) were extracted from SAP. Use SE11 to verify others.
        """
        catalog = _load_catalog()
        return catalog.get("tables", {})

    @mcp.resource("bapi://catalog/tables/{domain}")
    def get_tables_by_domain(domain: str) -> dict[str, Any]:
        """
        Get tables for a specific domain.

        Args:
            domain: Domain name (e.g., 'contracts', 'billing', 'customizing_isu')

        Available domains:
            contracts, installations, point_of_delivery, meter_reading,
            billing, fica_documents, contract_account, devices, premise,
            connection_object, business_partner, tariffs,
            customizing_isu, customizing_fica

        Returns:
            Tables in the specified domain with metadata.
        """
        catalog = _load_catalog()
        tables = catalog.get("tables", {})

        if domain not in tables:
            return {
                "error": f"Domain '{domain}' not found",
                "available_domains": list(tables.keys())
            }

        return {
            "domain": domain,
            "tables": tables[domain],
            "count": len(tables[domain])
        }

    @mcp.resource("bapi://catalog/customizing")
    def get_customizing_tables() -> dict[str, Any]:
        """
        Get IS-U and FI-CA customizing tables.

        Customizing tables (delivery class C) contain configuration data:

        IS-U Customizing (TE* tables):
        - TE069: Rate Types
        - TE221: Operands for billing calculations
        - TE835: Line Item Types
        - TE810: Billing Schema

        FI-CA Customizing (TFK* tables):
        - TFK001G: Company Code Groups
        - TFK047A: Dunning Procedures
        - TFK056A: Interest Keys
        - TFK070B: Correspondence Procedures

        These tables are typically maintained via SM30 or IMG transactions.
        """
        catalog = _load_catalog()
        tables = catalog.get("tables", {})

        return {
            "isu_customizing": tables.get("customizing_isu", {}),
            "fica_customizing": tables.get("customizing_fica", {}),
            "tariff_customizing": tables.get("tariffs", {}),
            "note": "Customizing tables use delivery class C (customer data)"
        }

    @mcp.resource("bapi://catalog/namespaces")
    def get_namespaces() -> dict[str, Any]:
        """
        Get SAP namespace information for IS-U/S4U.

        Key namespaces:
        - /IDXGC/: Market Process Management (Common Layer)
        - /IDXGL/: German Locale for market communication
        - /APE/: Application Process Engine (S/4HANA 2208+)
        - /APEU/: APE Utilities Extension
        - /UCOM/: Utilities Common Layer
        - /US4G/: Utilities Solution Germany
        """
        catalog = _load_catalog()
        return catalog.get("namespaces", {})

    @mcp.resource("bapi://catalog/metadata")
    def get_catalog_metadata() -> dict[str, Any]:
        """
        Get catalog metadata including version and extraction statistics.

        Returns:
        - version: Catalog version
        - last_updated: When the catalog was last updated
        - extraction_statistics: Number of objects found in SAP
        - how_to_update: Instructions for updating the catalog
        """
        catalog = _load_catalog()
        metadata = catalog.get("metadata", {})

        return {
            **metadata,
            "available_resources": [
                "bapi://catalog - Full catalog",
                "bapi://catalog/search/{pattern} - Search all objects",
                "bapi://catalog/categories - Functional categories",
                "bapi://catalog/category/{id} - Category details",
                "bapi://catalog/bapi/{name} - BAPI/FM details",
                "bapi://catalog/classes - ABAP classes",
                "bapi://catalog/reports - Reports by area",
                "bapi://catalog/tables - All tables by domain",
                "bapi://catalog/tables/{domain} - Tables for specific domain",
                "bapi://catalog/customizing - IS-U and FI-CA customizing tables",
                "bapi://catalog/namespaces - SAP namespaces",
                "bapi://catalog/workflows - Workflow patterns",
                "bapi://catalog/data_model - IS-U data model hierarchy",
            ],
            "verification_note": "Objects marked 'verified_in_system: true' were extracted from SAP. "
                                "Objects with 'source: online_research' are unverified."
        }

    @mcp.resource("bapi://catalog/workflows")
    def get_workflows() -> dict[str, Any]:
        """
        Get common SAP workflow patterns.

        Includes step-by-step patterns for:
        - payment_processing: Payment lot workflow
        - contract_account_clearing: Document posting with clearing
        - full_installation: Creating complete installation structure

        Use these as templates for implementing similar processes.
        """
        catalog = _load_catalog()
        return catalog.get("workflows", {})

    @mcp.resource("bapi://catalog/data_model")
    def get_data_model() -> dict[str, Any]:
        """
        Get the IS-U data model hierarchy.

        Shows the relationship between:
        Business Partner -> Contract Account -> Contract -> Installation ->
        Premise -> Connection Object -> Device -> Meter Reading

        Use this to understand how IS-U objects relate to each other.
        """
        catalog = _load_catalog()
        return catalog.get("data_model_hierarchy", {})

    @mcp.resource("bapi://catalog/transactions")
    def get_transactions() -> dict[str, Any]:
        """
        Get IS-U/FI-CA transaction information.

        Verified transactions extracted via SE93 from SAP system.
        Each transaction includes:
        - titel: Transaction title (German)
        - programm: ABAP program name
        - dynpro: Screen number
        - typ: Dialog, Report, etc.
        - paket: Development package
        - kategorie: Functional category

        Categories:
        - installation: ES31, ES32 (Installation management)
        - tariff: EC30 (Tariff data)
        - move_in_out: EC50 (Move-in/out documents)
        - billing: EA00 (Billing)
        - device: EG31 (Device installation)
        - fica_account: FPL9 (Account balance)
        - fica_dunning: FPVA (Dunning proposal)
        """
        catalog = _load_catalog()
        return catalog.get("transactions", {})

    @mcp.resource("bapi://catalog/field_types")
    def get_field_types() -> dict[str, Any]:
        """
        Get field type information for key IS-U/FI-CA tables.

        Extracted via SE11 (ABAP Dictionary) with data types:
        - CLNT: Client (Mandant)
        - CHAR: Character string
        - NUMC: Numeric text
        - DATS: Date (YYYYMMDD)
        - TIMS: Time (HHMMSS)
        - DEC: Packed decimal
        - CURR: Currency amount
        - CUKY: Currency key
        - LANG: Language key

        Available tables:
        - EVER: IS-U Contract (133 fields)
        - DFKKKO: FI-CA Document Header (66 fields)
        - ERCH: Billing Document (112 fields)
        - EVBS: Premise (27 fields)

        Each field includes: datentyp, laenge, langtext (German description)
        """
        catalog = _load_catalog()
        return catalog.get("field_types", {})
