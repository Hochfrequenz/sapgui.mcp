"""Pydantic models for IS-U / S/4 Utilities object catalog.

These models define the structure for:
- BAPIs and Function Modules
- ABAP Classes
- Reports and Transactions
- Tables and Table Fields
- Namespaces
- Workflows and Data Model

All catalog objects can be marked as verified_in_system (extracted from SAP)
or unverified (from online research).
"""

from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Base Models
# =============================================================================


class VerifiableObject(BaseModel):
    """Base class for objects that can be verified in SAP system."""

    verified_in_system: bool = Field(
        default=False, description="True if extracted directly from SAP system"
    )
    source: str | None = Field(
        default=None,
        description="Source of the data: 'sap_extraction', 'online_research', or combined",
    )


# =============================================================================
# Function Module / BAPI Models
# =============================================================================


class FunctionModuleParameter(BaseModel):
    """A parameter of a function module or BAPI."""

    name: str = Field(description="Parameter name")
    type: str | None = Field(default=None, description="ABAP type or structure name")
    optional: bool = Field(default=False, description="Whether the parameter is optional")
    description: str | None = Field(default=None, description="Parameter description")


class FunctionModule(VerifiableObject):
    """An ABAP function module or BAPI."""

    name: str = Field(description="Function module name (e.g., BAPI_EQUI_CREATE)")
    description: str | None = Field(default=None, description="Short description")
    category: str | None = Field(
        default=None, description="Functional category (e.g., 'equipment', 'billing')"
    )
    function_group: str | None = Field(default=None, description="Function group name")
    import_params: list[FunctionModuleParameter] = Field(
        default_factory=list, description="Import parameters"
    )
    export_params: list[FunctionModuleParameter] = Field(
        default_factory=list, description="Export parameters"
    )
    tables: list[FunctionModuleParameter] = Field(
        default_factory=list, description="Table parameters"
    )
    exceptions: list[str] = Field(default_factory=list, description="Exception names")
    usage_notes: str | None = Field(default=None, description="Usage notes and tips")


class Bapi(FunctionModule):
    """A BAPI (Business Application Programming Interface).

    BAPIs are standardized function modules following SAP's BAPI conventions.
    """

    is_bapi: bool = Field(default=True, description="Always True for BAPIs")
    related_bapis: list[str] = Field(
        default_factory=list, description="Related BAPIs (e.g., _CREATE, _CHANGE, _DELETE)"
    )


# =============================================================================
# Class Models
# =============================================================================


class ClassMethod(BaseModel):
    """A method of an ABAP class."""

    name: str = Field(description="Method name")
    visibility: str = Field(default="public", description="public, protected, or private")
    is_static: bool = Field(default=False, description="Whether the method is static")
    description: str | None = Field(default=None, description="Method description")
    parameters: list[FunctionModuleParameter] = Field(
        default_factory=list, description="Method parameters"
    )
    return_type: str | None = Field(default=None, description="Return type for functions")


class AbapClass(VerifiableObject):
    """An ABAP class."""

    name: str = Field(description="Class name (e.g., CL_ISU_BUPA)")
    description: str | None = Field(default=None, description="Short description")
    category: str | None = Field(default=None, description="Functional category")
    superclass: str | None = Field(default=None, description="Parent class if any")
    interfaces: list[str] = Field(default_factory=list, description="Implemented interfaces")
    key_methods: list[ClassMethod] = Field(
        default_factory=list, description="Important methods"
    )


class ClassesSummary(BaseModel):
    """Summary of ABAP classes in the catalog."""

    verified_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Number of classes per pattern found in SAP (e.g., {'CL_ISU_*': 1634})",
    )
    important_classes: list[AbapClass] = Field(
        default_factory=list, description="Documented important classes"
    )


# =============================================================================
# Table Models
# =============================================================================


class TableField(BaseModel):
    """A field in a database table."""

    name: str = Field(description="Field name")
    data_element: str | None = Field(default=None, description="Data element name")
    domain: str | None = Field(default=None, description="Domain name")
    type: str | None = Field(default=None, description="ABAP type (CHAR, NUMC, etc.)")
    length: int | None = Field(default=None, description="Field length")
    decimals: int | None = Field(default=None, description="Decimal places for numeric")
    is_key: bool = Field(default=False, description="Whether field is part of primary key")
    description: str | None = Field(default=None, description="Field description (long text)")
    check_table: str | None = Field(
        default=None, description="Foreign key table if applicable"
    )


