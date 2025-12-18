"""
Configuration models for SAP Web GUI MCP Server.

All settings are loaded from environment variables using pydantic-settings.
"""

from enum import StrEnum
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "BrowserMode",
    "BrowserType",
    "SapWebGuiSettings",
    "get_settings",
]


class BrowserMode(StrEnum):
    """
    Browser connection mode.

    LAUNCH: Start a new browser instance managed by the MCP server
    CONNECT: Connect to an existing browser via Chrome DevTools Protocol
    """

    LAUNCH = "launch"
    CONNECT = "connect"


class BrowserType(StrEnum):
    """
    Playwright browser type.

    CHROMIUM: Chrome/Chromium/Edge (recommended for SAP Web GUI)
    FIREFOX: Mozilla Firefox
    WEBKIT: Safari/WebKit
    """

    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class SapWebGuiSettings(BaseSettings):
    """
    Settings for SAP Web GUI MCP Server.

    All settings can be configured via environment variables.

    Example .env file:
        SAP_URL=https://your-sap-server/sap/bc/gui/sap/its/webgui
        BROWSER_MODE=launch
        BROWSER_TYPE=chromium
        BROWSER_HEADLESS=false

    For VPN/Citrix setups, use connect mode:
        BROWSER_MODE=connect
        CDP_URL=http://localhost:9222
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SAP Connection Settings
    sap_url: str = Field(
        default="",
        description="Default SAP Web GUI URL (can be overridden per call)",
        json_schema_extra={"env": "SAP_URL"},
    )

    # SAP Credentials (for automatic login)
    sap_user: str = Field(
        default="",
        description="SAP username for automatic login",
        json_schema_extra={"env": "SAP_USER"},
    )
    sap_password: str = Field(
        default="",
        description="SAP password for automatic login",
        json_schema_extra={"env": "SAP_PASSWORD"},
    )
    sap_mandant: str = Field(
        default="",
        description="SAP client/mandant (3-digit string, e.g., '100')",
        json_schema_extra={"env": "SAP_MANDANT"},
    )
    sap_language: str = Field(
        default="EN",
        description="SAP login language ('DE' or 'EN')",
        json_schema_extra={"env": "SAP_LANGUAGE"},
    )

    # Browser Configuration
    browser_mode: BrowserMode = Field(
        default=BrowserMode.LAUNCH,
        description="Browser mode: 'launch' (start new) or 'connect' (use existing)",
        json_schema_extra={"env": "BROWSER_MODE"},
    )
    browser_type: BrowserType = Field(
        default=BrowserType.CHROMIUM,
        description="Browser type: 'chromium', 'firefox', or 'webkit'",
        json_schema_extra={"env": "BROWSER_TYPE"},
    )
    browser_headless: bool = Field(
        default=False,
        description="Run browser in headless mode (not recommended for SAP)",
        json_schema_extra={"env": "BROWSER_HEADLESS"},
    )

    # CDP Connection (for connect mode)
    cdp_url: str = Field(
        default="http://localhost:9222",
        description="Chrome DevTools Protocol URL for connecting to existing browser",
        json_schema_extra={"env": "CDP_URL"},
    )

    def validate_for_browser(self) -> list[str]:
        """Validate settings required for browser connection."""
        errors: list[str] = []
        if self.browser_mode == BrowserMode.CONNECT and not self.cdp_url:
            errors.append("CDP_URL is required when BROWSER_MODE=connect")
        return errors


# Global settings instance (singleton)
_settings: Optional[SapWebGuiSettings] = None


def get_settings() -> SapWebGuiSettings:
    """
    Get the global settings instance.

    Settings are loaded once from environment variables and cached.
    """
    global _settings  # pylint: disable=global-statement
    if _settings is None:
        _settings = SapWebGuiSettings()
    return _settings
