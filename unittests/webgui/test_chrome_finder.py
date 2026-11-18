"""Integration tests for Chrome auto-detection and launch."""

import os
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from sapguimcp.backend.webgui.chrome_finder import (
    extract_port_from_cdp_url,
    find_chrome,
    launch_chrome,
    wait_for_cdp,
)
from sapguimcp.models.config import SapGuiSettings

# =============================================================================
# Tests for find_chrome()
# =============================================================================


class TestFindChrome:
    """Tests for Chrome auto-detection on Windows."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_find_chrome_returns_existing_exe(self) -> None:
        """find_chrome() should return a path that actually exists."""
        path = find_chrome()
        # On a dev machine with Chrome installed, this should succeed
        if path is not None:
            assert Path(path).is_file()
            assert path.lower().endswith(".exe")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_find_chrome_with_explicit_valid_path(self, tmp_path: Path) -> None:
        """find_chrome() should prefer an explicitly configured path."""
        fake_chrome = tmp_path / "chrome.exe"
        fake_chrome.write_text("fake")

        result = find_chrome(configured_path=str(fake_chrome))
        assert result == str(fake_chrome)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_find_chrome_with_invalid_configured_path_falls_back(self) -> None:
        """find_chrome() should fall back to auto-detection if configured path doesn't exist."""
        result = find_chrome(configured_path=r"C:\nonexistent\chrome.exe")
        # Should still find Chrome via registry/known paths (or None if not installed)
        if result is not None:
            assert Path(result).is_file()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_find_chrome_registry_detection(self) -> None:
        """find_chrome() should find Chrome via Windows registry on a machine with Chrome."""
        # On this dev machine, Chrome should be findable
        path = find_chrome()
        assert path is not None, "Chrome should be installed on this dev machine"
        assert Path(path).is_file()


# =============================================================================
# Tests for launch_chrome()
# =============================================================================


class TestLaunchChrome:
    """Tests for Chrome process launching."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_launch_chrome_starts_process(self, tmp_path: Path) -> None:
        """launch_chrome() should start a Chrome process and return a Popen handle."""
        chrome_path = find_chrome()
        if chrome_path is None:
            pytest.skip("Chrome not installed")

        user_data_dir = str(tmp_path / "chrome-test-data")
        # Use a non-standard port to avoid conflicts
        port = 19222

        process = launch_chrome(chrome_path, port, user_data_dir)
        try:
            assert isinstance(process, subprocess.Popen)
            assert process.pid > 0
            # Chrome should still be running
            assert process.poll() is None
        finally:
            process.terminate()
            process.wait(timeout=10)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_launch_chrome_creates_user_data_dir(self, tmp_path: Path) -> None:
        """launch_chrome() should create the user data directory if it doesn't exist."""
        chrome_path = find_chrome()
        if chrome_path is None:
            pytest.skip("Chrome not installed")

        user_data_dir = str(tmp_path / "new-data-dir")
        assert not Path(user_data_dir).exists()

        process = launch_chrome(chrome_path, port=19223, user_data_dir=user_data_dir)
        try:
            assert Path(user_data_dir).is_dir()
        finally:
            process.terminate()
            process.wait(timeout=10)


# =============================================================================
# Tests for wait_for_cdp()
# =============================================================================


class TestWaitForCdp:
    """Tests for CDP endpoint readiness polling."""

    @pytest.mark.anyio
    async def test_wait_for_cdp_timeout_on_unreachable_port(self) -> None:
        """wait_for_cdp() should return False if CDP never becomes reachable."""
        result = await wait_for_cdp("http://localhost:19999", timeout=timedelta(seconds=2))
        assert result is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    @pytest.mark.anyio
    async def test_wait_for_cdp_succeeds_after_chrome_launch(self, tmp_path: Path) -> None:
        """wait_for_cdp() should return True once Chrome's CDP endpoint is ready."""
        chrome_path = find_chrome()
        if chrome_path is None:
            pytest.skip("Chrome not installed")

        port = 19224
        user_data_dir = str(tmp_path / "chrome-cdp-test")
        process = launch_chrome(chrome_path, port, user_data_dir)

        try:
            result = await wait_for_cdp(f"http://localhost:{port}", timeout=timedelta(seconds=15))
            assert result is True
        finally:
            process.terminate()
            process.wait(timeout=10)


# =============================================================================
# Tests for extract_port_from_cdp_url()
# =============================================================================


class TestExtractPort:
    """Tests for CDP URL port extraction."""

    def test_extract_port_standard(self) -> None:
        assert extract_port_from_cdp_url("http://localhost:9222") == 9222

    def test_extract_port_custom(self) -> None:
        assert extract_port_from_cdp_url("http://127.0.0.1:9333") == 9333

    def test_extract_port_default_when_missing(self) -> None:
        assert extract_port_from_cdp_url("http://localhost") == 9222


# =============================================================================
# Tests for config integration
# =============================================================================


class TestConfigIntegration:
    """Tests that new config fields work correctly."""

    def test_default_chrome_path_is_empty(self) -> None:
        """CHROME_PATH should default to empty string."""
        with patch.dict(os.environ, {}, clear=True):
            settings = SapGuiSettings(_env_file=None)
        assert settings.chrome_path == ""

    def test_default_chrome_user_data_dir(self) -> None:
        """CHROME_USER_DATA_DIR should default to <tempdir>/chrome-debug."""
        with patch.dict(os.environ, {}, clear=True):
            settings = SapGuiSettings(_env_file=None)
        expected = str(Path(tempfile.gettempdir()) / "chrome-debug")
        assert settings.chrome_user_data_dir == expected

    def test_chrome_path_from_env(self) -> None:
        """CHROME_PATH should be loadable from environment."""
        with patch.dict(os.environ, {"CHROME_PATH": r"C:\custom\chrome.exe"}, clear=True):
            settings = SapGuiSettings(_env_file=None)
        assert settings.chrome_path == r"C:\custom\chrome.exe"

    def test_chrome_user_data_dir_from_env(self) -> None:
        """CHROME_USER_DATA_DIR should be loadable from environment."""
        with patch.dict(os.environ, {"CHROME_USER_DATA_DIR": r"D:\my-chrome"}, clear=True):
            settings = SapGuiSettings(_env_file=None)
        assert settings.chrome_user_data_dir == r"D:\my-chrome"


# =============================================================================
# End-to-end: find + launch + wait + connect
# =============================================================================


class TestEndToEnd:
    """Full integration test: find Chrome, launch it, wait for CDP, verify connection."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    @pytest.mark.anyio
    async def test_full_auto_launch_cycle(self, tmp_path: Path) -> None:
        """End-to-end: find_chrome → launch_chrome → wait_for_cdp → verify CDP responds."""
        chrome_path = find_chrome()
        if chrome_path is None:
            pytest.skip("Chrome not installed")

        port = 19225
        user_data_dir = str(tmp_path / "chrome-e2e")
        cdp_url = f"http://localhost:{port}"

        process = launch_chrome(chrome_path, port, user_data_dir)
        try:
            # Wait for CDP
            ready = await wait_for_cdp(cdp_url, timeout=timedelta(seconds=15))
            assert ready, "CDP should become reachable after launch"

            # Verify we can actually get version info
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{cdp_url}/json/version", timeout=5.0)
                assert resp.status_code == 200
                data = resp.json()
                assert "Browser" in data
        finally:
            process.terminate()
            process.wait(timeout=10)
