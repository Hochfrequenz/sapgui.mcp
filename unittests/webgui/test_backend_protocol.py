"""Tests for CheckActivateResult and backend structure."""


def test_webgui_backend_has_expected_methods() -> None:
    """WebGuiBackend must have the core backend methods."""
    from sapguimcp.backend.webgui.backend import WebGuiBackend

    for attr in ("backend_type", "login", "enter_transaction", "get_screen_info", "press_key"):
        assert hasattr(WebGuiBackend, attr), f"WebGuiBackend missing: {attr}"
