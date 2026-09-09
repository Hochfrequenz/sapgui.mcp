"""Unit tests for DesktopBackend.check_and_activate reporting (issue #859).

The reporter of #859 got ``activated: true`` from a status bar that only said
"Program ... saved" — the message shown *before* the activation outcome.  These
tests pin the reporting rules: activation is only claimed when the final
message confirms it, and the status bar is re-read after every popup.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from sapguimcp.backend.desktop import DesktopBackend


class _Sbar:
    def __init__(self, session: ScriptedSession) -> None:
        self._session = session

    @property
    def text(self) -> str:
        return self._session.message

    @property
    def message_type(self) -> str:
        return self._session.message_type


class _Wnd:
    def __init__(self, session: ScriptedSession, is_popup: bool) -> None:
        self._session = session
        self._is_popup = is_popup

    @property
    def text(self) -> str:
        return "popup" if self._is_popup else "SAP"

    def send_v_key(self, key: int) -> None:
        self._session.advance("popup" if self._is_popup else f"vkey{key}")


class ScriptedSession:
    """Fake GuiSession driven by a list of (event, message, type, popup) steps."""

    def __init__(self, steps: list[tuple[str, str, str, bool]]) -> None:
        self._steps = list(steps)
        self.message = ""
        self.message_type = ""
        self.popup = False
        self.events: list[str] = []

    def advance(self, event: str) -> None:
        self.events.append(event)
        for i, (step_event, message, message_type, popup) in enumerate(self._steps):
            if step_event == event:
                self._steps.pop(i)
                self.message, self.message_type, self.popup = message, message_type, popup
                return
        self.message, self.message_type, self.popup = "", "", False

    def find_by_id(self, element_id: str, raise_error: bool = True) -> Any:
        if element_id == "wnd[0]":
            return _Wnd(self, is_popup=False)
        if element_id == "wnd[0]/sbar":
            return _Sbar(self)
        if element_id == "wnd[1]":
            return _Wnd(self, is_popup=True) if self.popup else None
        if raise_error:
            raise AssertionError(f"unexpected element: {element_id}")
        return None


def make_backend(session: ScriptedSession) -> DesktopBackend:
    backend = DesktopBackend.__new__(DesktopBackend)

    async def run(fn):  # type: ignore[no-untyped-def]
        return fn()

    backend.com = MagicMock()
    backend.com.run = run
    backend.require_session = lambda: session  # type: ignore[assignment,method-assign,return-value]
    return backend


NO_SYNTAX_ERRORS = ("vkey26", "Es wurden keine Syntaxfehler in Report ZTEST gefunden", "S", False)


class TestCheckAndActivate:
    @pytest.mark.anyio
    async def test_confirmed_activation(self):
        session = ScriptedSession([NO_SYNTAX_ERRORS, ("vkey27", "Objekt(e) wurde(n) aktiviert", "S", False)])
        result = await make_backend(session).check_and_activate()
        assert result.success is True
        assert result.activated is True
        assert any("keine Syntaxfehler" in m for m in result.messages)
        assert any("aktiviert" in m for m in result.messages)

    @pytest.mark.anyio
    async def test_confirmed_activation_english(self):
        session = ScriptedSession(
            [("vkey26", "No syntax errors found", "S", False), ("vkey27", "Object(s) activated", "S", False)]
        )
        result = await make_backend(session).check_and_activate()
        assert result.activated is True

    @pytest.mark.anyio
    async def test_saved_but_not_activated_is_not_reported_as_activated(self):
        """The #859 symptom: 'Program ... saved' claimed activated: true."""
        session = ScriptedSession([NO_SYNTAX_ERRORS, ("vkey27", "Programm ZTEST gesichert", "S", False)])
        result = await make_backend(session).check_and_activate()
        assert result.activated is False
        assert result.success is True  # no error evidence — must not trigger an auto-revert
        assert any("could not be confirmed" in m for m in result.messages)

    @pytest.mark.anyio
    async def test_status_bar_is_reread_after_the_popup(self):
        """The activation outcome only appears once the popup is answered."""
        session = ScriptedSession(
            [
                NO_SYNTAX_ERRORS,
                ("vkey27", "Programm ZTEST gesichert", "S", True),
                ("popup", "Objekt(e) wurde(n) aktiviert", "S", False),
            ]
        )
        result = await make_backend(session).check_and_activate()
        assert result.activated is True
        assert any("gesichert" in m for m in result.messages)
        assert any("aktiviert" in m for m in result.messages)

    @pytest.mark.anyio
    async def test_activation_error_after_popup_fails(self):
        session = ScriptedSession(
            [
                NO_SYNTAX_ERRORS,
                ("vkey27", "Programm ZTEST gesichert", "S", True),
                ("popup", "Die Schachtelung ist nicht korrekt", "E", False),
            ]
        )
        result = await make_backend(session).check_and_activate()
        assert result.success is False
        assert result.activated is False
        assert "Schachtelung" in (result.error or "")

    @pytest.mark.anyio
    async def test_syntax_check_error_skips_activation(self):
        session = ScriptedSession([("vkey26", "Syntaxfehler in Zeile 42", "E", False)])
        backend = make_backend(session)
        result = await backend.check_and_activate()
        assert result.success is False
        assert result.activated is False
        assert "vkey27" not in session.events

    @pytest.mark.anyio
    async def test_com_failure_is_reported(self):
        backend = DesktopBackend.__new__(DesktopBackend)

        async def run(_fn):  # type: ignore[no-untyped-def]
            raise RuntimeError("COM is busy")

        backend.com = MagicMock()
        backend.com.run = run
        backend.require_session = lambda: ScriptedSession([])  # type: ignore[assignment,method-assign,return-value]
        result = await backend.check_and_activate()
        assert result.success is False
        assert result.activated is False
        assert "COM is busy" in (result.error or "")