class SapTable(VerifiableObject):
    """An SAP database table."""

    name: str = Field(description="Table name (e.g., EVER, EANL)")
    description: str | None = Field(default=None, description="Short description")
    domain: str | None = Field(
        default=None,
        description="Functional domain (contracts, installations, billing, etc.)",
    )
    delivery_class: str | None = Field(
        default=None,
        description="Delivery class (A=Application, C=Customizing, S=System, etc.)",
    )
    key_fields: list[str] = Field(default_factory=list, description="Primary key field names")
    important_fields: list[str] = Field(
        default_factory=list, description="Important non-key fields"
    )
    fields: list[TableField] = Field(
        default_factory=list, description="All fields with details"
    )
    related_tables: list[str] = Field(
        default_factory=list, description="Related tables (foreign keys)"
    )
    field_count: int | None = Field(default=None, description="Total number of fields")
    notes: str | None = Field(default=None, description="Usage notes")


class MaintenanceView(VerifiableObject):
    """An SM30 maintenance view for customizing tables."""

    name: str = Field(description="View name (e.g., V_EABL)")
    description: str | None = Field(default=None, description="Short description")
    base_tables: list[str] = Field(
        default_factory=list, description="Underlying tables"
    )
    transaction: str | None = Field(
        default=None, description="Associated transaction code if any"
    )


# =============================================================================
# Report Models
# =============================================================================


class Report(VerifiableObject):
    """An ABAP report/program."""

    name: str = Field(description="Report name (e.g., RFKKCOLL)")
    description: str | None = Field(default=None, description="Short description")
    area: str | None = Field(
        default=None, description="Functional area (billing, meter_reading, fica)"
    )
    transaction: str | None = Field(
        default=None, description="Associated transaction code"
    )
    selection_parameters: list[str] = Field(
        default_factory=list, description="Important selection parameters"
    )


# =============================================================================
# Namespace Models
# =============================================================================


class Namespace(VerifiableObject):
    """An SAP development namespace."""

    namespace: str = Field(description="Namespace (e.g., /IDXGC/, /APE/)")
    name: str = Field(description="Short name")
    full_name: str | None = Field(default=None, description="Full name")
    description: str | None = Field(default=None, description="Description")
    system_requirements: str | None = Field(
        default=None, description="Required SAP version/add-ons"
    )
    typical_objects: list[str] = Field(
        default_factory=list, description="Example objects in this namespace"
    )
    tables: list[str] = Field(default_factory=list, description="Key tables")
    sap_notes: list[str] = Field(default_factory=list, description="Related SAP Notes")
    replaces: str | None = Field(default=None, description="Namespace this replaces")
    replaced_by: str | None = Field(default=None, description="Newer namespace")


# =============================================================================
# Category Models
# =============================================================================


class Category(BaseModel):
    """A functional category grouping related objects."""

    id: str = Field(description="Category ID (e.g., 'equipment', 'billing')")
    name: str = Field(description="Human-readable name")
    description: str | None = Field(default=None, description="Description")
    prefix_patterns: list[str] = Field(
        default_factory=list, description="Naming patterns (e.g., 'BAPI_EQUI*')"
    )
    related_tables: list[str] = Field(default_factory=list, description="Key tables")
    key_bapis: list[str] = Field(default_factory=list, description="Important BAPIs")
    key_function_modules: list[str] = Field(
        default_factory=list, description="Important function modules"
    )


# =============================================================================
# Workflow Models (Data Model)
# =============================================================================


class WorkflowStep(BaseModel):
    """A step in a workflow pattern."""

    step: int = Field(description="Step number")
    action: str = Field(description="Action description")
    function_module: str | None = Field(
        default=None, description="Function module to call"
    )
    transaction: str | None = Field(default=None, description="Transaction to use")
    notes: str | None = Field(default=None, description="Additional notes")


class WorkflowPattern(BaseModel):
    """A reusable workflow pattern."""

    name: str = Field(description="Workflow name")
    description: str | None = Field(default=None, description="What this workflow does")
    steps: list[WorkflowStep] = Field(default_factory=list, description="Workflow steps")


class DataModelNode(BaseModel):
    """A node in the IS-U data model hierarchy."""

    name: str = Field(description="Object type name")
    table: str | None = Field(default=None, description="Main table")
    key_field: str | None = Field(default=None, description="Primary key field")
    children: list["DataModelNode"] = Field(
        default_factory=list, description="Child objects"
    )


# =============================================================================
# Catalog Metadata
# =============================================================================


