"""Tests for log_feedback tags parameter coercion (GH-554)."""

import pytest

from sapwebguimcp.tools.feedback_tools import _coerce_tags


class TestCoerceTags:
    """Test _coerce_tags validator handles various input formats."""

    def test_none_passthrough(self) -> None:
        assert _coerce_tags(None) is None

    def test_list_passthrough(self) -> None:
        assert _coerce_tags(["a", "b"]) == ["a", "b"]

    def test_empty_list_passthrough(self) -> None:
        assert _coerce_tags([]) == []

    def test_json_string_array(self) -> None:
        """GH-554: MCP client sends stringified JSON array."""
        result = _coerce_tags('["problem", "error-handling"]')
        assert result == ["problem", "error-handling"]

    def test_json_string_empty_array(self) -> None:
        result = _coerce_tags("[]")
        assert result == []

    def test_bare_string_wrapped(self) -> None:
        """Single string tag gets wrapped in a list."""
        assert _coerce_tags("problem") == ["problem"]

    def test_json_string_non_array(self) -> None:
        """JSON string that parses to non-array is treated as bare string."""
        assert _coerce_tags('"just-a-string"') == ['"just-a-string"']

    def test_json_string_with_mixed_types(self) -> None:
        """JSON array with non-string elements gets str-coerced."""
        result = _coerce_tags('[1, "two", true]')
        assert result == ["1", "two", "True"]
