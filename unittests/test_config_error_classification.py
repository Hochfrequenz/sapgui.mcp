"""Config load errors are classified in one helper and never crash the server."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sapguimcp import server
from sapguimcp.models import config as config_module
from sapguimcp.tools.sap_list_connections_impl import _get_configured_systems


@pytest.fixture(name="config_file")
def _config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated config location: own SAP_CONFIG_FILE, cwd without a .env, fresh singleton."""
    path = tmp_path / "systems.json"
    monkeypatch.setenv("SAP_CONFIG_FILE", str(path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "_sap_config", None)
    return path


def _write_it(path: Path) -> None:
    system = {
        "connection_name": "DEV",
        "host": "https://sap-host-a.example.com",
        "client": "100",
        "user": "testuser",
        "password": "not-a-real-password",
        "language": "IT",
    }
    path.write_text(json.dumps({"default_system": "dev", "systems": {"dev": system}}), encoding="utf-8")


def test_instructions_show_configuration_error_for_value_error() -> None:
    with patch.object(config_module, "get_sap_config", side_effect=ValueError("language must be one of DE, EN")):
        text = server._build_instructions()  # pylint: disable=protected-access
    assert "CONFIGURATION ERROR" in text
    assert "language must be one of DE, EN" in text
    assert "AVAILABLE SYSTEMS" not in text
    assert "restart" in text.lower()
    assert "sap_list_connections" in text


def test_it_language_message_is_clean(config_file: Path) -> None:
    _write_it(config_file)
    cfg, message = config_module.try_get_sap_config()
    assert cfg is None
    assert message is not None
    assert "language must be one of" in message
    assert "validation error for Config" not in message
    assert "input_value" not in message
    assert "not-a-real-password" not in message


def test_missing_file_is_silent(config_file: Path) -> None:
    assert not config_file.exists()
    assert config_module.try_get_sap_config() == (None, None)
    assert _get_configured_systems() == ([], None)
    assert "CONFIGURATION ERROR" not in server._build_instructions()  # pylint: disable=protected-access


def test_valid_config_returned(config_file: Path) -> None:
    _write_it(config_file)
    text = config_file.read_text(encoding="utf-8").replace('"IT"', '"DE"')
    config_file.write_text(text, encoding="utf-8")
    cfg, message = config_module.try_get_sap_config()
    assert message is None
    assert cfg is not None
    assert "dev" in cfg.systems


@pytest.fixture(name="broken_config", params=["malformed_yaml", "directory"])
def _broken_config(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "_sap_config", None)
    if request.param == "malformed_yaml":
        path = tmp_path / "systems.yaml"
        path.write_text("systems: [unclosed\n  - : :\n", encoding="utf-8")
    else:
        path = tmp_path / "adir"
        path.mkdir()
    monkeypatch.setenv("SAP_CONFIG_FILE", str(path))
    return path


def test_broken_config_does_not_crash_list_connections(broken_config: Path) -> None:
    assert broken_config.exists()
    systems, error = _get_configured_systems()
    assert systems == []
    assert error


def test_broken_config_does_not_crash_instructions(broken_config: Path) -> None:
    assert broken_config.exists()
    text = server._build_instructions()  # pylint: disable=protected-access
    assert "CONFIGURATION ERROR" in text
    assert "AVAILABLE SYSTEMS" not in text


_SECRET = "s3cr3t-sentinel"  # noqa: S105


def _write_malformed_yaml_with_secret(path: Path) -> Path:
    yaml_path = path.parent / "secret.yaml"
    yaml_path.write_text(f'systems:\n  dev:\n    password: {_SECRET}: "oops\n', encoding="utf-8")
    return yaml_path


def test_malformed_yaml_message_never_echoes_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "_sap_config", None)
    monkeypatch.setenv("SAP_CONFIG_FILE", str(_write_malformed_yaml_with_secret(tmp_path / "x")))
    _, message = config_module.try_get_sap_config()
    assert message
    assert _SECRET not in message
    assert "line 3" in message
    instructions = server._build_instructions()  # pylint: disable=protected-access
    assert _SECRET not in instructions
    assert "CONFIGURATION ERROR" in instructions
    systems, error = _get_configured_systems()
    assert systems == []
    assert error
    assert _SECRET not in error


def test_wrong_typed_host_names_the_location(config_file: Path) -> None:
    _write_it(config_file)
    data = json.loads(config_file.read_text(encoding="utf-8"))
    data["systems"]["dev"]["language"] = "DE"
    data["systems"]["dev"]["host"] = 123
    config_file.write_text(json.dumps(data), encoding="utf-8")
    _, message = config_module.try_get_sap_config()
    assert message
    assert "dev" in message
    assert "host" in message
    assert "not-a-real-password" not in message


def test_multiple_errors_joined_by_newline(config_file: Path) -> None:
    _write_it(config_file)
    data = json.loads(config_file.read_text(encoding="utf-8"))
    data["systems"]["dev"]["language"] = "DE"
    data["systems"]["dev"]["host"] = 123
    data["systems"]["dev"]["client"] = ["x"]
    config_file.write_text(json.dumps(data), encoding="utf-8")
    _, message = config_module.try_get_sap_config()
    assert message
    assert "\n" in message
    assert "; " not in message
