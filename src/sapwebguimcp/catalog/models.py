"""Data models for SAP catalogs - SHARED.

===========================================================================
These models are used by BOTH runtime (MCP tools) and development (scraper).
They define the data structure for:
- transactions.json (TransactionInfo, TransactionCatalog)
- function_modules.json (FunctionModuleInfo, FunctionModuleCatalog)
- classes.json (ClassInfo, ClassCatalog)
===========================================================================

Design Notes:
- TransactionInfo is immutable-ish (Pydantic model) for safe caching
- TransactionCatalog maintains a lazy tcode index for O(1) lookups
- Area detection uses longest-prefix-first matching (3-char before 2-char)
  because CO01 should match "PP-Orders" (CO0*) not "CO-General" (CO*)
"""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# Transaction types (same as SE93)
TransactionType = Literal["dialog", "report", "unknown"]


# SAP module/area prefixes - common patterns
SAP_AREA_PREFIXES: dict[str, str] = {
    # Sales & Distribution
    "VA": "SD-Sales",
    "VL": "SD-Shipping",
    "VF": "SD-Billing",
    # Materials Management
    "MM": "MM-General",
    "ME": "MM-Purchasing",
    "MB": "MM-Inventory",
    "MI": "MM-Inventory",
    "MR": "MM-Invoice",
    # Financial Accounting
    "FI": "FI-General",
    "FB": "FI-Postings",
    "FK": "FI-Vendors",
    "FD": "FI-Customers",
    "FS": "FI-GL",
    "F1": "FI-General",
    "F2": "FI-General",
    # Controlling
    "CO": "CO-General",
    "KS": "CO-CostCenters",
    "KP": "CO-Planning",
    "KB": "CO-Postings",
    # Human Resources
    "PA": "HR-Personnel",
    "PB": "HR-Recruitment",
    # NOTE: PP* = Production Planning, NOT HR-Planning (common misconception)
    # PP01 = Maintain Work Center, PP02 = Change Work Center, etc.
    "PP": "PP-Production",
    # Production Planning / MRP
    "MD": "PP-MRP",
    "MF": "PP-Production",
    "CR": "PP-WorkCenters",
    "CA": "PP-Routing",
    "CO0": "PP-Orders",
    # Plant Maintenance
    "IW": "PM-Orders",
    "IE": "PM-Equipment",
    "IL": "PM-FunctionalLoc",
    # Basis/Technical
    "SE": "BC-Development",
    "SA": "BC-Admin",
    "SM": "BC-Monitoring",
    "SU": "BC-Users",
    "ST": "BC-Trace",
    "SP": "BC-Spool",
    "RZ": "BC-CCMS",
    # Project System
    "CJ": "PS-Projects",
    "CN": "PS-Networks",
    # Quality Management
    "QA": "QM-Inspection",
    "QC": "QM-Certificates",
    # Warehouse Management
    "LT": "WM-Transfers",
    "LI": "WM-Inventory",
}


def detect_area(tcode: str) -> str | None:
    """Detect SAP module/area from transaction code prefix.

    Uses longest-prefix-first matching to handle overlapping prefixes correctly.
    Example: CO01 should match "PP-Orders" (CO0*) not "CO-General" (CO*).

    Args:
        tcode: Transaction code (e.g., "VA01", "ME21N")

    Returns:
        Area identifier if detected, None otherwise.
        Returns None for custom/Z* transactions (no standard mapping).
    """
    if not tcode:
        return None

    tcode_upper = tcode.upper()

    # IMPORTANT: Check 3-char prefix FIRST for specificity.
    # CO01 should match CO0* (PP-Orders) not CO* (CO-General).
    # This is a longest-prefix-match algorithm.
    if len(tcode_upper) >= 3 and tcode_upper[:3] in SAP_AREA_PREFIXES:
        return SAP_AREA_PREFIXES[tcode_upper[:3]]

    # Fall back to 2-char prefix
    if len(tcode_upper) >= 2 and tcode_upper[:2] in SAP_AREA_PREFIXES:
        return SAP_AREA_PREFIXES[tcode_upper[:2]]

    return None


