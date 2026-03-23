"""Unit tests for SapWebGuiSettings.credentials_for and SapSystemCredentials."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from sapwebguimcp.models.config import SapSystemCredentials, SapWebGuiSettings


def _make_settings(**overrides) -> SapWebGuiSettings:
    defaults = {
        "sap_user": "default_user",
        "sap_password": "default_pass",
    }
    defaults.update(overrides)
    with patch.dict("os.environ", {}, clear=False):
        return SapWebGuiSettings(**defaults)


class TestSapSystemCredentials:
    """SapSystemCredentials validates per-system credential entries."""

    def test_valid_credentials(self) -> None:
        creds = SapSystemCredentials(user="u", password="p")
        assert creds.user == "u"
        assert creds.password == "p"

    def test_missing_user_raises(self) -> None:
        with pytest.raises(ValidationError):
            SapSystemCredentials(password="p")  # type: ignore[call-arg]

    def test_missing_password_raises(self) -> None:
        with pytest.raises(ValidationError):
            SapSystemCredentials(user="u")  # type: ignore[call-arg]


class TestCredentialsFor:
    """credentials_for resolves per-system credentials with fallback."""

    def test_falls_back_to_global_when_no_mapping(self) -> None:
        settings = _make_settings()
        user, password = settings.credentials_for("HFQ")
        assert user == "default_user"
        assert password == "default_pass"

    def test_returns_system_credentials_when_mapped(self) -> None:
        settings = _make_settings(sap_credentials='{"HFQ": {"user": "hfq_user", "password": "hfq_pass"}}')
        user, password = settings.credentials_for("HFQ")
        assert user == "hfq_user"
        assert password == "hfq_pass"

    def test_falls_back_for_unmapped_system(self) -> None:
        settings = _make_settings(sap_credentials='{"HFQ": {"user": "hfq_user", "password": "hfq_pass"}}')
        user, password = settings.credentials_for("S4U")
        assert user == "default_user"
        assert password == "default_pass"

    def test_incomplete_entry_raises(self) -> None:
        """Each system must have both user and password."""
        settings = _make_settings(sap_credentials='{"HFQ": {"user": "hfq_user"}}')
        with pytest.raises(ValidationError):
            settings.credentials_for("HFQ")

    def test_invalid_json_raises(self) -> None:
        """Malformed JSON raises at parse time."""
        settings = _make_settings(sap_credentials="not valid json")
        with pytest.raises(Exception):
            settings.credentials_for("HFQ")

    def test_empty_string_falls_back(self) -> None:
        settings = _make_settings(sap_credentials="")
        user, password = settings.credentials_for("HFQ")
        assert user == "default_user"
        assert password == "default_pass"

    def test_empty_mapping_falls_back(self) -> None:
        settings = _make_settings(sap_credentials="{}")
        user, password = settings.credentials_for("HFQ")
        assert user == "default_user"
        assert password == "default_pass"
