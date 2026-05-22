"""
Parser for SE24 (Class Builder) ARIA snapshots.

Extracts class/interface metadata from SE24 display screens, handling:
- Class/interface name and type from heading
- Methods with parameters
- Attributes (constants, instance/static variables)
- German and English label support
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import (
    SE24_CLASS_BUILDER_DE,
    SE24_CLASS_BUILDER_EN,
    SE24_CLASS_DE,
    SE24_CLASS_EN,
    SE24_DISPLAY_PREFIX_EN,
    SE24_DISPLAY_SUFFIX_DE,
    SE24_INITIAL_SCREEN_DE,
    SE24_INITIAL_SCREEN_EN,
    SE24_INTERFACE_DE,
    SE24_INTERFACE_EN,
    SE24_NOT_EXIST_DE,
    SE24_NOT_EXIST_EN,
    SE24_NOT_FOUND_DE,
    SE24_OBJECT_TYPE_DE,
    SE24_OBJECT_TYPE_EN,
    SE24_PRIVATE_DE,
    SE24_PRIVATE_EN,
    SE24_PROTECTED_DE,
    SE24_PROTECTED_EN,
    bilingual_pattern,
)
from sapguimcp.models.se24_models import (
    SE24Attribute,
    SE24Entry,
    SE24Error,
    SE24Method,
    SE24ObjectType,
    SE24Visibility,
)

logger = logging.getLogger(__name__)

__all__ = [
    "parse_se24_snapshot",
    "parse_se24_methods_snapshot",
    "parse_se24_attributes_snapshot",
    "SE24TabSnapshots",
]

# =============================================================================
# Regex Patterns
# =============================================================================

# Class/Interface name from heading
# Uses explicit constants: SE24_CLASS_BUILDER_DE/EN, SE24_DISPLAY_SUFFIX_DE, SE24_DISPLAY_PREFIX_EN
# German: "Klassenpflege: CL_SALV_TABLE anzeigen"
# English: "Class Builder: Display CL_SALV_TABLE"
_CLASS_HEADING_PATTERN = re.compile(
    rf'heading "{bilingual_pattern(SE24_CLASS_BUILDER_DE, SE24_CLASS_BUILDER_EN)}:\s*'
    rf"(?:(?P<name_de>[A-Z0-9_/]+)\\s+{SE24_DISPLAY_SUFFIX_DE}|{SE24_DISPLAY_PREFIX_EN}\\s+(?P<name_en>[A-Z0-9_/]+))\"",
    re.IGNORECASE,
)

# Determine if class or interface from screen content
# Uses explicit constants: SE24_OBJECT_TYPE_DE/EN, SE24_CLASS_DE/EN, SE24_INTERFACE_DE/EN
_OBJECT_TYPE_LABEL = bilingual_pattern(SE24_OBJECT_TYPE_DE, SE24_OBJECT_TYPE_EN)
_CLASS_OR_INTERFACE = f"{SE24_CLASS_EN}|{SE24_CLASS_DE}|{SE24_INTERFACE_EN}"
_OBJECT_TYPE_PATTERN = re.compile(
    rf'{_OBJECT_TYPE_LABEL}[^"]*"(?P<type>{_CLASS_OR_INTERFACE})"',
    re.IGNORECASE,
)

# Gridcell value extraction: matches gridcells with a quoted text value.
# Empty gridcells (checkboxes, buttons without text) are skipped.
_GRIDCELL_VALUE_RE = re.compile(r'gridcell "([^"]*)"')


# =============================================================================
# Helper Functions
# =============================================================================


def _extract_gridcell_rows(snapshot: str) -> list[list[str]]:
    """Extract data rows from a grid as lists of gridcell text values.

    Splits the snapshot by ``row "..."`` markers, skips header rows
    (containing ``columnheader``), and collects quoted gridcell values.
    Empty gridcells (checkboxes, buttons without text) are skipped, so
    positions correspond only to cells that carry a text value.

    The lookahead split on ``row "..."`` is intentionally broad — it will
    match header rows, status rows, and rowgroup separators alike.  We rely
    on two subsequent filters (``columnheader`` check and ``gridcell``
    presence) plus the caller's ``name[0].isalpha()`` guard to discard
    non-data rows.  This is simpler and more robust than anchoring the
    split to a specific YAML indentation level, which could break if the
    accessibility-tree nesting depth changes.
    """
    rows: list[list[str]] = []
    parts = re.split(r'(?=\s+- row ")', snapshot)
    for part in parts:
        if "columnheader" in part:
            continue
        if "gridcell" not in part:
            continue
        cells = _GRIDCELL_VALUE_RE.findall(part)
        if cells:
            rows.append(cells)
    return rows


def _map_visibility(visibility_str: str | None) -> SE24Visibility:
    """Map German/English visibility to standard value."""
    # Uses explicit constants: SE24_PRIVATE_DE/EN, SE24_PROTECTED_DE/EN
    if not visibility_str:
        return "public"
    visibility_lower = visibility_str.lower()
    if visibility_lower in (SE24_PRIVATE_EN.lower(), SE24_PRIVATE_DE.lower()):
        return "private"
    if visibility_lower in (SE24_PROTECTED_EN.lower(), SE24_PROTECTED_DE.lower()):
        return "protected"
    return "public"


def _extract_class_name(snapshot: str) -> str | None:
    """Extract class/interface name from heading."""
    match = _CLASS_HEADING_PATTERN.search(snapshot)
    if match:
        return match.group("name_de") or match.group("name_en")
    return None


def _determine_object_type(snapshot: str) -> SE24ObjectType:
    """Determine if this is a class or interface."""
    # Uses explicit constants: SE24_INTERFACE_DE/EN
    match = _OBJECT_TYPE_PATTERN.search(snapshot)
    if match:
        type_str = match.group("type").lower()
        if type_str in (SE24_INTERFACE_EN.lower(), SE24_INTERFACE_DE.lower()):
            return "interface"
    return "class"


def _is_initial_se24_screen(snapshot: str) -> bool:
    """Check if we're on the initial SE24 screen (no class displayed)."""
    # Uses explicit constants: SE24_INITIAL_SCREEN_DE, SE24_INITIAL_SCREEN_EN
    header_section = "\\n".join(snapshot.split("\\n")[:10])
    has_initial_heading = (
        f'heading "{SE24_INITIAL_SCREEN_EN}"' in header_section
        or f'heading "{SE24_INITIAL_SCREEN_DE}"' in header_section
    )
    return has_initial_heading


