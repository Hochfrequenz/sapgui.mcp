"""Tests for sapgui error class hierarchy."""

import pytest

from sapsucker._errors import (
    ElementNotFoundError,
    SapConnectionError,
    SapGuiError,
    SapGuiTimeoutError,
    ScriptingDisabledError,
)


class TestSapGuiError:
    def test_is_exception(self):
        assert issubclass(SapGuiError, Exception)

    def test_str_content(self):
        err = SapGuiError("something broke")
        assert "something broke" in str(err)


class TestSapConnectionError:
    def test_inherits_sap_gui_error(self):
        assert issubclass(SapConnectionError, SapGuiError)

    def test_str_content(self):
        err = SapConnectionError("connection lost")
        assert "connection lost" in str(err)


class TestScriptingDisabledError:
    def test_inherits_sap_gui_error(self):
        assert issubclass(ScriptingDisabledError, SapGuiError)

    def test_str_content(self):
        err = ScriptingDisabledError("scripting is off")
        assert "scripting is off" in str(err)


class TestElementNotFoundError:
    def test_inherits_sap_gui_error(self):
        assert issubclass(ElementNotFoundError, SapGuiError)

    def test_str_content(self):
        err = ElementNotFoundError("no such element")
        assert "no such element" in str(err)


class TestSapGuiTimeoutError:
    def test_inherits_sap_gui_error(self):
        assert issubclass(SapGuiTimeoutError, SapGuiError)

    def test_str_content(self):
        err = SapGuiTimeoutError("timed out")
        assert "timed out" in str(err)
