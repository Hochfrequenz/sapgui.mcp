"""
Parser for SE37 (Function Builder) ARIA snapshots.

Extracts function module metadata from SE37 display screens, handling:
- Function module name from heading
- Import/Export/Changing/Tables parameters from grids
- Exceptions from grid
- German and English label support
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import (
    SE37_DISPLAY_PREFIX_EN,
    SE37_DISPLAY_SUFFIX_DE,
    SE37_INITIAL_SCREEN_DE,
    SE37_INITIAL_SCREEN_EN,
    SE37_NOT_EXIST_DE,
    SE37_NOT_EXIST_EN,
    SE37_NOT_FOUND_DE,
    SE37_NOT_FOUND_EN,
    bilingual_pattern,
)
from sapguimcp.models.se37_models import (
    SE37Entry,
    SE37Error,
    SE37Exception,
    SE37Parameter,
    SE37ParameterCategory,
    SE37TypingMethod,
)

logger = logging.getLogger(__name__)

__all__ = [
    "parse_se37_snapshot",
    "parse_se37_parameters_snapshot",
    "parse_se37_exceptions_snapshot",
    "SE37TabSnapshots",
]

# =============================================================================
# Regex Patterns
# =============================================================================

# Function module name from heading
# Uses explicit constants: SE37_DISPLAY_SUFFIX_DE, SE37_DISPLAY_PREFIX_EN
# German: "Function Builder: RFC_READ_TABLE anzeigen"
# English: "Function Builder: Display RFC_READ_TABLE"
_FM_HEADING_PATTERN = re.compile(
    rf'heading "Function Builder:\s*(?:(?P<fm_de>[A-Z0-9_/]+)\s+{SE37_DISPLAY_SUFFIX_DE}'
    rf"|{SE37_DISPLAY_PREFIX_EN}\s+(?P<fm_en>[A-Z0-9_/]+))\"",
    re.IGNORECASE,
)

# Parameter row pattern - extracts data from row description
# Uses explicit constants: SE37_DISPLAY_SUFFIX_DE ("anzeigen" button), SE37_DISPLAY_PREFIX_EN ("Display" button)
# Format: "PARAM_NAME LIKE|TYPE REF_TYPE [DEFAULT] [optional_flag] Description Button"
_PARAM_ROW_PATTERN = re.compile(
    r'row "(?P<name>[A-Z0-9_]+)\s+(?P<typing>LIKE|TYPE)\s+(?P<ref>[A-Z0-9_/-]+)'
    r"(?:\s+(?P<default>\S+))?"
    r"(?:\s+)?"
    r'(?P<desc>[^"]*?)'
    rf'(?:\s+{bilingual_pattern(SE37_DISPLAY_SUFFIX_DE, SE37_DISPLAY_PREFIX_EN)})?"\s*:',
    re.IGNORECASE,
)

# Exception row pattern
# Uses explicit constants: SE37_DISPLAY_SUFFIX_DE, SE37_DISPLAY_PREFIX_EN
# Format: "EXCEPTION_NAME Description Button"
_DISPLAY_BUTTON = bilingual_pattern(SE37_DISPLAY_SUFFIX_DE, SE37_DISPLAY_PREFIX_EN)
_EXCEPTION_ROW_PATTERN = re.compile(
    rf'row "(?P<name>[A-Z0-9_]+)\s+(?P<desc>[^"]+?)(?:\s+{_DISPLAY_BUTTON})?"\s*:',
    re.IGNORECASE,
)

# Check if checkbox is checked
_CHECKBOX_CHECKED_PATTERN = re.compile(r"checkbox[^]]*\[checked\]", re.IGNORECASE)

# Tab selection pattern
_TAB_SELECTED_PATTERN = re.compile(r'tab "(?P<tab>[^"]+)"\s*\[selected\]', re.IGNORECASE)


# =============================================================================
# Parser Functions
# =============================================================================


def _extract_function_module_name(snapshot: str) -> str | None:
    """Extract function module name from heading."""
    match = _FM_HEADING_PATTERN.search(snapshot)
    if match:
        return match.group("fm_de") or match.group("fm_en")
    return None


def _get_selected_tab(snapshot: str) -> str | None:
    """Get the currently selected tab name."""
    match = _TAB_SELECTED_PATTERN.search(snapshot)
    if match:
        return match.group("tab")
    return None


def _get_checkbox_flags(snapshot: str, match: re.Match[str], category: SE37ParameterCategory) -> tuple[bool, bool]:
    """Extract optional and pass_by_value flags from checkbox states."""
    row_start = match.start()
    row_end = snapshot.find("\n        - row", row_start + 1)
    if row_end == -1:
        row_end = len(snapshot)
    row_content = snapshot[row_start:row_end]
    checked_count = len(_CHECKBOX_CHECKED_PATTERN.findall(row_content))

    if category == "import":
        return checked_count >= 1, checked_count >= 2
    if category == "export":
        return False, checked_count >= 1
    if category == "tables":
        return checked_count >= 1, False
    if category == "changing":
        return checked_count >= 1, checked_count >= 2
    return False, False


def _parse_parameter_rows(snapshot: str, category: SE37ParameterCategory) -> list[SE37Parameter]:
    """Parse parameter rows from a grid section."""
    parameters: list[SE37Parameter] = []

    for match in _PARAM_ROW_PATTERN.finditer(snapshot):
        name = match.group("name")
        typing_str = match.group("typing").upper()
        ref_type = match.group("ref")
        default = match.group("default")
        desc = re.sub(r"\s+$", "", match.group("desc").strip())
        typing: SE37TypingMethod = "LIKE" if typing_str == "LIKE" else "TYPE"
        optional, pass_by_value = _get_checkbox_flags(snapshot, match, category)

        parameters.append(
            SE37Parameter(
                name=name,
                category=category,
                typing=typing,
                reference_type=ref_type,
                default_value=default if default and default.strip() else None,
                optional=optional,
                pass_by_value=pass_by_value,
                description=desc,
            )
        )

    return parameters


def _parse_exception_rows(snapshot: str) -> list[SE37Exception]:
    """Parse exception rows from exceptions grid."""
    exceptions: list[SE37Exception] = []

    for match in _EXCEPTION_ROW_PATTERN.finditer(snapshot):
        name = match.group("name")
        desc = match.group("desc").strip()

        # Skip if this looks like a parameter row (has LIKE/TYPE)
        if " LIKE " in match.group(0) or " TYPE " in match.group(0):
            continue

        exceptions.append(
            SE37Exception(
                name=name,
                description=desc,
            )
        )

    return exceptions


def _is_initial_se37_screen(snapshot: str) -> bool:
    """Check if we're on the initial SE37 screen (no function module displayed)."""
    # Uses explicit constants: SE37_INITIAL_SCREEN_DE, SE37_INITIAL_SCREEN_EN
    header_section = "\n".join(snapshot.split("\n")[:10])
    has_initial_heading = (
        f'heading "{SE37_INITIAL_SCREEN_DE}"' in header_section
        or f'heading "{SE37_INITIAL_SCREEN_EN}"' in header_section
    )
    return has_initial_heading


