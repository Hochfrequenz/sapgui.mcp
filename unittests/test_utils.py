"""Tests for sapwebguimcp.utils module."""

import pytest

from sapwebguimcp.utils import is_sap_shortcut


class TestIsSapShortcut:
    """Tests for is_sap_shortcut function."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            # F-keys (should be shortcuts)
            ("F1", True),
            ("F3", True),
            ("F4", True),
            ("F5", True),
            ("F8", True),
            ("F12", True),
            ("F24", True),
            ("f8", True),  # lowercase
            # F-keys with modifiers
            ("Shift+F3", True),
            ("Ctrl+F4", True),
            ("Alt+F5", True),
            ("Control+F8", True),
            # Ctrl combinations (should be shortcuts)
            ("Ctrl+S", True),
            ("Ctrl+Y", True),
            ("Ctrl+C", True),
            ("Ctrl+V", True),
            ("ctrl+s", True),  # lowercase
            ("Control+S", True),
            ("control+s", True),
            # Non-shortcuts
            ("Enter", False),
            ("Tab", False),
            ("Escape", False),
            ("Space", False),
            ("Backspace", False),
            ("Delete", False),
            ("ArrowUp", False),
            ("ArrowDown", False),
            ("a", False),
            ("1", False),
            # Edge cases
            ("", False),
            ("Shift+Enter", False),  # Shift alone doesn't make it a shortcut
            ("Alt+Tab", False),  # Alt alone doesn't make it a shortcut
        ],
    )
    def test_is_sap_shortcut(self, key: str, expected: bool) -> None:
        """Test is_sap_shortcut with various key combinations."""
        assert is_sap_shortcut(key) == expected, f"is_sap_shortcut({key!r}) should be {expected}"