class TransactionInfo(BaseModel):
    """Complete transaction metadata for the catalog.

    Combines data from TSTC (transaction codes table) and SE93 (transaction maintenance).

    Design Decision: We use Pydantic's BaseModel (not dataclass) because:
    1. We need JSON serialization with model_dump_json()
    2. We need validation when loading from external JSON files
    3. We need model_copy() for immutable updates during SE93 enrichment
    """

    # Reject unknown fields to catch typos in JSON data or code
    model_config = ConfigDict(extra="forbid")

    tcode: str = Field(description="Transaction code (e.g., 'VA01', 'SE38')")
    description: str = Field(default="", description="Transaction text/description")
    program: str = Field(default="", description="Program/report name (e.g., 'SAPMV45A')")
    screen_number: str | None = Field(default=None, description="Dynpro/screen number (dialog transactions)")
    transaction_type: TransactionType = Field(default="unknown", description="Type: 'dialog', 'report', or 'unknown'")

    # Classification
    area: str | None = Field(default=None, description="SAP module area (e.g., 'SD-Sales', 'MM-Purchasing')")
    package: str | None = Field(default=None, description="Development package (e.g., 'VA', 'SEDT')")

    # GUI capabilities
    gui_html: bool = Field(default=False, description="Supports SAP GUI for HTML (Web GUI)")
    gui_java: bool = Field(default=False, description="Supports SAP GUI for Java")
    gui_windows: bool = Field(default=False, description="Supports SAP GUI for Windows")

    # Authorization
    authorization_object: str | None = Field(default=None, description="Authorization object (e.g., 'S_DEVELOP')")

    # Metadata
    enriched: bool = Field(default=False, description="Whether SE93 enrichment was applied")
    retrieved_at: AwareDatetime | None = Field(default=None, description="UTC timestamp when data was retrieved")

    @classmethod
    def from_tstc_row(cls, row_data: dict[str, object]) -> "TransactionInfo":
        """Create TransactionInfo from a TSTC table row.

        TSTC columns can be in English technical names or German display names:
        - TCODE / Transaktionscode: Transaction code
        - PGMNA / Programm: Program name
        - DESSION / Dynpro: Screen/session number
        """
        # Handle both technical names and German display names
        tcode = str(row_data.get("TCODE") or row_data.get("Transaktionscode", "")).strip()
        program = str(row_data.get("PGMNA") or row_data.get("Programm", "")).strip()
        screen = row_data.get("DESSION") or row_data.get("Dynpro")

        screen_number = None
        if screen is not None and screen != "":
            screen_number = str(screen).strip()

        return cls(
            tcode=tcode,
            program=program,
            screen_number=screen_number,
            area=detect_area(tcode),
            enriched=False,
        )


class TransactionCatalog(BaseModel):
    """Container for the full transaction catalog with metadata.

    Performance Note:
    - get_by_tcode() uses a cached dict index for O(1) lookups
    - The index is built lazily on first access via cached_property
    - If you modify transactions list directly, call _invalidate_index()
    """

    model_config = ConfigDict(extra="forbid")

    transactions: list[TransactionInfo] = Field(default_factory=list, description="All transactions in catalog")
    source_system: str | None = Field(default=None, description="SAP system ID where data was collected")
    language: str | None = Field(default=None, description="Language used for descriptions (EN/DE)")
    last_updated: AwareDatetime | None = Field(default=None, description="When catalog was last updated")
    tstc_count: int = Field(default=0, description="Total transactions from TSTC table")
    enriched_count: int = Field(default=0, description="Transactions enriched via SE93")

    # Internal: cached index for O(1) tcode lookups
    # NOTE: We can't use cached_property directly with Pydantic models,
    # so we use a private dict that's populated on first access.
    _tcode_index: dict[str, int] | None = None

    def _get_tcode_index(self) -> dict[str, int]:
        """Get or build the tcode -> list index mapping.

        Returns dict mapping uppercase tcode to index in transactions list.
        This gives O(1) lookups instead of O(n) linear scan.
        """
        if self._tcode_index is None:
            # Build index: tcode (uppercase) -> index in transactions list
            self._tcode_index = {txn.tcode.upper(): i for i, txn in enumerate(self.transactions)}
        return self._tcode_index

    def _invalidate_index(self) -> None:
        """Clear the cached index. Call this if you modify transactions list."""
        self._tcode_index = None

    def get_by_tcode(self, tcode: str) -> TransactionInfo | None:
        """Look up a transaction by code (case-insensitive, O(1) via index)."""
        index = self._get_tcode_index()
        idx = index.get(tcode.upper())
        if idx is not None:
            return self.transactions[idx]
        return None

    def get_by_area(self, area: str) -> list[TransactionInfo]:
        """Get all transactions for a given area.

        Note: This is O(n) as we don't index by area. For frequent area
        queries, consider building a separate area index.
        """
        area_upper = area.upper()
        return [t for t in self.transactions if t.area and t.area.upper() == area_upper]


# =============================================================================
# Function Module Catalog Models (IS-U / S4 Utilities)
# =============================================================================

