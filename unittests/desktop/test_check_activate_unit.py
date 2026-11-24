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
        return (self._session.popup or "popup") if self._is_popup else "SAP"

    def send_v_key(self, key: int) -> None:
        self._session.advance("popup" if self._is_popup else f"vkey{key}")


class ScriptedSession:
    """Fake GuiSession driven by (event, message, type, popup-title) steps.

    An empty popup title means no dialog is standing.
    """

    def __init__(self, steps: list[tuple[str, str, str, str]]) -> None:
        self._steps = list(steps)
        self.message = ""
        self.message_type = ""
        self.popup = ""
        self.events: list[str] = []

    def advance(self, event: str) -> None:
        self.events.append(event)
        for i, (step_event, message, message_type, popup) in enumerate(self._steps):
            if step_event == event:
                self._steps.pop(i)
                self.message, self.message_type, self.popup = message, message_type, popup
                return
        self.message, self.message_type, self.popup = "", "", ""

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


INACTIVE_OBJECTS = "Inaktive Objekte"

NO_SYNTAX_ERRORS = ("vkey26", "Es wurden keine Syntaxfehler in Report ZTEST gefunden", "S", "")


class TestCheckAndActivate:
    @pytest.mark.anyio
    async def test_confirmed_activation(self):
        session = ScriptedSession([NO_SYNTAX_ERRORS, ("vkey27", "Objekt(e) wurde(n) aktiviert", "S", "")])
        result = await make_backend(session).check_and_activate()
        assert result.success is True
        assert result.activated is True
        assert any("keine Syntaxfehler" in m for m in result.messages)
        assert any("aktiviert" in m for m in result.messages)

    @pytest.mark.anyio
    async def test_confirmed_activation_english(self):
        session = ScriptedSession(
            [("vkey26", "No syntax errors found", "S", ""), ("vkey27", "Object(s) activated", "S", "")]
        )
        result = await make_backend(session).check_and_activate()
        assert result.activated is True

    @pytest.mark.anyio
    async def test_saved_but_not_activated_is_not_reported_as_activated(self):
        """The #859 symptom: 'Program ... saved' claimed activated: true."""
        session = ScriptedSession([NO_SYNTAX_ERRORS, ("vkey27", "Programm ZTEST gesichert", "S", "")])
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
                ("vkey27", "Programm ZTEST gesichert", "S", INACTIVE_OBJECTS),
                ("popup", "Objekt(e) wurde(n) aktiviert", "S", ""),
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
                ("vkey27", "Programm ZTEST gesichert", "S", INACTIVE_OBJECTS),
                ("popup", "Die Schachtelung ist nicht korrekt", "E", ""),
            ]
        )
        result = await make_backend(session).check_and_activate()
        assert result.success is False
        assert result.activated is False
        assert "Schachtelung" in (result.error or "")

    @pytest.mark.anyio
    async def test_syntax_check_error_skips_activation(self):
        session = ScriptedSession([("vkey26", "Syntaxfehler in Zeile 42", "E", "")])
        backend = make_backend(session)
        result = await backend.check_and_activate()
        assert result.success is False
        assert result.activated is False
        assert "vkey27" not in session.events

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "message",
        [
            "Objekt wurde nicht aktiviert",
            "Object could not be activated",
            "Programm konnte nicht aktiviert werden",
            "Objekt ist inaktiv",
            "Objekt wurde deaktiviert",
        ],
    )
    async def test_negated_activation_messages_are_not_confirmations(self, message):
        """'aktiviert' is a substring of 'nicht aktiviert' — the positive token alone lies."""
        session = ScriptedSession([NO_SYNTAX_ERRORS, ("vkey27", message, "W", "")])
        result = await make_backend(session).check_and_activate()
        assert result.activated is False
        assert any("could not be confirmed" in m for m in result.messages)

    @pytest.mark.anyio
    async def test_unexpected_dialog_blocks_the_activation_claim(self):
        """A transport prompt is confirmed to unblock the session, but never claimed as success."""
        session = ScriptedSession(
            [
                NO_SYNTAX_ERRORS,
                ("vkey27", "Programm ZTEST gesichert", "S", "Transportauftrag zuordnen"),
                ("popup", "Objekt(e) wurde(n) aktiviert", "S", ""),
            ]
        )
        result = await make_backend(session).check_and_activate()
        assert result.activated is False
        assert any("Transportauftrag zuordnen" in m for m in result.messages)

    @pytest.mark.anyio
    async def test_error_behind_three_stacked_popups_is_not_missed(self):
        """The last Enter must still be followed by a read (#859 review finding)."""
        session = ScriptedSession(
            [
                NO_SYNTAX_ERRORS,
                ("vkey27", "Programm ZTEST gesichert", "S", INACTIVE_OBJECTS),
                ("popup", "Auftrag zuordnen", "S", INACTIVE_OBJECTS),
                ("popup", "Paket zuordnen", "S", INACTIVE_OBJECTS),
                ("popup", "Aktivierung abgebrochen", "E", ""),
            ]
        )
        result = await make_backend(session).check_and_activate()
        assert result.success is False
        assert result.activated is False
        assert "abgebrochen" in (result.error or "")

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


class _Window:
    def __init__(self, session: StackedSession, index: int, title: str) -> None:
        self._session = session
        self._index = index
        self.text = title

    def send_v_key(self, key: int) -> None:
        self._session.press(self._index, key)


class StackedSession:
    """Fake GuiSession with a real window stack: Ctrl+F3 opens the worklist, Enter opens an error dialog."""

    def __init__(self, activation_fails: bool) -> None:
        self._activation_fails = activation_fails
        self.windows: dict[int, str] = {}
        self.message = ""
        self.keys: list[tuple[int, int]] = []

    def press(self, index: int, key: int) -> None:
        self.keys.append((index, key))
        if index != max(self.windows, default=0):
            raise AssertionError(f"key {key} sent to covered window wnd[{index}]")
        if index == 0 and key == 27:
            self.windows[1] = INACTIVE_OBJECTS
        elif index == 1 and key == 0:
            if self._activation_fails:
                self.windows[2] = "Aktivierungsfehler"
            else:
                del self.windows[1]
                self.message = "Objekt(e) wurde(n) aktiviert"
        elif index > 0 and key == 12:
            del self.windows[index]

    def find_by_id(self, element_id: str, raise_error: bool = True) -> Any:
        del raise_error  # a missing window is always None here
        if element_id == "wnd[0]/sbar":
            return MagicMock(text=self.message, message_type="S" if self.message else "")
        index = int(element_id[4])
        if index == 0:
            return _Window(self, 0, "SAP")
        if index in self.windows:
            return _Window(self, index, self.windows[index])
        return None


class TestActivationErrorDialog:
    @pytest.mark.anyio
    async def test_error_dialog_on_the_worklist_fails_and_is_cancelled(self):
        """#1169: Enter on the error dialog would answer 'Activate' and activate the broken source."""
        session = StackedSession(activation_fails=True)
        result = await make_backend(session).check_and_activate()
        assert result.success is False
        assert result.activated is False
        assert "Aktivierungsfehler" in (result.error or "")
        assert (2, 12) in session.keys
        assert (1, 12) in session.keys
        assert (2, 0) not in session.keys
        assert session.windows == {}

    @pytest.mark.anyio
    async def test_worklist_confirmed_with_enter_still_activates(self):
        session = StackedSession(activation_fails=False)
        result = await make_backend(session).check_and_activate()
        assert result.success is True
        assert result.activated is True
        assert (1, 0) in session.keys
        assert (1, 12) not in session.keys
