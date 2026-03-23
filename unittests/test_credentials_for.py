"""Unit tests for SapWebGuiSettings.credentials_for."""

from unittest.mock import patch

from sapwebguimcp.models.config import SapWebGuiSettings


def _make_settings(**overrides: str) -> SapWebGuiSettings:
    defaults = {
        "sap_user": "default_user",
        "sap_password": "default_pass",
        "sap_credentials": "",
    }
    defaults.update(overrides)
    with patch.dict("os.environ", {}, clear=False):
        return SapWebGuiSettings(**defaults)


class TestCredentialsFor:
    """credentials_for resolves per-system credentials with fallback."""

    def test_falls_back_to_global_when_no_mapping(self) -> None:
        settings = _make_settings()
        user, password = settings.credentials_for("HFQ")
        assert user == "default_user"
        assert password == "default_pass"

    def test_returns_system_credentials_when_mapped(self) -> None:
        settings = _make_settings(
            sap_credentials='{"HFQ": {"user": "hfq_user", "password": "hfq_pass"}}'
        )
        user, password = settings.credentials_for("HFQ")
        assert user == "hfq_user"
        assert password == "hfq_pass"

    def test_falls_back_for_unmapped_system(self) -> None:
        settings = _make_settings(
            sap_credentials='{"HFQ": {"user": "hfq_user", "password": "hfq_pass"}}'
        )
        user, password = settings.credentials_for("S4U")
        assert user == "default_user"
        assert password == "default_pass"

    def test_partial_mapping_falls_back_per_field(self) -> None:
        """If only user is mapped, password falls back to global."""
        settings = _make_settings(
            sap_credentials='{"HFQ": {"user": "hfq_user"}}'
        )
        user, password = settings.credentials_for("HFQ")
        assert user == "hfq_user"
        assert password == "default_pass"

    def test_invalid_json_falls_back(self) -> None:
        settings = _make_settings(sap_credentials="not valid json")
        user, password = settings.credentials_for("HFQ")
        assert user == "default_user"
        assert password == "default_pass"

    def test_empty_mapping_falls_back(self) -> None:
        settings = _make_settings(sap_credentials="{}")
        user, password = settings.credentials_for("HFQ")
        assert user == "default_user"
        assert password == "default_pass"
