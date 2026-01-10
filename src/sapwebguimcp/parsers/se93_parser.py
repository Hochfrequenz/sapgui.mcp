"""
Parser for SE93 (Transaction Maintenance) ARIA snapshots.

Extracts transaction metadata from SE93 display screens, handling:
- Transaction type detection from heading (Dialog vs Report)
- Basic metadata (tcode, description, package, program)
- Type-specific fields (screen number vs selection screen)
- GUI capability checkboxes
- German and English label support
"""

import logging
import re
from datetime import UTC, datetime

from sapwebguimcp.models.se93_models import SE93Entry, SE93Error, SE93TransactionType

logger = logging.getLogger(__name__)

# =============================================================================
# Regex Patterns
# =============================================================================

# Transaction type from heading
# German: "Dialogtransaktion anzeigen", "Reporttransaktion anzeigen"
# English: "Display Dialog Transaction", "Display Report Transaction"
_DIALOG_HEADING_PATTERN = re.compile(r"Dialogtransaktion|Dialog Transaction", re.IGNORECASE)
_REPORT_HEADING_PATTERN = re.compile(r"Reporttransaktion|Report Transaction", re.IGNORECASE)

# Textbox value extraction - matches: textbox "Label": Value or textbox "Label": "Value"
_TEXTBOX_PATTERN = re.compile(r'textbox "(?P<label>[^"]+)"(?::\s*(?P<value>[^\n]*))?')

# Checkbox state - checked or unchecked
_CHECKBOX_PATTERN = re.compile(r'checkbox "(?P<label>[^"]+)"(?:\s*\[checked\])?')


# =============================================================================
# Parser Functions
# =============================================================================


def _extract_textbox_value(snapshot: str, *labels: str) -> str:
    """
    Extract textbox value for any of the given labels.

    Args:
        snapshot: YAML snapshot content
        labels: One or more label names to search for (German/English variants)

    Returns:
        The textbox value, or empty string if not found
    """
    for match in _TEXTBOX_PATTERN.finditer(snapshot):
        label = match.group("label")
        if any(lbl.lower() in label.lower() for lbl in labels):
            value = match.group("value") or ""
            # Clean up quoted values
            value = value.strip().strip('"').strip("'")
            return value
    return ""


def _is_checkbox_checked(snapshot: str, *labels: str) -> bool:
    """
    Check if a checkbox with any of the given labels is checked.

    Args:
        snapshot: YAML snapshot content
        labels: One or more label names to search for

    Returns:
        True if checkbox is checked, False otherwise
    """
    for line in snapshot.split("\n"):
        if "checkbox" in line.lower():
            for label in labels:
                if label.lower() in line.lower() and "[checked]" in line:
                    return True
    return False


def _detect_transaction_type(snapshot: str) -> SE93TransactionType | None:
    """
    Detect transaction type from the page heading.

    Returns:
        'dialog', 'report', or None if type cannot be determined
    """
    # Check first ~20 lines for the heading
    header_section = "\n".join(snapshot.split("\n")[:20])

    if _DIALOG_HEADING_PATTERN.search(header_section):
        return "dialog"
    if _REPORT_HEADING_PATTERN.search(header_section):
        return "report"

    return None


def _extract_gui_capabilities(snapshot: str) -> tuple[bool, bool, bool]:
    """Extract GUI capability checkboxes (html, java, windows)."""
    gui_html = _is_checkbox_checked(snapshot, "SAP GUI für HTML", "SAP GUI for HTML")
    gui_java = _is_checkbox_checked(snapshot, "SAP GUI für Java", "SAP GUI for Java")
    gui_windows = _is_checkbox_checked(snapshot, "SAP GUI für Windows", "SAP GUI for Windows")
    return gui_html, gui_java, gui_windows


def _is_initial_se93_screen(snapshot: str) -> bool:
    """Check if we're on the initial SE93 screen (no transaction displayed)."""
    header_section = "\n".join(snapshot.split("\n")[:10])
    has_initial_heading = (
        'heading "Transaktionspflege"' in header_section or 'heading "Transaction Maintenance"' in header_section
    )
    has_display_heading = "anzeigen" in header_section.lower() or "display" in header_section.lower()
    return has_initial_heading and not has_display_heading


def _extract_type_specific_fields(
    snapshot: str, tx_type: SE93TransactionType
) -> tuple[str | None, str | None, str | None]:
    """Extract type-specific fields (screen_number, selection_screen, start_variant)."""
    if tx_type == "dialog":
        screen_number = _extract_textbox_value(snapshot, "Dynpronummer", "Screen number") or None
        return screen_number, None, None

    # report
    selection_screen = _extract_textbox_value(snapshot, "Selektionsbild", "Selection screen") or None
    start_variant = _extract_textbox_value(snapshot, "Start mit Variante", "Start with variant") or None
    return None, selection_screen, start_variant


def parse_se93_snapshot(snapshot: str, tcode: str) -> SE93Entry | SE93Error:
    """
    Parse SE93 transaction display snapshot into structured data.

    Args:
        snapshot: The YAML accessibility snapshot from browser_snapshot
        tcode: The transaction code being looked up

    Returns:
        SE93Entry on success, SE93Error on parse failure
    """
    now = datetime.now(UTC)

    # Detect transaction type
    tx_type = _detect_transaction_type(snapshot)

    if tx_type is None:
        # Check if we're still on the initial screen (transaction not found)
        if _is_initial_se93_screen(snapshot):
            return SE93Error(
                tcode=tcode,
                error=f"Transaction '{tcode}' not found",
                retrieved_at=now,
            )

        # Unknown transaction type - might be OO, Parameter, or Variant
        return SE93Error(
            tcode=tcode,
            error=(
                f"Unsupported transaction type for '{tcode}'. "
                "Only 'dialog' and 'report' transactions are currently supported. "
                "Please report this transaction code to help improve support: "
                "https://github.com/Hochfrequenz/sapwebgui.mcp/issues"
            ),
            retrieved_at=now,
        )

    # Extract common fields
    found_tcode = _extract_textbox_value(snapshot, "Transaktionscode", "Transaction code")
    description = _extract_textbox_value(snapshot, "Transaktionstext", "Transaction text")
    package = _extract_textbox_value(snapshot, "Paket", "Package")
    program = _extract_textbox_value(snapshot, "Programm", "Program")
    auth_object = _extract_textbox_value(snapshot, "Berechtigungsobjekt", "Authorization object") or None

    # Type-specific and GUI capability fields
    screen_number, selection_screen, start_variant = _extract_type_specific_fields(snapshot, tx_type)
    gui_html, gui_java, gui_windows = _extract_gui_capabilities(snapshot)

    return SE93Entry(
        tcode=(found_tcode or tcode).upper(),
        description=description,
        transaction_type=tx_type,
        package=package,
        program=program,
        screen_number=screen_number,
        selection_screen=selection_screen,
        start_variant=start_variant,
        authorization_object=auth_object,
        gui_html=gui_html,
        gui_java=gui_java,
        gui_windows=gui_windows,
        retrieved_at=now,
    )
