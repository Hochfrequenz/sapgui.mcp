"""Data models for the transaction catalog."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

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
    "PP": "HR-Planning",
    # Production Planning
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

    Args:
        tcode: Transaction code (e.g., "VA01", "ME21N")

    Returns:
        Area identifier if detected, None otherwise
    """
    if not tcode:
        return None

    tcode_upper = tcode.upper()

    # Try 3-char prefix first (for CO0*, etc.)
    if len(tcode_upper) >= 3 and tcode_upper[:3] in SAP_AREA_PREFIXES:
        return SAP_AREA_PREFIXES[tcode_upper[:3]]

    # Try 2-char prefix
    if len(tcode_upper) >= 2 and tcode_upper[:2] in SAP_AREA_PREFIXES:
        return SAP_AREA_PREFIXES[tcode_upper[:2]]

    return None


class TransactionInfo(BaseModel):
    """Complete transaction metadata for the catalog.

    Combines data from TSTC (transaction codes table) and SE93 (transaction maintenance).
    """

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
    """Container for the full transaction catalog with metadata."""

    transactions: list[TransactionInfo] = Field(default_factory=list, description="All transactions in catalog")
    source_system: str | None = Field(default=None, description="SAP system ID where data was collected")
    language: str | None = Field(default=None, description="Language used for descriptions (EN/DE)")
    last_updated: AwareDatetime | None = Field(default=None, description="When catalog was last updated")
    tstc_count: int = Field(default=0, description="Total transactions from TSTC table")
    enriched_count: int = Field(default=0, description="Transactions enriched via SE93")

    def get_by_tcode(self, tcode: str) -> TransactionInfo | None:
        """Look up a transaction by code."""
        tcode_upper = tcode.upper()
        for txn in self.transactions:
            if txn.tcode.upper() == tcode_upper:
                return txn
        return None

    def get_by_area(self, area: str) -> list[TransactionInfo]:
        """Get all transactions for a given area."""
        area_upper = area.upper()
        return [t for t in self.transactions if t.area and t.area.upper() == area_upper]
