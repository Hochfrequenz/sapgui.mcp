"""Tests for tool call logging middleware identity injection."""

_LOGGER_NAME = "sapguimcp.middleware.logging"


def test_extract_sap_user_js_exists():
    """The JS file should be loadable and contain expected selectors."""
    from importlib import resources

    content = resources.files("sapguimcp.backend.webgui.js").joinpath("extract_sap_user.js").read_text(encoding="utf-8")
    assert "sysInfoAreaMenuItemSAPITS_MBAR_USER" in content
    assert "lsdata" in content
    assert "aria-label" in content
