"""
Configuration models for SAP Web GUI MCP Server.

Server-specific settings are loaded from environment variables using pydantic-settings.
SAP system credentials are loaded from the shared ``sap-mcp-config`` JSON file
(``~/.config/sap-mcp/systems.json`` by default, or via ``SAP_CONFIG_FILE`` env var).
"""

import sys
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sap_mcp_config import Config as SapMcpConfig
from sap_mcp_config import load_default as load_sap_config

__all__ = [
    "BackendType",
    "BrowserMode",
    "BrowserType",
    "SapGuiSettings",
    "get_sap_config",
    "get_settings",
]

# ---------------------------------------------------------------------------
# Shared SAP system config (singleton)
# ---------------------------------------------------------------------------

_sap_config: SapMcpConfig | None = None


def get_sap_config() -> SapMcpConfig:
    """Load the shared SAP system config (singleton)."""
    global _sap_config  # pylint: disable=global-statement
    if _sap_config is None:
        _sap_config = load_sap_config()
    return _sap_config


# Backend type: "webgui" for Playwright browser automation,
# "desktop" for SAP GUI Scripting (COM) via sapsucker.
BackendType = Literal["webgui", "desktop"]


def _env_files() -> tuple[str, ...]:
    """Return env file paths, accounting for PyInstaller bundles.

    In a frozen .exe, PyInstaller extracts bundled data files to a temp
    directory (``sys._MEIPASS``).  We look for ``.env.production`` there
    first, then always include the user's ``.env`` (resolved from cwd).

    Priority (later files override earlier):
      1. ``.env.production`` from ``_MEIPASS`` (if present)
      2. ``.env`` from the current working directory
    """
    base = Path(getattr(sys, "_MEIPASS", "."))
    production = base / ".env.production"
    files: list[str] = []
    if production.is_file():
        files.append(str(production))
    files.append(".env")
    return tuple(files)


# TODO(split): BrowserMode and BrowserType are webgui-only — move to webgui
# project's own config when splitting.


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


