"""Unit tests for dump_tree BDT fallback."""

from unittest.mock import MagicMock, PropertyMock

import pytest
from sapsucker.components.base import GuiComponentType, _dump_tree_recursive, _probe_bdt_fields

# Real component type numbers, taken from sapsucker so that the mocks cannot drift from what it probes with.
# (sapsucker < 1.5 probed radio buttons, checkboxes and labels with 42, 43 and 46 instead of 41, 42 and 30;
# 1.5.0 derives the probe types from the enum, so these tests need >= 1.5.0.)
_TEXT_FIELD = int(GuiComponentType.GuiTextField)
_LABEL = int(GuiComponentType.GuiLabel)


def _make_normal_container(children_data):
    """Mock a normal container with Children.Count/Item."""
    com = MagicMock()
    com.Children.Count = len(children_data)
    com.Children.Item = lambda i: children_data[i]
    com.ContainerType = True
    com.Id = "/app/con[0]/ses[0]/wnd[0]/usr/container"
    return com


def _make_bdt_container():
    """Mock a BDT container where Children.Count throws."""
    com = MagicMock()
    type(com.Children).Count = PropertyMock(side_effect=Exception("Bad index"))
    com.ContainerType = True
    com.Id = "/app/con[0]/ses[0]/wnd[0]/usr/subscreen"

    field1 = MagicMock()
    field1.Id = "/app/con[0]/ses[0]/wnd[0]/usr/sub/txtBUT000-NAME_LAST"
    field1.Type = "GuiTextField"
    field1.TypeAsNumber = _TEXT_FIELD
    field1.Name = "BUT000-NAME_LAST"
    field1.Text = ""
    field1.Changeable = True

    label1 = MagicMock()
    label1.Id = "/app/con[0]/ses[0]/wnd[0]/usr/sub/lblBUT000-NAME_LAST"
    label1.Type = "GuiLabel"
    label1.TypeAsNumber = _LABEL
    label1.Name = "BUT000-NAME_LAST"
    label1.Text = "Nachname"
    label1.Changeable = False

    def find_all_by_name_ex(name, type_num):
        coll = MagicMock()
        if type_num == _TEXT_FIELD:
            coll.Count = 1
            coll.Item = lambda i: field1
        elif type_num == _LABEL:
            coll.Count = 1
            coll.Item = lambda i: label1
        else:
            coll.Count = 0
        return coll

    com.FindAllByNameEx = find_all_by_name_ex
    return com


class TestDumpTreeNormalContainer:
    def test_normal_children_traversed(self):
        """Normal container with children works as before."""
        child = MagicMock()
        child.Id = "wnd[0]/usr/txt1"
        child.Type = "GuiTextField"
        child.TypeAsNumber = _TEXT_FIELD
        child.Name = "txt1"
        child.Text = "hello"
        child.Changeable = True
        child.ContainerType = False
        child.Children.Count = 0

        com = _make_normal_container([child])
        result = _dump_tree_recursive(com, 0, 5)
        assert len(result) == 1
        assert result[0].name == "txt1"


class TestDumpTreeBDTFallback:
    def test_bdt_container_discovers_fields(self):
        """BDT container where Children.Count throws falls back to FindAllByNameEx."""
        com = _make_bdt_container()
        result = _dump_tree_recursive(com, 0, 5)
        assert len(result) >= 2
        names = {e.name for e in result}
        assert "BUT000-NAME_LAST" in names

    def test_bdt_fallback_skips_non_usr_containers(self):
        """BDT fallback only probes /usr/ containers."""
        com = MagicMock()
        type(com.Children).Count = PropertyMock(side_effect=Exception("Bad"))
        com.ContainerType = True
        com.Id = "/app/con[0]/ses[0]/wnd[0]/tbar[0]"
        com.FindAllByNameEx = MagicMock()

        result = _dump_tree_recursive(com, 0, 5)
        assert len(result) == 0
        com.FindAllByNameEx.assert_not_called()

    def test_bdt_fallback_on_count_zero(self):
        """BDT fallback also fires when Children.Count == 0 (not just exception)."""
        com = MagicMock()
        com.Children.Count = 0
        com.ContainerType = True
        com.Id = "/app/con[0]/ses[0]/wnd[0]/usr/empty"

        field = MagicMock()
        field.Id = "wnd[0]/usr/empty/txtF1"
        field.Type = "GuiTextField"
        field.TypeAsNumber = _TEXT_FIELD
        field.Name = "F1"
        field.Text = ""
        field.Changeable = True

        def find_all(name, type_num):
            coll = MagicMock()
            if type_num == _TEXT_FIELD:
                coll.Count = 1
                coll.Item = lambda i: field
            else:
                coll.Count = 0
            return coll

        com.FindAllByNameEx = find_all
        result = _dump_tree_recursive(com, 0, 5)
        assert len(result) == 1
        assert result[0].name == "F1"


class TestProbeBdtFields:
    def test_deduplication(self):
        """Same field found by multiple type queries appears only once."""
        field = MagicMock()
        field.Id = "wnd[0]/usr/txt1"
        field.Type = "GuiTextField"
        field.TypeAsNumber = _TEXT_FIELD
        field.Name = "txt1"
        field.Text = ""
        field.Changeable = True

        com = MagicMock()
        coll = MagicMock()
        coll.Count = 1
        coll.Item = lambda i: field
        com.FindAllByNameEx = MagicMock(return_value=coll)

        result = _probe_bdt_fields(com)
        assert len(result) == 1
