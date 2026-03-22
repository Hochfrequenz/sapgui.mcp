"""Integration tests for GuiTree against the SE80 Object Navigator tree.

SE80 always shows a tree control in its left panel (the repository browser).
Tests are read-only — they inspect the tree but don't double-click or modify.
"""

import sys
import time

import pytest

from unittests.conftest import is_sap_integration_test_machine

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only"),
    pytest.mark.skipif(
        not is_sap_integration_test_machine(),
        reason="SAP integration tests only run on authorized machines",
    ),
]


def _navigate_to_se80(session):
    """Navigate to SE80 and wait for the tree to load."""
    okcode = session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/nSE80"
    session.find_by_id("wnd[0]").send_v_key(0)
    time.sleep(1)


def _find_se80_tree(session):
    """Find the tree control in SE80's left panel."""
    from sapwebguimcp.sapgui.components.tree import GuiTree

    _navigate_to_se80(session)
    tree_id = "wnd[0]/shellcont/shell/shellcont[1]/shell/shellcont[2]/shell"
    try:
        elem = session.find_by_id(tree_id)
        if isinstance(elem, GuiTree):
            return elem
    except Exception:
        pass
    pytest.skip("Could not find SE80 tree control")


@pytest.fixture
def se80_tree(sap_desktop_session):
    """Provide a GuiTree from SE80 for testing."""
    tree = _find_se80_tree(sap_desktop_session)
    yield tree
    # Navigate back to avoid leaving SE80 open for next test
    okcode = sap_desktop_session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/n"
    sap_desktop_session.find_by_id("wnd[0]").send_v_key(0)


# ---------------------------------------------------------------------------
# Pre-existing GuiTree methods (were never integration-tested)
# ---------------------------------------------------------------------------


class TestGuiTreePreExisting:
    """Test pre-existing GuiTree methods against a real SAP tree."""

    def test_tree_type(self, se80_tree):
        assert se80_tree.tree_type in (0, 1, 2)

    def test_top_node(self, se80_tree):
        assert isinstance(se80_tree.top_node, str)
        assert len(se80_tree.top_node) > 0

    def test_get_node_text_by_key(self, se80_tree):
        key = se80_tree.top_node
        text = se80_tree.get_node_text_by_key(key)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_get_node_children_count(self, se80_tree):
        key = se80_tree.top_node
        count = se80_tree.get_node_children_count(key)
        assert isinstance(count, int)
        assert count >= 0

    def test_selected_node_after_select(self, se80_tree):
        key = se80_tree.top_node
        se80_tree.select_node(key)
        assert se80_tree.selected_node == key

    def test_select_and_expand_node(self, se80_tree):
        key = se80_tree.top_node
        se80_tree.select_node(key)
        if se80_tree.is_folder(key):
            se80_tree.expand_node(key)
            assert se80_tree.get_node_children_count(key) > 0
            se80_tree.collapse_node(key)


# ---------------------------------------------------------------------------
# New methods added in PR #505 (PDF-verified)
# ---------------------------------------------------------------------------


class TestGuiTreeNewMethods:
    """Test new GuiTree methods (from PR #505) against a real SAP tree."""

    def test_is_folder(self, se80_tree):
        key = se80_tree.top_node
        result = se80_tree.is_folder(key)
        assert isinstance(result, bool)

    def test_get_node_style(self, se80_tree):
        key = se80_tree.top_node
        style = se80_tree.get_node_style(key)
        assert isinstance(style, int)

    def test_changeable_property_inherited(self, se80_tree):
        """Verify the inherited `changeable` property works (was wrongly
        planned as is_changeable() method)."""
        assert isinstance(se80_tree.changeable, bool)
