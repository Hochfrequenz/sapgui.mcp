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

from sapwebguimcp.models.se24_models import (
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
# German: "Class Builder: CL_SALV_TABLE anzeigen"
# English: "Class Builder: Display CL_SALV_TABLE"
_CLASS_HEADING_PATTERN = re.compile(
    r'heading "(?:Class Builder|Klassenpflege):\s*'
    r"(?:(?P<name_de>[A-Z0-9_/]+)\\s+anzeigen|Display\\s+(?P<name_en>[A-Z0-9_/]+))\"",
    re.IGNORECASE,
)

# Determine if class or interface from screen content
# German: "Klasse" / "Interface"
# English: "Class" / "Interface"
_OBJECT_TYPE_PATTERN = re.compile(
    r'(?:Object\\s+Type|Objekttyp)[^"]*"(?P<type>Class|Klasse|Interface)"',
    re.IGNORECASE,
)

# Method row pattern - extract method info from grid row
# Format varies, but typically: "METHOD_NAME visibility [static] [abstract] Description"
_METHOD_ROW_PATTERN = re.compile(
    r'row "(?P<name>[A-Z0-9_]+)'
    r"(?:\\s+(?P<visibility>Public|Private|Protected|Öffentlich|Privat|Geschützt))?"
    r"(?:\\s+(?P<static>Static|Statisch))?"
    r"(?:\\s+(?P<abstract>Abstract|Abstrakt))?"
    r'(?:\\s+(?P<desc>[^"]*))?"\\s*:',
    re.IGNORECASE,
)

# Attribute row pattern
_ATTRIBUTE_ROW_PATTERN = re.compile(
    r'row "(?P<name>[A-Z0-9_]+)'
    r"(?:\\s+(?P<visibility>Public|Private|Protected|Öffentlich|Privat|Geschützt))?"
    r"(?:\\s+(?P<type_ref>[A-Z0-9_]+))?"
    r'(?:\\s+(?P<desc>[^"]*))?"\\s*:',
    re.IGNORECASE,
)

# Check if checkbox is checked (for static, constant, etc.)
_CHECKBOX_CHECKED_PATTERN = re.compile(r"checkbox[^]]*\[checked\]", re.IGNORECASE)


# =============================================================================
# Helper Functions
# =============================================================================


def _map_visibility(visibility_str: str | None) -> SE24Visibility:
    """Map German/English visibility to standard value."""
    if not visibility_str:
        return "public"
    visibility_lower = visibility_str.lower()
    if visibility_lower in ("private", "privat"):
        return "private"
    if visibility_lower in ("protected", "geschützt"):
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
    match = _OBJECT_TYPE_PATTERN.search(snapshot)
    if match:
        type_str = match.group("type").lower()
        if type_str == "interface":
            return "interface"
    return "class"


def _is_initial_se24_screen(snapshot: str) -> bool:
    """Check if we're on the initial SE24 screen (no class displayed)."""
    header_section = "\\n".join(snapshot.split("\\n")[:10])
    has_initial_heading = (
        'heading "Class Builder: Initial"' in header_section
        or 'heading "Klassenpflege: Einstieg"' in header_section
        or 'heading "Class Builder: Einstieg"' in header_section
    )
    return has_initial_heading


def _is_class_not_found(snapshot: str, class_name: str) -> bool:
    """Check if class/interface was not found (status bar message)."""
    not_found_patterns = [
        f"{class_name} does not exist",
        f"{class_name} nicht vorhanden",
        f"{class_name} existiert nicht",
        "does not exist",
        "nicht vorhanden",
        "existiert nicht",
    ]
    snapshot_lower = snapshot.lower()
    return any(pattern.lower() in snapshot_lower for pattern in not_found_patterns)


# =============================================================================
# Parser Functions
# =============================================================================


def _parse_method_rows(snapshot: str) -> list[SE24Method]:
    """Parse method rows from Methods tab grid."""
    methods: list[SE24Method] = []

    for match in _METHOD_ROW_PATTERN.finditer(snapshot):
        name = match.group("name")
        visibility = _map_visibility(match.group("visibility"))
        is_static = match.group("static") is not None
        is_abstract = match.group("abstract") is not None
        desc = match.group("desc") or ""

        # Check for constructor
        is_constructor = name.upper() == "CONSTRUCTOR" or name.upper() == "CLASS_CONSTRUCTOR"

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
    """Parse attribute rows from Attributes tab grid."""
    attributes: list[SE24Attribute] = []

    for match in _ATTRIBUTE_ROW_PATTERN.finditer(snapshot):
        name = match.group("name")
        visibility = _map_visibility(match.group("visibility"))
        type_ref = match.group("type_ref") or ""
        desc = match.group("desc") or ""

        # Get row content to check checkboxes
        row_start = match.start()
        row_end = snapshot.find("\\n        - row", row_start + 1)
        if row_end == -1:
            row_end = len(snapshot)
        row_content = snapshot[row_start:row_end]

        # Check for static and constant flags via checkboxes
        checked_count = len(_CHECKBOX_CHECKED_PATTERN.findall(row_content))
        is_static = checked_count >= 1
        is_constant = checked_count >= 2

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


def parse_se24_methods_snapshot(snapshot: str) -> list[SE24Method]:
    """
    Parse methods from a SE24 Methods tab snapshot.

    Args:
        snapshot: YAML accessibility snapshot from the Methods tab

    Returns:
        List of parsed methods
    """
    return _parse_method_rows(snapshot)


def parse_se24_attributes_snapshot(snapshot: str) -> list[SE24Attribute]:
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

    methods_tab: str | None = None
    attributes_tab: str | None = None
    interfaces_tab: str | None = None


def parse_se24_snapshot(
    snapshot: str,
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
