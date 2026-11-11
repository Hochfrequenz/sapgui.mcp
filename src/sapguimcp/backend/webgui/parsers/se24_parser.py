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
from sapguimcp.lang import alt_of
from sapguimcp.lang.schema import LanguagePack, Visibility
from sapguimcp.lang.text import compiled
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
    "map_visibility",
    "parse_se24_snapshot",
    "parse_se24_methods_snapshot",
    "parse_se24_attributes_snapshot",
    "SE24TabSnapshots",
]

# =============================================================================
# Regex Patterns
# =============================================================================

_HEADING_TEXT = re.compile(r'heading "([^"]*)"')
_NAME_CHARS = r"[A-Za-z0-9_/ ]+"
"""Heading name group: the object name, possibly preceded by its type word ("Klasse CL_X", "Class CL_X")."""


def _object_type_pattern(t: LanguagePack) -> re.Pattern[str]:
    """Object type value after its label: ``Object Type ... "Class"`` / ``"Interface"``."""
    return compiled(
        rf'(?i){t.se24.object_type.alt}[^"]*"(?P<type>{alt_of(t.se24.class_label, t.se24.interface_label)})"'
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


_VISIBILITY_LITERALS: dict[Visibility, SE24Visibility] = {
    Visibility.PUBLIC: "public",
    Visibility.PROTECTED: "protected",
    Visibility.PRIVATE: "private",
}


def map_visibility(t: LanguagePack, raw: str | None, *, exact: bool = True) -> SE24Visibility:
    """Map a visibility text in any pack language to the canonical value; unknown or empty is public.

    ``exact`` compares the whole text (the WebGUI grid cell); otherwise a text that merely contains the
    visibility word counts (the desktop table control cell).
    """
    if not raw:
        return "public"
    for member in (Visibility.PRIVATE, Visibility.PROTECTED):
        text = t.se24.visibility[member]
        if text.equals(raw) if exact else text.contains(raw):
            return _VISIBILITY_LITERALS[member]
    return "public"


def _extract_class_name(snapshot: str, t: LanguagePack) -> str | None:
    """Extract class/interface name from the heading (``Class Builder: Display Class CL_X``)."""
    for heading in _HEADING_TEXT.finditer(snapshot):
        match = t.se24.display_title.search(heading.group(1), name=_NAME_CHARS)
        if match is not None and (tokens := match.group("name").split()):
            return tokens[-1].upper()
    return None


def _determine_object_type(snapshot: str, t: LanguagePack) -> SE24ObjectType:
    """Determine if this is a class or interface."""
    match = _object_type_pattern(t).search(snapshot)
    if match and t.se24.interface_label.equals(match.group("type")):
        return "interface"
    return "class"


def _is_initial_se24_screen(snapshot: str, t: LanguagePack) -> bool:
    """Check if we're on the initial SE24 screen (no class displayed)."""
    header_section = "\\n".join(snapshot.split("\\n")[:10])
    return any(f'heading "{variant}"' in header_section for variant in t.se24.initial_screen)


def _is_class_not_found(snapshot: str, t: LanguagePack) -> bool:
    """Check if class/interface was not found (status bar message)."""
    return t.common.does_not_exist.contains(snapshot)


# =============================================================================
# Parser Functions
# =============================================================================


def _parse_method_rows(snapshot: str, t: LanguagePack) -> list[SE24Method]:
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
        visibility = map_visibility(t, cells[2] if len(cells) > 2 else None)
        # cells[3] is method type ("Leer"), skip
        desc = cells[4] if len(cells) > 4 else ""

        is_static = t.se24.static.contains(method_kind)
        is_abstract = t.se24.abstract.contains(method_kind)
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


def _parse_attribute_rows(snapshot: str, t: LanguagePack) -> list[SE24Attribute]:
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
        visibility = map_visibility(t, cells[2] if len(cells) > 2 else None)
        # cells[3] is the typing keyword ("Type" / "Like") — skipped
        # because _GRIDCELL_VALUE_RE only captures quoted text values and
        # the typing column always has a quoted value, so it occupies a
        # stable position in the cells list.
        type_ref = cells[4] if len(cells) > 4 else ""
        desc = cells[5] if len(cells) > 5 else ""

        is_constant = t.se24.constant.contains(attr_kind)
        is_static = is_constant or t.se24.static.contains(attr_kind)

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


def parse_se24_methods_snapshot(snapshot: AriaSnapshot, t: LanguagePack) -> list[SE24Method]:
    """
    Parse methods from a SE24 Methods tab snapshot.

    Args:
        snapshot: YAML accessibility snapshot from the Methods tab
        t: Language pack of the session

    Returns:
        List of parsed methods
    """
    return _parse_method_rows(snapshot, t)


def parse_se24_attributes_snapshot(snapshot: AriaSnapshot, t: LanguagePack) -> list[SE24Attribute]:
    """
    Parse attributes from a SE24 Attributes tab snapshot.

    Args:
        snapshot: YAML accessibility snapshot from the Attributes tab
        t: Language pack of the session

    Returns:
        List of parsed attributes
    """
    return _parse_attribute_rows(snapshot, t)


@dataclass
class SE24TabSnapshots:
    """Container for SE24 tab snapshots."""

    methods_tab: AriaSnapshot | None = None
    attributes_tab: AriaSnapshot | None = None
    interfaces_tab: AriaSnapshot | None = None


def parse_se24_snapshot(
    snapshot: AriaSnapshot,
    class_name: str,
    t: LanguagePack,
    tab_snapshots: SE24TabSnapshots | None = None,
) -> SE24Entry | SE24Error:
    """
    Parse SE24 class/interface display snapshot into structured data.

    Args:
        snapshot: The main YAML accessibility snapshot from browser_snapshot
        class_name: The class/interface name being looked up
        t: Language pack of the session
        tab_snapshots: Optional container with snapshots from each tab

    Returns:
        SE24Entry on success, SE24Error on parse failure
    """
    now = datetime.now(UTC)

    # Check if we're on initial screen
    if _is_initial_se24_screen(snapshot, t):
        return SE24Error(
            class_name=class_name,
            error=f"Class/interface '{class_name}' not found - still on initial screen",
            retrieved_at=now,
        )

    # Check for not found message
    if _is_class_not_found(snapshot, t):
        return SE24Error(
            class_name=class_name,
            error=f"Class/interface '{class_name}' not found",
            retrieved_at=now,
        )

    # Extract class name from heading
    found_name = _extract_class_name(snapshot, t)
    if not found_name:
        # Try to use provided name if we can't extract from heading
        found_name = class_name.upper()

    # Determine object type
    object_type = _determine_object_type(snapshot, t)

    # Parse tabs if provided
    tabs = tab_snapshots or SE24TabSnapshots()
    methods = parse_se24_methods_snapshot(tabs.methods_tab, t) if tabs.methods_tab else []
    attributes = parse_se24_attributes_snapshot(tabs.attributes_tab, t) if tabs.attributes_tab else []

    return SE24Entry(
        class_name=found_name,
        object_type=object_type,
        methods=methods,
        attributes=attributes,
        retrieved_at=now,
    )
