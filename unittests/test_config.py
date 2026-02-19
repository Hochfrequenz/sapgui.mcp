"""Tests for the configuration module."""

import os
from unittest.mock import patch

import pytest

from sapwebguimcp.models.config import (
    BrowserMode,
    BrowserType,
    SapWebGuiSettings,
    get_settings,
)


class TestSapWebGuiSettings:
    """Tests for SapWebGuiSettings."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        # pydantic-settings reads from .env file directly, so we need to both
        # clear os.environ AND tell SapWebGuiSettings not to read .env
        with patch.dict(os.environ, {}, clear=True):
            settings = SapWebGuiSettings(_env_file=None)

        assert settings.sap_url == ""
        assert settings.browser_mode == BrowserMode.CONNECT
        assert settings.browser_type == BrowserType.CHROMIUM
        assert settings.browser_headless is False
        assert settings.cdp_url == "http://localhost:9222"

    def test_env_variable_loading(self) -> None:
        """Test that environment variables are loaded correctly."""
        env_vars = {
            "SAP_URL": "https://sap.example.com/webgui",
            "BROWSER_MODE": "connect",
            "BROWSER_TYPE": "firefox",
            "BROWSER_HEADLESS": "true",
            "CDP_URL": "http://localhost:9333",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = SapWebGuiSettings(_env_file=None)

        assert settings.sap_url == "https://sap.example.com/webgui"
        assert settings.browser_mode == BrowserMode.CONNECT
        assert settings.browser_type == BrowserType.FIREFOX
        assert settings.browser_headless is True
        assert settings.cdp_url == "http://localhost:9333"

    def test_validate_for_browser_connect_mode_missing_cdp(self) -> None:
        """Test validation when in connect mode without CDP URL."""
        env_vars = {
            "BROWSER_MODE": "connect",
            "CDP_URL": "",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = SapWebGuiSettings(_env_file=None)

        errors = settings.validate_for_browser()
        assert len(errors) == 1
        assert "CDP_URL is required" in errors[0]

    def test_validate_for_browser_launch_mode(self) -> None:
        """Test validation passes in launch mode."""
        with patch.dict(os.environ, {"BROWSER_MODE": "launch"}, clear=True):
            settings = SapWebGuiSettings(_env_file=None)

        errors = settings.validate_for_browser()
        assert len(errors) == 0


class TestGetSettings:
    """Tests for the get_settings function."""

    def test_returns_settings_instance(self) -> None:
        """Test that get_settings returns a SapWebGuiSettings instance."""
        # Reset the global settings
        import sapwebguimcp.models.config

        sapwebguimcp.models.config._settings = None

        settings = get_settings()
        assert isinstance(settings, SapWebGuiSettings)

    def test_returns_same_instance(self) -> None:
        """Test that get_settings returns the same instance on subsequent calls."""
        # Reset the global settings
        import sapwebguimcp.models.config

        sapwebguimcp.models.config._settings = None

        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2