class SapGuiSettings(BaseSettings):
    """
    Settings for SAP Web GUI MCP Server.

    Server-specific settings (browser config, logging, GitHub integration) are
    loaded from environment variables.  SAP system credentials and connection
    details are loaded from the shared ``sap-mcp-config`` JSON file --
    see :func:`get_sap_config`.

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
        env_file=_env_files(),  # called at import time
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Shared fields (used by both backends) ---

    backend_type: BackendType = Field(
        default="webgui",
        description="Backend type: 'webgui' (browser) or 'desktop' (SAP GUI COM)",
        json_schema_extra={"env": "BACKEND_TYPE"},
    )

    sap_url: str = Field(
        default="",
        description="Default SAP Web GUI URL (can be overridden per call)",
        json_schema_extra={"env": "SAP_URL"},
    )

    # --- Desktop-only fields ---
    # TODO(split): move to desktop project's own Settings class

    com_min_interval_ms: int = Field(
        default=100,
        ge=0,
        le=5000,
        description=(
            "Minimum milliseconds between COM calls (desktop only). "
            "Prevents COM overload with parallel agents. 0 to disable."
        ),
        json_schema_extra={"env": "COM_MIN_INTERVAL_MS"},
    )

    # --- WebGUI-only fields ---
    # TODO(split): move to webgui project's own Settings class

    browser_mode: BrowserMode = Field(
        default=BrowserMode.CONNECT,
        description=(
            "Browser mode: 'connect' (default, use existing Chrome with CDP) " "or 'launch' (start new via Playwright)"
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
    cdp_url: str = Field(
        default="http://localhost:9222",
        description="Chrome DevTools Protocol URL for connecting to existing browser",
        json_schema_extra={"env": "CDP_URL"},
    )
    chrome_path: str = Field(
        default="",
        description="Explicit path to chrome.exe. If empty, Chrome is auto-detected via registry/known paths.",
        json_schema_extra={"env": "CHROME_PATH"},
    )
    chrome_user_data_dir: str = Field(
        default=str(Path(tempfile.gettempdir()) / "chrome-debug"),
        description="User data directory for auto-launched Chrome (separate from default profile).",
        json_schema_extra={"env": "CHROME_USER_DATA_DIR"},
    )

    # --- Shared infrastructure fields ---

    # GitHub Settings (optional)
    github_pat: str = Field(
        default="",
        description="GitHub Personal Access Token. Used for two purposes: "
        "(1) creating GitHub issues from log_feedback, "
        "(2) authenticating abapGit pulls (unless ABAPGIT_PAT is set). "
        "Leave empty to disable both.",
        json_schema_extra={"env": "GITHUB_PAT"},
    )
    github_user: str = Field(
        default="",
        description="GitHub username for abapGit authentication. "
        "Falls back to 'x-access-token' if not set (works with PAT auth).",
        json_schema_extra={"env": "GITHUB_USER"},
    )
    github_repo: str = Field(
        default="Hochfrequenz/sapgui.mcp",
        description="GitHub repository for feedback issues (format: owner/repo)",
        json_schema_extra={"env": "GITHUB_REPO"},
    )

    # Logging
    log_format: Literal["", "json"] = Field(
        default="",
        description="Set to 'json' for JSON log output. Default is human-readable console.",
        json_schema_extra={"env": "LOG_FORMAT"},
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Log level: DEBUG, INFO, WARNING, or ERROR.",
        json_schema_extra={"env": "LOG_LEVEL"},
    )

    # Papertrail Logging (optional)
    # Defaults are empty — Papertrail is OFF everywhere (source, pip install, and .exe).
    # Set PAPERTRAIL_HOST + PAPERTRAIL_PORT in your .env (or environment) to enable.
    papertrail_host: str = Field(
        default="",
        description="Papertrail syslog destination host. Leave empty to disable.",
        json_schema_extra={"env": "PAPERTRAIL_HOST"},
    )
    papertrail_port: int = Field(
        default=0,
        description="Papertrail syslog destination port.",
        json_schema_extra={"env": "PAPERTRAIL_PORT"},
    )

    # abapGit Integration
    # ABAPGIT_PAT is optional and overrides GITHUB_PAT for abapGit operations only.
    # Use it when you need a separate token scoped to your ABAP repos,
    # while GITHUB_PAT remains scoped to feedback/issue creation.
    abapgit_pat: str | None = Field(
        default=None,
        description="Optional: separate PAT for abapGit pulls, overrides GITHUB_PAT. "
        "Use this if you want a different token for abapGit than for feedback/issues. "
        "If not set, GITHUB_PAT is used for both.",
        json_schema_extra={"env": "ABAPGIT_PAT"},
    )

    def credentials_for(self, system_key: str) -> tuple[str, str]:
        """Return (user, password) for a system key.

        Looks up ``system_key`` in the shared SAP config
        (``~/.config/sap-mcp/systems.json``).  Raises ``KeyError`` when the
        key is not found.
        """
        sap_cfg = get_sap_config()
        system = sap_cfg.systems.get(system_key)
        if system is None:
            available = list(sap_cfg.systems.keys())
            raise KeyError(f"System key {system_key!r} not found in systems.json. " f"Available: {available}")
        return system.user, system.password.get_secret_value()

    def validate_for_browser(self) -> list[str]:
        """Validate settings required for browser connection."""
        errors: list[str] = []
        if self.browser_mode == BrowserMode.CONNECT and not self.cdp_url:
            errors.append("CDP_URL is required when BROWSER_MODE=connect")
        return errors


# Global settings instance (singleton)
_settings: Optional[SapGuiSettings] = None


def get_settings() -> SapGuiSettings:
    """
    Get the global settings instance.

    Settings are loaded once from environment variables and cached.
    """
    global _settings  # pylint: disable=global-statement
    if _settings is None:
        _settings = SapGuiSettings()
    return _settings