# FM area prefixes for IS-U/Utilities
FM_AREA_PREFIXES: dict[str, str] = {
    # IS-U specific (longest prefixes first)
    "ISU_EDM_": "ISU-EDM",
    "ISU_DM_": "ISU-DM",
    "ISU_S_": "ISU-Service",
    "ISU_DB_": "ISU-DB",
    "ISU_": "ISU",
    # FICA
    "FKK_": "FICA",
    # BAPIs
    "BAPI_ISUPARTNER": "ISU-BAPI",
    "BAPI_ISUACCOUNT": "ISU-BAPI",
    "BAPI_ISUPOD": "ISU-BAPI",
    "BAPI_ISUMOVE": "ISU-BAPI",
    "BAPI_ISU": "ISU-BAPI",
    "BAPI_CTRAC": "FICA-BAPI",
    "BAPI_FKK": "FICA-BAPI",
    # Energy/EDM
    "EDM_": "EDM",
    "IDEX": "IDEX",
}


def detect_fm_area(fm_name: str) -> str | None:
    """Detect area from function module name prefix.

    Uses longest-prefix-first matching.
    """
    if not fm_name:
        return None

    fm_upper = fm_name.upper()

    # Sort prefixes by length (longest first) for correct matching
    for prefix in sorted(FM_AREA_PREFIXES.keys(), key=len, reverse=True):
        if fm_upper.startswith(prefix):
            return FM_AREA_PREFIXES[prefix]

    return None


class ParameterInfo(BaseModel):
    """Function module parameter information."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Parameter name")
    category: str = Field(description="Parameter category: import/export/changing/tables")
    typing: str = Field(default="", description="Typing method: TYPE, LIKE, etc.")
    reference_type: str = Field(default="", description="Reference type or structure")
    default_value: str = Field(default="", description="Default value if any")
    optional: bool = Field(default=False, description="Whether parameter is optional")
    pass_by_value: bool = Field(default=False, description="Pass by value flag")
    description: str = Field(default="", description="Parameter description")


class ExceptionInfo(BaseModel):
    """Function module exception information."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Exception name")
    description: str = Field(default="", description="Exception description")


class FunctionModuleInfo(BaseModel):
    """Complete function module metadata for the catalog."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Function module name (e.g., 'ISU_CONSUMPTION_DETERMINE')")
    description: str = Field(default="", description="Short text description")
    function_group: str | None = Field(default=None, description="Function group name")
    package: str | None = Field(default=None, description="Development package")
    area: str | None = Field(default=None, description="Area: ISU, ISU-EDM, FICA, etc.")

    # Parameters from SE37
    import_parameters: list[ParameterInfo] = Field(default_factory=list)
    export_parameters: list[ParameterInfo] = Field(default_factory=list)
    changing_parameters: list[ParameterInfo] = Field(default_factory=list)
    tables_parameters: list[ParameterInfo] = Field(default_factory=list)
    exceptions: list[ExceptionInfo] = Field(default_factory=list)

    # Flags
    is_rfc_enabled: bool = Field(default=False, description="Remote-enabled (RFC)")
    enriched: bool = Field(default=False, description="Whether SE37 enrichment was applied")
    retrieved_at: AwareDatetime | None = Field(default=None, description="UTC timestamp")

    @classmethod
    def from_se37_entry(cls, entry: dict[str, Any]) -> "FunctionModuleInfo":
        """Create FunctionModuleInfo from SE37 lookup result."""
        name = entry.get("function_module", "")

        # Convert parameters
        import_params = [ParameterInfo(**p) for p in entry.get("import_parameters", [])]
        export_params = [ParameterInfo(**p) for p in entry.get("export_parameters", [])]
        changing_params = [ParameterInfo(**p) for p in entry.get("changing_parameters", [])]
        tables_params = [ParameterInfo(**p) for p in entry.get("tables_parameters", [])]
        exceptions = [ExceptionInfo(**e) for e in entry.get("exceptions", [])]

        return cls(
            name=name,
            description=entry.get("description", ""),
            function_group=entry.get("function_group"),
            package=entry.get("package"),
            area=detect_fm_area(name),
            import_parameters=import_params,
            export_parameters=export_params,
            changing_parameters=changing_params,
            tables_parameters=tables_params,
            exceptions=exceptions,
            is_rfc_enabled=entry.get("is_rfc_enabled", False),
            enriched=True,
            retrieved_at=entry.get("retrieved_at"),
        )


class FunctionModuleCatalog(BaseModel):
    """Container for the function module catalog."""

    model_config = ConfigDict(extra="forbid")

    function_modules: list[FunctionModuleInfo] = Field(default_factory=list)
    source_system: str | None = Field(default=None, description="SAP system ID")
    language: str | None = Field(default=None, description="Language (EN/DE)")
    last_updated: AwareDatetime | None = Field(default=None)
    total_count: int = Field(default=0)
    enriched_count: int = Field(default=0)

    _name_index: dict[str, int] | None = None

    def _get_name_index(self) -> dict[str, int]:
        """Get or build the name -> list index mapping."""
        if self._name_index is None:
            self._name_index = {fm.name.upper(): i for i, fm in enumerate(self.function_modules)}
        return self._name_index

    def _invalidate_index(self) -> None:
        """Clear the cached index."""
        self._name_index = None

    def get_by_name(self, name: str) -> FunctionModuleInfo | None:
        """Look up a function module by name (case-insensitive)."""
        index = self._get_name_index()
        idx = index.get(name.upper())
        if idx is not None:
            return self.function_modules[idx]
        return None

    def add_or_update(self, fm: FunctionModuleInfo) -> None:
        """Add or update a function module in the catalog."""
        existing = self.get_by_name(fm.name)
        if existing:
            # Update existing
            idx = self._get_name_index()[fm.name.upper()]
            self.function_modules[idx] = fm
        else:
            # Add new
            self.function_modules.append(fm)  # pylint: disable=no-member
            self._invalidate_index()


# =============================================================================
# Class Catalog Models (IS-U / S4 Utilities)
# =============================================================================

# Class area prefixes
CLASS_AREA_PREFIXES: dict[str, str] = {
    "CL_ISU_": "ISU",
    "CL_FKK": "FICA",
    "CL_EDM_": "EDM",
    "CL_IDEX": "IDEX",
    "IF_ISU_": "ISU",
    "IF_FKK": "FICA",
    "IF_EDM": "EDM",
}


def detect_class_area(class_name: str) -> str | None:
    """Detect area from class/interface name prefix."""
    if not class_name:
        return None

    class_upper = class_name.upper()

    for prefix in sorted(CLASS_AREA_PREFIXES.keys(), key=len, reverse=True):
        if class_upper.startswith(prefix):
            return CLASS_AREA_PREFIXES[prefix]

    return None


class MethodInfo(BaseModel):
    """Class method information."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Method name")
    visibility: str = Field(default="public", description="public/protected/private")
    description: str = Field(default="", description="Method description")
    parameters: list[ParameterInfo] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)


