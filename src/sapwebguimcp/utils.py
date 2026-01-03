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