def _is_class_not_found(snapshot: str, class_name: str) -> bool:
    """Check if class/interface was not found (status bar message)."""
    # Uses explicit constants: SE24_NOT_EXIST_DE/EN, SE24_NOT_FOUND_DE/EN
    not_found_patterns = [
        f"{class_name} {SE24_NOT_EXIST_EN}",
        f"{class_name} {SE24_NOT_FOUND_DE}",
        f"{class_name} {SE24_NOT_EXIST_DE}",
        SE24_NOT_EXIST_EN,
        SE24_NOT_FOUND_DE,
        SE24_NOT_EXIST_DE,
    ]
    snapshot_lower = snapshot.lower()
    return any(pattern.lower() in snapshot_lower for pattern in not_found_patterns)


# =============================================================================
# Parser Functions
# =============================================================================


def _parse_method_rows(snapshot: str) -> list[SE24Method]:
    """Parse method rows from Methods tab grid using gridcell values.

    Grid columns (quoted gridcells only, empty cells skipped):
        [0] Method name  (may include IF_*~ prefix for interface methods)
        [1] Art          ("Instance Method" / "Static Method")
        [2] Visibility   ("Public" / "Private" / "Protected")
        [3] Method type  ("Leer" / "Empty" – ignored)
        [4] Description  (optional)
    """
    methods: list[SE24Method] = []

    for cells in _extract_gridcell_rows(snapshot):
        if len(cells) < 3:
            continue
        name = cells[0]
        # SAP ABAP identifiers always start with a letter (A-Z); this
        # filters out spurious rows (status bars, separators) that passed
        # through _extract_gridcell_rows.  Interface methods like
        # IF_SALV_GUI~METHOD also start with a letter, so no false negatives.
        if not name or not name[0].isalpha():
            continue
        method_kind = cells[1] if len(cells) > 1 else ""
        visibility = _map_visibility(cells[2] if len(cells) > 2 else None)
        # cells[3] is method type ("Leer"), skip
        desc = cells[4] if len(cells) > 4 else ""

        is_static = "static" in method_kind.lower()
        # EN: "Abstract Method", DE: "Abstrakte Methode" — the German
        # root "abstrakt" differs from English "abstract" (k vs c).
        is_abstract = "abstract" in method_kind.lower() or "abstrakt" in method_kind.lower()
        is_constructor = name.upper() in ("CONSTRUCTOR", "CLASS_CONSTRUCTOR")

        methods.append(
            SE24Method(
                name=name,
                visibility=visibility,
                is_static=is_static,
                is_abstract=is_abstract,
                is_constructor=is_constructor,
                description=desc.strip(),
            )
        )

    return methods


