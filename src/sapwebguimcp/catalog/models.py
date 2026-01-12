"""Data models for the transaction catalog.

Design Notes:
- TransactionInfo is immutable-ish (Pydantic model) for safe caching
- TransactionCatalog maintains a lazy tcode index for O(1) lookups
- Area detection uses longest-prefix-first matching (3-char before 2-char)
  because CO01 should match "PP-Orders" (CO0*) not "CO-General" (CO*)
"""

from typing import Literal

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
        tcode = str(
            row_data.get("TCODE") or row_data.get("Transaktionscode", "")
        ).strip()
        program = str(
            row_data.get("PGMNA") or row_data.get("Programm", "")
        ).strip()
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
            self._tcode_index = {
                txn.tcode.upper(): i for i, txn in enumerate(self.transactions)
            }
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