class ExtractionStatistics(BaseModel):
    """Statistics about object extraction from SAP."""

    function_modules_from_sap: dict[str, Any] = Field(
        default_factory=dict,
        description="Count of function modules per pattern",
    )
    classes_from_sap: dict[str, int] = Field(
        default_factory=dict,
        description="Count of classes per pattern",
    )
    tables_from_sap: dict[str, int] = Field(
        default_factory=dict,
        description="Count of tables per pattern",
    )


class CatalogMetadata(BaseModel):
    """Metadata about the catalog."""

    version: str = Field(description="Catalog version (semver)")
    description: str | None = Field(default=None, description="Catalog description")
    last_updated: str = Field(description="Last update date (ISO format)")
    source_system: str | None = Field(default=None, description="SAP system ID")
    source_client: str | None = Field(default=None, description="SAP client number")
    extraction_statistics: ExtractionStatistics = Field(
        default_factory=ExtractionStatistics
    )
    how_to_update: str | None = Field(
        default=None, description="Instructions for updating the catalog"
    )


# =============================================================================
# Full Catalog Model
# =============================================================================


class UtilitiesCatalog(BaseModel):
    """Complete IS-U / S/4 Utilities object catalog."""

    metadata: CatalogMetadata = Field(description="Catalog metadata")
    namespaces: dict[str, Namespace] = Field(
        default_factory=dict, description="SAP namespaces"
    )
    tables: dict[str, dict[str, SapTable]] = Field(
        default_factory=dict,
        description="Tables grouped by domain (e.g., {'contracts': {'EVER': {...}}})",
    )
    categories: dict[str, Category] = Field(
        default_factory=dict, description="Functional categories"
    )
    bapis: list[Bapi] = Field(default_factory=list, description="BAPI list")
    function_modules: list[FunctionModule] = Field(
        default_factory=list, description="Non-BAPI function modules"
    )
    classes: ClassesSummary = Field(
        default_factory=ClassesSummary, description="ABAP classes"
    )
    reports: dict[str, dict[str, Report]] = Field(
        default_factory=dict, description="Reports grouped by area"
    )
    transactions: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Transactions grouped by area"
    )
    workflows: dict[str, WorkflowPattern] = Field(
        default_factory=dict, description="Workflow patterns"
    )
    data_model_hierarchy: DataModelNode | None = Field(
        default=None, description="IS-U data model hierarchy"
    )
    maintenance_views: dict[str, MaintenanceView] = Field(
        default_factory=dict, description="SM30 maintenance views"
    )


# =============================================================================
# Search Result Models
# =============================================================================


class SearchResult(BaseModel):
    """Result of searching across all object types."""

    pattern: str = Field(description="Search pattern used")
    bapis: list[Bapi] = Field(default_factory=list)
    function_modules: list[FunctionModule] = Field(default_factory=list)
    classes: list[AbapClass] = Field(default_factory=list)
    reports: list[Report] = Field(default_factory=list)
    tables: list[SapTable] = Field(default_factory=list)
    namespaces: list[Namespace] = Field(default_factory=list)
    categories: list[Category] = Field(default_factory=list)
    total_matches: int = Field(default=0, description="Total number of matches")


class BapiLookupResult(BaseModel):
    """Result of looking up a specific BAPI or function module."""

    found: bool = Field(description="Whether the object was found")
    type: str | None = Field(
        default=None, description="Object type: 'bapi' or 'function_module'"
    )
    verified: bool = Field(
        default=False, description="Whether verified in SAP system"
    )
    object: Bapi | FunctionModule | None = Field(
        default=None, description="The found object"
    )
    error: str | None = Field(default=None, description="Error message if not found")
    hint: str | None = Field(default=None, description="Hint for user")


class CategoryDetailsResult(BaseModel):
    """Result of getting category details."""

    category: Category | None = Field(default=None)
    bapis: list[Bapi] = Field(default_factory=list)
    function_modules: list[FunctionModule] = Field(default_factory=list)
    total_count: int = Field(default=0)
    error: str | None = Field(default=None)
    available_categories: list[str] | None = Field(default=None)


class CatalogMetadataResult(BaseModel):
    """Result of getting catalog metadata."""

    version: str | None = Field(default=None)
    last_updated: str | None = Field(default=None)
    extraction_statistics: ExtractionStatistics | None = Field(default=None)
    how_to_update: str | None = Field(default=None)
    available_resources: list[str] = Field(default_factory=list)
    verification_note: str | None = Field(default=None)
