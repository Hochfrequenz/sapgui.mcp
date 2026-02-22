"""Utility functions for SAP WebGUI MCP."""


def is_sap_shortcut(key: str) -> bool:
    """Check if a key is an SAP shortcut that typically triggers status bar feedback.

    SAP shortcuts include:
    - F-keys (F1-F12, with or without Shift/Ctrl/Alt modifiers)
    - Ctrl+* combinations (e.g., Ctrl+S for save)

    Args:
        key: Keyboard key string (e.g., "F8", "Ctrl+S", "Shift+F3", "Enter")

    Returns:
        True if the key is a shortcut that should trigger status bar reading.

    Examples:
        >>> is_sap_shortcut("F8")
        True
        >>> is_sap_shortcut("Ctrl+S")
        True
        >>> is_sap_shortcut("Shift+F3")
        True
        >>> is_sap_shortcut("Enter")
        False
        >>> is_sap_shortcut("Tab")
        False
    """
    key_upper = key.upper()

    # Check for Ctrl/Control modifier
    if "CONTROL" in key_upper or "CTRL" in key_upper:
        return True

    # Check for F-keys (F1-F24, with or without modifiers)
    # Split by + to handle modifiers like "Shift+F3"
    parts = key_upper.replace("+", " ").split()
    for part in parts:
        # Match F followed by 1-2 digits
        if len(part) >= 2 and part[0] == "F" and part[1:].isdigit():
            return True

    return False


def format_sap_date(iso_date: str, language: str) -> str:
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
    parts = iso_date.split("-")
    if len(parts) != 3:
        raise ValueError(f"Expected YYYY-MM-DD format, got: {iso_date}")

    year, month, day = parts[0], parts[1], parts[2]

    if language.upper() == "DE":
        return f"{day}.{month}.{year}"
    return f"{month}/{day}/{year}"