def _is_fm_not_found(snapshot: str, fm_name: str) -> bool:
    """Check if function module was not found (status bar message)."""
    # Uses explicit constants: SE37_NOT_EXIST_DE/EN, SE37_NOT_FOUND_DE/EN
    not_found_patterns = [
        f"{fm_name} {SE37_NOT_EXIST_DE}",
        f"{fm_name} {SE37_NOT_EXIST_EN}",
        f"{fm_name} not found",
        SE37_NOT_FOUND_DE,
        SE37_NOT_FOUND_EN,
    ]
    snapshot_lower = snapshot.lower()
    return any(pattern.lower() in snapshot_lower for pattern in not_found_patterns)


def parse_se37_parameters_snapshot(snapshot: AriaSnapshot, category: SE37ParameterCategory) -> list[SE37Parameter]:
    """
    Parse parameters from a SE37 tab snapshot.

    Args:
        snapshot: YAML accessibility snapshot from the Import/Export/Changing/Tables tab
        category: Which parameter category this is

    Returns:
        List of parsed parameters
    """
    return _parse_parameter_rows(snapshot, category)


def parse_se37_exceptions_snapshot(snapshot: AriaSnapshot) -> list[SE37Exception]:
    """
    Parse exceptions from a SE37 Exceptions tab snapshot.

    Args:
        snapshot: YAML accessibility snapshot from the Exceptions tab

    Returns:
        List of parsed exceptions
    """
    return _parse_exception_rows(snapshot)


@dataclass
class SE37TabSnapshots:
    """Container for SE37 tab snapshots."""

    import_tab: AriaSnapshot | None = None
    export_tab: AriaSnapshot | None = None
    changing_tab: AriaSnapshot | None = None
    tables_tab: AriaSnapshot | None = None
    exceptions_tab: AriaSnapshot | None = None


def parse_se37_snapshot(
    snapshot: AriaSnapshot,
    fm_name: str,
    tab_snapshots: SE37TabSnapshots | None = None,
) -> SE37Entry | SE37Error:
    """
    Parse SE37 function module display snapshot into structured data.

    Args:
        snapshot: The main YAML accessibility snapshot from browser_snapshot
        fm_name: The function module name being looked up
        tab_snapshots: Optional container with snapshots from each tab

    Returns:
        SE37Entry on success, SE37Error on parse failure
    """
    now = datetime.now(UTC)

    # Check if we're on initial screen
    if _is_initial_se37_screen(snapshot):
        return SE37Error(
            function_module=fm_name,
            error=f"Function module '{fm_name}' not found - still on initial screen",
            retrieved_at=now,
        )

    # Check for not found message
    if _is_fm_not_found(snapshot, fm_name):
        return SE37Error(
            function_module=fm_name,
            error=f"Function module '{fm_name}' not found",
            retrieved_at=now,
        )

    # Extract function module name from heading
    found_fm = _extract_function_module_name(snapshot)
    if not found_fm:
        # Try to use provided name if we can't extract from heading
        found_fm = fm_name.upper()

    # Parse parameters from each tab if provided
    tabs = tab_snapshots or SE37TabSnapshots()
    import_params = parse_se37_parameters_snapshot(tabs.import_tab, "import") if tabs.import_tab else []
    export_params = parse_se37_parameters_snapshot(tabs.export_tab, "export") if tabs.export_tab else []
    changing_params = parse_se37_parameters_snapshot(tabs.changing_tab, "changing") if tabs.changing_tab else []
    tables_params = parse_se37_parameters_snapshot(tabs.tables_tab, "tables") if tabs.tables_tab else []
    exceptions = parse_se37_exceptions_snapshot(tabs.exceptions_tab) if tabs.exceptions_tab else []

    return SE37Entry(
        function_module=found_fm,
        import_parameters=import_params,
        export_parameters=export_params,
        changing_parameters=changing_params,
        tables_parameters=tables_params,
        exceptions=exceptions,
        retrieved_at=now,
    )
