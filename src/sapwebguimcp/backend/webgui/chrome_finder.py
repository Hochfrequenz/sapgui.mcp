"""
Auto-detect and launch Chrome with CDP debugging flags on Windows.

Used by BrowserManager in connect mode: when no Chrome instance is reachable
on the CDP port, this module finds chrome.exe, launches it with the required
flags, and waits until the CDP endpoint is ready.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

__all__ = [
    "extract_port_from_cdp_url",
    "find_chrome",
    "launch_chrome",
    "wait_for_cdp",
]

logger = logging.getLogger(__name__)

# Well-known Chrome installation paths on Windows
_KNOWN_CHROME_PATHS: list[str] = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


if sys.platform == "win32":
    import winreg  # pylint: disable=import-error

    def _chrome_from_registry() -> Optional[str]:
        """Look up chrome.exe in the Windows registry (App Paths)."""
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                    path, _ = winreg.QueryValueEx(key, "")
                    if path and Path(path).is_file():
                        logger.info("Chrome found via registry: %s", path)
                        return str(path)
            except OSError:
                continue
        return None

else:

    def _chrome_from_registry() -> Optional[str]:
        """No-op on non-Windows platforms."""
        return None


def _chrome_from_localappdata() -> Optional[str]:
    """Check per-user Chrome install in %LOCALAPPDATA%."""
    local_app_data = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"
    if local_app_data.is_file():
        logger.info("Chrome found in LOCALAPPDATA: %s", local_app_data)
        return str(local_app_data)
    return None


def _chrome_from_known_paths() -> Optional[str]:
    """Check well-known system-wide install paths."""
    for path_str in _KNOWN_CHROME_PATHS:
        p = Path(path_str)
        if p.is_file():
            logger.info("Chrome found at known path: %s", p)
            return str(p)
    return None


def _chrome_from_path() -> Optional[str]:
    """Try to find chrome via ``where chrome`` on PATH (Windows only)."""
    try:
        result = subprocess.run(
            ["where", "chrome"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if not lines:
                return None
            first_line = lines[0]
            if Path(first_line).is_file():
                logger.info("Chrome found on PATH: %s", first_line)
                return first_line
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def find_chrome(configured_path: Optional[str] = None) -> Optional[str]:
    """Find chrome.exe on this Windows machine.

    Search order:
      1. Explicitly configured path (CHROME_PATH env var)
      2. Windows Registry (HKLM + HKCU App Paths)
      3. %LOCALAPPDATA% per-user install
      4. Well-known system paths (Program Files)
      5. System PATH

    Args:
        configured_path: Optional explicit path from settings (CHROME_PATH).

    Returns:
        Absolute path to chrome.exe, or None if not found.
    """
    if sys.platform != "win32":
        logger.warning("chrome_finder: auto-detection is only supported on Windows")
        return None

    # 1. Explicit config
    if configured_path:
        p = Path(configured_path)
        if p.is_file():
            logger.info("Using configured CHROME_PATH: %s", configured_path)
            return str(p)
        logger.warning("Configured CHROME_PATH does not exist: %s", configured_path)

    # 2–5: Registry → LOCALAPPDATA → known paths → PATH
    for finder in (_chrome_from_registry, _chrome_from_localappdata, _chrome_from_known_paths, _chrome_from_path):
        path = finder()
        if path:
            return path

    logger.warning("Chrome could not be found automatically")
    return None


def launch_chrome(exe_path: str, port: int, user_data_dir: str) -> subprocess.Popen[bytes]:
    """Launch Chrome with remote debugging enabled.

    Args:
        exe_path: Absolute path to chrome.exe.
        port: CDP debugging port (e.g. 9222).
        user_data_dir: Separate user data directory to avoid conflicts
            with existing Chrome sessions.

    Returns:
        The Popen handle for the Chrome process.
    """
    # Ensure user-data-dir exists
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    cmd = [
        exe_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--ignore-certificate-errors",
    ]
    logger.info("Launching Chrome: %s", " ".join(cmd))

    process = subprocess.Popen(  # pylint: disable=consider-using-with
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Chrome started (PID %d)", process.pid)
    return process


async def wait_for_cdp(cdp_url: str, timeout: timedelta = timedelta(seconds=10)) -> bool:
    """Poll the CDP endpoint until it responds or timeout expires.

    Args:
        cdp_url: Base CDP URL, e.g. ``http://localhost:9222``.
        timeout: Maximum time to wait.

    Returns:
        True if CDP became reachable, False on timeout.
    """
    version_url = f"{cdp_url}/json/version"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout.total_seconds()

    async with httpx.AsyncClient() as client:
        while loop.time() < deadline:
            try:
                resp = await client.get(version_url, timeout=1.5)
                if resp.status_code == 200:
                    logger.info("CDP endpoint ready at %s", cdp_url)
                    return True
            except (httpx.ConnectError, httpx.TimeoutException, OSError):
                pass
            await asyncio.sleep(0.5)

    logger.warning("CDP endpoint did not become ready within %s", timeout)
    return False


def extract_port_from_cdp_url(cdp_url: str) -> int:
    """Extract the port number from a CDP URL.

    Args:
        cdp_url: E.g. ``http://localhost:9222``

    Returns:
        Port number (default 9222 if not specified).
    """
    parsed = urlparse(cdp_url)
    return parsed.port or 9222
