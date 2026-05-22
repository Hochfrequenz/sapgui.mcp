"""Map key names to SAP GUI VKey numbers.

SAP GUI's SendVKey accepts a numeric VKey code (0-36+). This module maps
human-readable key names (as used by the MCP protocol's press_key method)
to those numbers.

Note: These are SAP VKeys, NOT Windows virtual key codes. "Escape" maps
to VKey 12 (F12/Cancel in SAP), not the literal Escape key.
"""

from __future__ import annotations

# Standard SAP VKey table (from SAP GUI Scripting API, Table GUI_FKEY)
_VKEY_MAP: dict[str, int] = {
    "enter": 0,
    **{f"f{i}": i for i in range(1, 13)},
    **{f"shift+f{i}": 12 + i for i in range(1, 13)},
    **{f"ctrl+f{i}": 24 + i for i in range(1, 13)},
    # SAP-conventional aliases (not literal OS keys — see module docstring)
    "escape": 12,  # F12 = Cancel in SAP
    "backspace": 3,  # F3 = Back in SAP
    "ctrl+s": 11,  # SAP Save = Ctrl+S → maps to VKey 11 (same as F11)
    "ctrl+shift+f3": 24,  # Ctrl+Shift+F3 mapped as Shift+F12
}


def key_to_vkey(key: str) -> int:
    """Convert a key name to a SAP VKey number.

    Args:
        key: Key name like "Enter", "F5", "Ctrl+F2", "Escape".
              Case-insensitive.

    Returns:
        The SAP VKey number.

    Raises:
        KeyError: If the key name is not recognized.
    """
    normalized = key.strip().lower()
    if normalized not in _VKEY_MAP:
        raise KeyError(f"Unknown key '{key}'. Known keys: Enter, F1-F12, Shift+F1-F12, Ctrl+F1-F12, Escape")
    return _VKEY_MAP[normalized]
