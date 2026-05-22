"""Unit tests for SapGuiSettings.credentials_for using shared sap-mcp-config."""

from unittest.mock import patch

import pytest
from pydantic import SecretStr
from sap_mcp_config import Config, SAPSystem

from sapguimcp.models.config import SapGuiSettings, get_sap_config


def _make_config(**systems: dict) -> Config:
    """Build a Config with the given systems (first key becomes default)."""
    sys_map = {}
    for name, vals in systems.items():
        sys_map[name] = SAPSystem(
            host=vals.get("host", "https://example.com"),
            client=vals.get("client", "100"),
            user=vals.get("user", ""),
            password=SecretStr(vals.get("password", "")),
            language=vals.get("language", "EN"),
        )
    default = next(iter(systems))
    return Config(default_system=default, systems=sys_map)


def _make_settings() -> SapGuiSettings:
    with patch.dict("os.environ", {}, clear=False):
        return SapGuiSettings(_env_file=None)


class TestCredentialsFor:
    """credentials_for resolves per-system credentials via shared config."""

    def test_raises_key_error_when_not_found(self) -> None:
        cfg = _make_config(DEV={"user": "dev_user", "password": "dev_pass"})
        with patch("sapguimcp.models.config._sap_config", cfg):
            settings = _make_settings()
            with pytest.raises(KeyError, match="UNKNOWN"):
                settings.credentials_for("UNKNOWN")

    def test_returns_system_credentials_when_mapped(self) -> None:
        cfg = _make_config(
            DEV={"user": "dev_user", "password": "dev_pass"},
            HFQ={"user": "hfq_user", "password": "hfq_pass"},
        )
        with patch("sapguimcp.models.config._sap_config", cfg):
            settings = _make_settings()
            user, password = settings.credentials_for("HFQ")
        assert user == "hfq_user"
        assert password == "hfq_pass"

    def test_raises_key_error_for_unmapped_system(self) -> None:
        cfg = _make_config(
            DEV={"user": "dev_user", "password": "dev_pass"},
            HFQ={"user": "hfq_user", "password": "hfq_pass"},
        )
        with patch("sapguimcp.models.config._sap_config", cfg):
            settings = _make_settings()
            with pytest.raises(KeyError, match="S4U"):
                settings.credentials_for("S4U")


class TestGetSapConfig:
    """get_sap_config loads and caches the shared SAP config."""

    def test_singleton_caching(self, tmp_path: pytest.TempPathFactory) -> None:
        """get_sap_config returns the same instance on subsequent calls."""
        import sapguimcp.models.config as mod

        cfg = _make_config(DEV={"user": "u", "password": "p"})
        old = mod._sap_config
        try:
            mod._sap_config = cfg
            assert get_sap_config() is cfg
        finally:
            mod._sap_config = old
