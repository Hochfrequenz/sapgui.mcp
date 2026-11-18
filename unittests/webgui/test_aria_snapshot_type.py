"""Tests for the AriaSnapshot type alias."""

from sapguimcp.backend.webgui.types import AriaSnapshot


def test_aria_snapshot_is_str_subtype() -> None:
    """AriaSnapshot should be usable wherever str is expected."""
    snapshot = AriaSnapshot('heading "Test"')
    assert isinstance(snapshot, str)
    assert "Test" in snapshot


def test_aria_snapshot_distinct_from_raw_str() -> None:
    """AriaSnapshot should be a NewType, not just str."""
    snapshot = AriaSnapshot('body:\n  heading "Title"')
    assert snapshot == 'body:\n  heading "Title"'
