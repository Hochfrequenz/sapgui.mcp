"""Tests for the notice and warning shown to users who still carry legacy WebGUI settings (decision D4)."""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from sapguimcp import server
from sapguimcp.backend import manager as manager_module

_WEBGUI_VARS = ("BACKEND_TYPE", "SAP_URL", "CDP_URL")


@pytest.fixture(autouse=True)
def _no_legacy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _WEBGUI_VARS:
        monkeypatch.delenv(name, raising=False)
    # A developer's own .env must not leak into these tests.
    monkeypatch.setattr(server, "_env_files", lambda: ())


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("SAP_URL=https://sap.example/webgui", ["SAP_URL"]),
        ("BACKEND_TYPE=webgui", ["BACKEND_TYPE=webgui"]),
        ("sap_url=https://sap.example/webgui", ["SAP_URL"]),
        ("backend_type=webgui", ["BACKEND_TYPE=webgui"]),
    ],
)
def test_legacy_settings_in_dotenv_file_are_detected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, line: str, expected: list[str]
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{line}\n", encoding="utf-8")
    monkeypatch.setattr(server, "_env_files", lambda: (str(env_file),))
    assert server._legacy_webgui_settings() == expected


def test_missing_dotenv_file_is_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(server, "_env_files", lambda: (str(tmp_path / "missing.env"),))
    assert server._legacy_webgui_settings() == []


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


def test_require_windows_raises_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager_module.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="requires Windows"):
        manager_module._require_windows()
