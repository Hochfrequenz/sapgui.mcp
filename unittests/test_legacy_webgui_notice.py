"""Tests for the notice and warning shown to users who still carry legacy WebGUI settings (decision D4)."""

import logging
from unittest.mock import patch

import pytest

from sapguimcp import server

_WEBGUI_VARS = ("BACKEND_TYPE", "SAP_URL", "CDP_URL")


@pytest.fixture(autouse=True)
def _no_legacy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _WEBGUI_VARS:
        monkeypatch.delenv(name, raising=False)


def test_no_warning_without_legacy_settings(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=server.logger.name):
        assert server._warn_legacy_webgui_settings() == []
    assert not caplog.records
    with patch.object(server, "try_get_sap_config", return_value=(None, None)):
        assert "sapwebgui.mcp" not in server._build_instructions()


def test_backend_type_desktop_is_not_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_TYPE", "desktop")
    assert server._legacy_webgui_settings() == []


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("BACKEND_TYPE", "webgui", "BACKEND_TYPE=webgui"),
        ("BACKEND_TYPE", "WebGUI", "BACKEND_TYPE=webgui"),
        ("SAP_URL", "https://sap.example/webgui", "SAP_URL"),
        ("CDP_URL", "http://localhost:9222", "CDP_URL"),
    ],
)
def test_legacy_setting_logs_warning_and_adds_notice(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, name: str, value: str, expected: str
) -> None:
    monkeypatch.setenv(name, value)
    with (
        caplog.at_level(logging.WARNING, logger=server.logger.name),
        patch.object(server, "try_get_sap_config", return_value=(None, None)),
    ):
        instructions = server._build_instructions()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert expected in warnings[0].getMessage()
    assert "https://github.com/Hochfrequenz/sapwebgui.mcp" in warnings[0].getMessage()
    assert "sapwebgui.mcp" in instructions
    assert "https://github.com/Hochfrequenz/sapwebgui.mcp" in instructions
    assert "WebGUI" in instructions


def test_all_legacy_settings_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_TYPE", "webgui")
    monkeypatch.setenv("SAP_URL", "https://sap.example")
    monkeypatch.setenv("CDP_URL", "http://localhost:9222")
    assert server._legacy_webgui_settings() == ["BACKEND_TYPE=webgui", "SAP_URL", "CDP_URL"]
