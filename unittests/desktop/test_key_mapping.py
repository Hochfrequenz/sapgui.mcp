# unittests/desktop/test_key_mapping.py
"""Tests for VKey name → number mapping."""

from sapguimcp.backend.desktop._key_mapping import key_to_vkey


def test_enter():
    assert key_to_vkey("Enter") == 0


def test_f_keys():
    for i in range(1, 13):
        assert key_to_vkey(f"F{i}") == i


def test_shift_f_keys():
    for i in range(1, 13):
        assert key_to_vkey(f"Shift+F{i}") == 12 + i


def test_ctrl_f_keys():
    for i in range(1, 13):
        assert key_to_vkey(f"Ctrl+F{i}") == 24 + i


def test_escape_maps_to_f12():
    assert key_to_vkey("Escape") == 12


def test_case_insensitive():
    assert key_to_vkey("enter") == 0
    assert key_to_vkey("ENTER") == 0
    assert key_to_vkey("f5") == 5


def test_unknown_key_raises():
    import pytest

    with pytest.raises(KeyError, match="Delete"):
        key_to_vkey("Delete")