def _parse_attribute_rows(snapshot: str) -> list[SE24Attribute]:
    """Parse attribute rows from Attributes tab grid using gridcell values.

    Grid columns (quoted gridcells only, empty cells skipped):
        [0] Attribute name
        [1] Art           ("Constant" / "Static Attribute" / "Instance Attribute")
        [2] Visibility    ("Public" / "Private" / "Protected")
        [3] Typing        ("Type" / "Like" / etc.)
        [4] Type ref      ("STRING", "I", "ABAP_CHAR1", ...)
        [5] Description   (optional)
        [6] Initial value (optional)
    """
    attributes: list[SE24Attribute] = []

    for cells in _extract_gridcell_rows(snapshot):
        if len(cells) < 3:
            continue
        name = cells[0]
        # Same isalpha() guard as _parse_method_rows — SAP identifiers
        # always start with a letter, so this filters non-data rows.
        if not name or not name[0].isalpha():
            continue
        attr_kind = cells[1] if len(cells) > 1 else ""
        visibility = _map_visibility(cells[2] if len(cells) > 2 else None)
        # cells[3] is the typing keyword ("Type" / "Like") — skipped
        # because _GRIDCELL_VALUE_RE only captures quoted text values and
        # the typing column always has a quoted value, so it occupies a
        # stable position in the cells list.
        type_ref = cells[4] if len(cells) > 4 else ""
        desc = cells[5] if len(cells) > 5 else ""

        is_constant = "constant" in attr_kind.lower()
        is_static = is_constant or "static" in attr_kind.lower()

        attributes.append(
            SE24Attribute(
                name=name,
                visibility=visibility,
                is_static=is_static,
                is_constant=is_constant,
                type_ref=type_ref,
                description=desc.strip(),
            )
        )

    return attributes


def parse_se24_methods_snapshot(snapshot: AriaSnapshot) -> list[SE24Method]:
    """
    Parse methods from a SE24 Methods tab snapshot.

    Args:
        snapshot: YAML accessibility snapshot from the Methods tab

    Returns:
        List of parsed methods
    """
    return _parse_method_rows(snapshot)


def parse_se24_attributes_snapshot(snapshot: AriaSnapshot) -> list[SE24Attribute]:
    """
    Parse attributes from a SE24 Attributes tab snapshot.

    Args:
        snapshot: YAML accessibility snapshot from the Attributes tab

    Returns:
        List of parsed attributes
    """
    return _parse_attribute_rows(snapshot)


@dataclass
class SE24TabSnapshots:
    """Container for SE24 tab snapshots."""

    methods_tab: AriaSnapshot | None = None
    attributes_tab: AriaSnapshot | None = None
    interfaces_tab: AriaSnapshot | None = None


def parse_se24_snapshot(
    snapshot: AriaSnapshot,
    class_name: str,
    tab_snapshots: SE24TabSnapshots | None = None,
) -> SE24Entry | SE24Error:
    """
    Parse SE24 class/interface display snapshot into structured data.

    Args:
        snapshot: The main YAML accessibility snapshot from browser_snapshot
        class_name: The class/interface name being looked up
        tab_snapshots: Optional container with snapshots from each tab

    Returns:
        SE24Entry on success, SE24Error on parse failure
    """
    now = datetime.now(UTC)

    # Check if we're on initial screen
    if _is_initial_se24_screen(snapshot):
        return SE24Error(
            class_name=class_name,
            error=f"Class/interface '{class_name}' not found - still on initial screen",
            retrieved_at=now,
        )

    # Check for not found message
    if _is_class_not_found(snapshot, class_name):
        return SE24Error(
            class_name=class_name,
            error=f"Class/interface '{class_name}' not found",
            retrieved_at=now,
        )

    # Extract class name from heading
    found_name = _extract_class_name(snapshot)
    if not found_name:
        # Try to use provided name if we can't extract from heading
        found_name = class_name.upper()

    # Determine object type
    object_type = _determine_object_type(snapshot)

    # Parse tabs if provided
    tabs = tab_snapshots or SE24TabSnapshots()
    methods = parse_se24_methods_snapshot(tabs.methods_tab) if tabs.methods_tab else []
    attributes = parse_se24_attributes_snapshot(tabs.attributes_tab) if tabs.attributes_tab else []

    return SE24Entry(
        class_name=found_name,
        object_type=object_type,
        methods=methods,
        attributes=attributes,
        retrieved_at=now,
    )