class AttributeInfo(BaseModel):
    """Class attribute information."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Attribute name")
    visibility: str = Field(default="public", description="public/protected/private")
    typing: str = Field(default="", description="Type reference")
    description: str = Field(default="", description="Attribute description")


class ClassInfo(BaseModel):
    """Complete class/interface metadata for the catalog."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Class/interface name (e.g., 'CL_ISU_BILLING')")
    description: str = Field(default="", description="Short text description")
    class_type: str = Field(default="class", description="'class' or 'interface'")
    area: str | None = Field(default=None, description="Area: ISU, FICA, EDM, etc.")

    # Details from SE24
    methods: list[MethodInfo] = Field(default_factory=list)
    attributes: list[AttributeInfo] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)

    # Flags
    is_remote: bool = Field(default=False, description="Remote-enabled")
    enriched: bool = Field(default=False, description="Whether SE24 enrichment was applied")
    retrieved_at: AwareDatetime | None = Field(default=None)


class ClassCatalog(BaseModel):
    """Container for the class catalog."""

    model_config = ConfigDict(extra="forbid")

    classes: list[ClassInfo] = Field(default_factory=list)
    source_system: str | None = Field(default=None)
    language: str | None = Field(default=None)
    last_updated: AwareDatetime | None = Field(default=None)
    total_count: int = Field(default=0)
    enriched_count: int = Field(default=0)

    _name_index: dict[str, int] | None = None

    def _get_name_index(self) -> dict[str, int]:
        """Get or build the name -> list index mapping."""
        if self._name_index is None:
            self._name_index = {c.name.upper(): i for i, c in enumerate(self.classes)}
        return self._name_index

    def _invalidate_index(self) -> None:
        """Clear the cached index."""
        self._name_index = None

    def get_by_name(self, name: str) -> ClassInfo | None:
        """Look up a class by name (case-insensitive)."""
        index = self._get_name_index()
        idx = index.get(name.upper())
        if idx is not None:
            return self.classes[idx]
        return None

    def add_or_update(self, cls: ClassInfo) -> None:
        """Add or update a class in the catalog."""
        existing = self.get_by_name(cls.name)
        if existing:
            idx = self._get_name_index()[cls.name.upper()]
            self.classes[idx] = cls
        else:
            self.classes.append(cls)  # pylint: disable=no-member
            self._invalidate_index()
