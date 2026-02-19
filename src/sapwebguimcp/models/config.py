"""
Configuration models for SAP Web GUI MCP Server.

All settings are loaded from environment variables using pydantic-settings.
"""

from enum import StrEnum
from typing import Literal, Optional

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

    CONNECT (default): Connect to an existing Chrome browser via Chrome DevTools Protocol.
        Requires Chrome running with --remote-debugging-port=9222.
        This is the default because:
        - Chrome with CDP is a prerequisite for SAP Web GUI automation anyway.
        - It avoids bundling Playwright's Chromium binaries (~400MB), which is
          essential for PyInstaller exe distribution.
        - The user sees the browser, helpful for CAPTCHAs and manual intervention.

    LAUNCH: Start a new browser instance managed by Playwright.
        Requires Playwright browser binaries installed via `playwright install`.
        Useful for development/testing but not recommended for production or exe builds.
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
        CDP_URL=http://localhost:9222

    The default browser mode is 'connect', which expects Chrome running with
    --remote-debugging-port=9222. For development with Playwright-managed browsers:
        BROWSER_MODE=launch
        BROWSER_HEADLESS=false
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
        pattern=r"^(\d{3})?$",  # Allow empty string or exactly 3 digits
        json_schema_extra={"env": "SAP_MANDANT"},
    )
    sap_language: Literal["DE", "EN"] = Field(
        default="EN",
        description="SAP login language ('DE' or 'EN')",
        json_schema_extra={"env": "SAP_LANGUAGE"},
    )

    # Browser Configuration
    browser_mode: BrowserMode = Field(
        default=BrowserMode.CONNECT,
        description=(
            "Browser mode: 'connect' (default, use existing Chrome with CDP) "
            "or 'launch' (start new via Playwright)"
        ),
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

    # Audit Logging
    audit_log_dir: str = Field(
        default="",
        description="Directory for intent audit logs (JSONL files). "
        "Leave empty to disable file-based audit logging.",
        json_schema_extra={"env": "AUDIT_LOG_DIR"},
    )

    # GitHub Settings (optional)
    github_pat: str = Field(
        default="",
        description="GitHub Personal Access Token for creating issues from feedback "
        "and authenticating abapGit pulls. Leave empty to disable.",
        json_schema_extra={"env": "GITHUB_PAT"},
    )
    github_user: str = Field(
        default="",
        description="GitHub username for abapGit authentication. "
        "Falls back to 'x-access-token' if not set (works with PAT auth).",
        json_schema_extra={"env": "GITHUB_USER"},
    )
    github_repo: str = Field(
        default="Hochfrequenz/sapwebgui.mcp",
        description="GitHub repository for feedback issues (format: owner/repo)",
        json_schema_extra={"env": "GITHUB_REPO"},
    )

    # Papertrail Logging (optional)
    papertrail_host: str = Field(
        default="logs5.papertrailapp.com",
        description="Papertrail syslog destination host. Leave empty to disable.",
        json_schema_extra={"env": "PAPERTRAIL_HOST"},
    )
    papertrail_port: int = Field(
        default=35329,
        description="Papertrail syslog destination port.",
        json_schema_extra={"env": "PAPERTRAIL_PORT"},
    )

    # abapGit Integration
    # For abapGit authentication, ABAPGIT_PAT takes priority over GITHUB_PAT.
    # Use ABAPGIT_PAT if you need separate tokens for abapGit vs feedback/issues.
    # The github_user field is used for authentication; defaults to 'x-access-token'.
    abapgit_pat: str | None = Field(
        default=None,
        description="GitHub Personal Access Token for abapGit pull/push operations. "
        "Required for private repositories or to avoid rate limits.",
        json_schema_extra={"env": "ABAPGIT_PAT"},
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
