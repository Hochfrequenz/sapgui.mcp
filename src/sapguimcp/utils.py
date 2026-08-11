"""Shared utility functions for SAP WebGUI MCP."""

import logging
from datetime import datetime
from typing import Literal

logger = logging.getLogger(__name__)

SapLanguage = Literal["DE", "EN"]


def as_sap_language(value: str) -> SapLanguage:
    """Narrow a configured language string to the two values date formatting handles.

    ``sap-mcp-config`` still guarantees a system's language is ``DE`` or ``EN``,
    but since 1.1.0 it *types* the field as ``str``: the check moved off the
    field onto the ``Config`` model validator, so that one invalid language no
    longer aborts validation and hides every other error.  That leaves the
    static type too wide to assign straight to :data:`SapLanguage`.

    Narrowing at runtime rather than with a ``cast`` keeps this correct even if
    the upstream guarantee changes again.  Anything unrecognised becomes ``EN``,
    which is the same default the config layer applies for a missing language —
    but it is logged, because an EN fallback formats dates as ``MM/DD/YYYY``,
    and typing that into a DE selection screen silently selects the wrong range.
    """
    normalized = value.strip().upper()
    if normalized == "DE":
        return "DE"
    if normalized != "EN":
        logger.warning(
            "unexpected configured language, falling back to EN",
            extra={"language": value},
        )
    return "EN"


def format_sap_date(iso_date: str, language: SapLanguage) -> str:
    """
    Convert ISO date (YYYY-MM-DD) to SAP locale format.

    Args:
        iso_date: Date string in YYYY-MM-DD format (e.g., "2026-02-22")
        language: SAP language code ("DE" or "EN")

    Returns:
        Formatted date string:
        - DE: DD.MM.YYYY (e.g., "22.02.2026")
        - EN: MM/DD/YYYY (e.g., "02/22/2026")

    Raises:
        ValueError: If iso_date is not in YYYY-MM-DD format
    """
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Expected YYYY-MM-DD format, got: {iso_date}") from e

    if language == "DE":
        return dt.strftime("%d.%m.%Y")
    return dt.strftime("%m/%d/%Y")
