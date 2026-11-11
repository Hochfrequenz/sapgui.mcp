"""``get_sap_config`` passes the server's own supported languages to sap-mcp-config."""

import json
from pathlib import Path
from typing import get_args

import pytest

from sapguimcp import lang
from sapguimcp.lang import supported_languages
from sapguimcp.models import config as config_module
from sapguimcp.utils import SapLanguage


def _system(**overrides: str) -> dict[str, str]:
    entry = {
        "connection_name": "DEV",
        "host": "https://sap-host-a.example.com",
        "client": "100",
        "user": "testuser",
        "password": "not-a-real-password",
    }
    entry.update(overrides)
    return entry


@pytest.fixture(name="config_file")
def _config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated config location: own SAP_CONFIG_FILE, cwd without a .env, fresh singleton."""
    path = tmp_path / "systems.json"
    monkeypatch.setenv("SAP_CONFIG_FILE", str(path))
    monkeypatch.chdir(tmp_path)  # sap-mcp-config runs load_dotenv(find_dotenv(usecwd=True))
    monkeypatch.setattr(config_module, "_sap_config", None)
    return path  # monkeypatch restores the singleton on teardown


def _write(path: Path, **overrides: str) -> None:
    path.write_text(
        json.dumps({"default_system": "dev", "systems": {"dev": _system(**overrides)}}),
        encoding="utf-8",
    )


def test_supported_languages_come_from_the_language_packs() -> None:
    assert supported_languages() == ("DE", "EN")
    assert not hasattr(config_module, "SUPPORTED_LANGUAGES")  # no second copy of the list


def test_sap_language_literal_matches_the_packs() -> None:
    """``utils.SapLanguage`` types date formatting until phase 3 retires it; it must not drift."""
    assert set(get_args(SapLanguage)) == set(supported_languages())


def test_config_accepts_every_registered_pack_language(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, ...]] = []

    def fake_load(*, supported_languages: tuple[str, ...]) -> object:
        seen.append(supported_languages)
        return object()

    monkeypatch.setattr(config_module, "_sap_config", None)
    monkeypatch.setattr(config_module, "load_sap_config", fake_load)
    # Only the registry is patched: the loader reads supported_languages(), which does not touch
    # the merged-view caches. Do not combine this with lang.current()/universal() (decision 13).
    monkeypatch.setitem(lang._PACKS, "XX", lang.pack_for("EN"))  # pylint: disable=protected-access
    config_module.get_sap_config()
    assert seen == [("DE", "EN", "XX")]


def test_unsupported_language_fails_loudly(config_file: Path) -> None:
    _write(config_file, language="IT")
    with pytest.raises(ValueError, match=r'language must be one of "DE", "EN"') as excinfo:
        config_module.get_sap_config()
    assert "not-a-real-password" not in str(excinfo.value)
    assert config_module._sap_config is None  # failure is not cached  # pylint: disable=protected-access


def test_lowercase_supported_language_accepted(config_file: Path) -> None:
    _write(config_file, language="de")
    assert config_module.get_sap_config().systems["dev"].language == "DE"


def test_omitted_language_defaults_to_en(config_file: Path) -> None:
    _write(config_file)
    assert config_module.get_sap_config().systems["dev"].language == "EN"
