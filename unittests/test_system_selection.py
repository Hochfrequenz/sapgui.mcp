"""Unit tests for system selection: system_key resolution and server instructions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from sap_mcp_config import Config, SAPSystem

from sapguimcp.models.sap_results import LoginResult

_PATCH_GET_BACKEND = "sapguimcp.tools.sap_login_impl.get_backend"
_PATCH_GET_SETTINGS = "sapguimcp.tools.sap_login_impl.get_settings"
_PATCH_GET_SAP_CONFIG = "sapguimcp.tools.sap_login_impl.get_sap_config"


def _multi_system_config() -> Config:
    """Config with two systems sharing the same host but different clients."""
    return Config(
        default_system="dev-100",
        systems={
            "dev-100": SAPSystem(
                connection_name="DEV - ERP Development",
                host="https://dev-sap.example.com:44300",
                client="100",
                user="dev_user",
                password=SecretStr("dev_pass"),
                language="DE",
            ),
            "dev-200": SAPSystem(
                connection_name="DEV - ERP Development",
                host="https://dev-sap.example.com:44300",
                client="200",
                user="qa_user",
                password=SecretStr("qa_pass"),
                language="EN",
            ),
        },
    )


def _two_host_config() -> Config:
    """Config with two systems on *different* hosts (for URL-precedence tests)."""
    return Config(
        default_system="dev-100",
        systems={
            "dev-100": SAPSystem(
                connection_name="DEV",
                host="https://dev-sap.example.com:44300",
                client="100",
                user="dev_user",
                password=SecretStr("dev_pass"),
                language="DE",
            ),
            "prod-200": SAPSystem(
                connection_name="PROD",
                host="https://prod-sap.example.com:44300",
                client="200",
                user="prod_user",
                password=SecretStr("prod_pass"),
                language="EN",
            ),
        },
    )


def _make_settings(backend_type: str = "desktop", sap_url: str = "") -> MagicMock:
    settings = MagicMock()
    settings.backend_type = backend_type
    settings.sap_url = sap_url
    return settings


def _make_backend() -> AsyncMock:
    backend = AsyncMock()
    backend.login.return_value = LoginResult(success=True, user="test")
    backend.start_keepalive.return_value = None
    return backend


class TestSystemKeyResolution:
    """sap_login resolves system_key to SAP Logon entry and passes it to the backend."""

    @pytest.mark.anyio
    async def test_default_system_uses_sap_logon_entry(self) -> None:
        """Default system's SAP Logon entry is passed to backend, not the dict key."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=_make_settings("desktop")),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl()

        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] == "DEV - ERP Development"
        assert kwargs["client"] == "100"
        assert kwargs["username"] == "dev_user"

    @pytest.mark.anyio
    async def test_explicit_key_resolves_to_sap_logon_entry(self) -> None:
        """Passing a system_key resolves to that system's SAP Logon entry."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=_make_settings("desktop")),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl(system_key="dev-200")

        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] == "DEV - ERP Development"
        assert kwargs["client"] == "200"
        assert kwargs["username"] == "qa_user"

    @pytest.mark.anyio
    async def test_same_sap_logon_entry_different_clients(self) -> None:
        """Two system keys sharing the same SAP Logon entry but different clients work correctly."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()

        for key, expected_client in [("dev-100", "100"), ("dev-200", "200")]:
            backend = _make_backend()
            with (
                patch(_PATCH_GET_SETTINGS, return_value=_make_settings("desktop")),
                patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
                patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
            ):
                await sap_login_impl(system_key=key)

            _, kwargs = backend.login.call_args
            assert kwargs["connection_name"] == "DEV - ERP Development"
            assert kwargs["client"] == expected_client

    @pytest.mark.anyio
    async def test_webgui_backend_receives_sap_logon_entry(self) -> None:
        """WebGUI backend also receives the SAP Logon entry (even though it ignores it)."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=_make_settings("webgui")),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl(system_key="dev-200")

        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] == "DEV - ERP Development"

    @pytest.mark.anyio
    async def test_unknown_system_key_returns_error(self) -> None:
        """Passing an unknown system_key returns a failure instead of silently falling back."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=_make_settings("desktop")),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
        ):
            result = await sap_login_impl(system_key="nonexistent")

        assert result.success is False
        assert "nonexistent" in result.error
        assert "dev-100" in result.error


class TestUrlPrecedenceForNonDefaultSystem:
    """Regression coverage for issue #659.

    Symptom: when ``SAP_URL`` is set in the environment (legacy single-system
    setup) and the user picks a non-default system via ``system_key``, the
    login navigates to the *default* system's URL but fills the form with the
    chosen system's user/password/client. The end result is a session in the
    default Mandant — never in the requested one.

    Fix: when the resolved system has a ``host`` configured, that host wins
    over ``settings.sap_url``. The explicit ``url`` argument still has the
    highest priority.
    """

    @pytest.mark.anyio
    async def test_system_host_wins_over_env_sap_url_for_explicit_key(self) -> None:
        """system.host must win over settings.sap_url when system_key is given."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _two_host_config()
        settings = _make_settings(
            "webgui",
            sap_url="https://dev-sap.example.com:44300/sap/bc/gui/sap/its/webgui?sap-client=100",
        )
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl(system_key="prod-200")

        _, kwargs = backend.login.call_args
        assert "prod-sap.example.com" in kwargs["url"], (
            f"Expected prod-sap host, got {kwargs['url']!r}. "
            "settings.sap_url is leaking through and overriding the chosen system's host."
        )
        assert kwargs["username"] == "prod_user"
        assert kwargs["client"] == "200"

    @pytest.mark.anyio
    async def test_system_host_wins_over_env_sap_url_for_default_too(self) -> None:
        """Even for the default system, the system's host should be authoritative.

        This keeps URL resolution consistent: systems.json is the source of
        truth, and ``SAP_URL`` is only a legacy fallback for systems that have
        no ``host`` configured.
        """
        from sapguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _two_host_config()
        settings = _make_settings(
            "webgui",
            sap_url="https://stale-legacy.example.com/sap/bc/gui/sap/its/webgui",
        )
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl()

        _, kwargs = backend.login.call_args
        assert "dev-sap.example.com" in kwargs["url"]
        assert "stale-legacy" not in kwargs["url"]

    @pytest.mark.anyio
    async def test_explicit_url_argument_still_wins(self) -> None:
        """An explicit ``url`` argument keeps top priority — it's the manual escape hatch."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _two_host_config()
        settings = _make_settings(
            "webgui",
            sap_url="https://dev-sap.example.com:44300/sap/bc/gui/sap/its/webgui",
        )
        backend = _make_backend()

        manual = "https://manual-override.example.com/sap/bc/gui/sap/its/webgui"
        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl(url=manual, system_key="prod-200")

        _, kwargs = backend.login.call_args
        assert kwargs["url"] == manual

    @pytest.mark.anyio
    async def test_env_sap_url_used_when_system_has_no_host(self) -> None:
        """``settings.sap_url`` is the legacy fallback when ``host`` is empty.

        Some users may still rely on ``SAP_URL`` from a pre-systems.json setup.
        We must not break that path — only stop it from overriding a real host.
        """
        from sapguimcp.tools.sap_login_impl import sap_login_impl

        cfg = Config(
            default_system="legacy",
            systems={
                "legacy": SAPSystem(
                    connection_name="LEGACY",
                    host="https://legacy.example.com",  # required by Config validator
                    client="100",
                    user="legacy_user",
                    password=SecretStr("legacy_pass"),
                    language="DE",
                ),
            },
        )
        # The Config validator rejects an empty ``host`` at construction time,
        # so we strip it on a copy to simulate the legacy fallback path.
        legacy_system_no_host = cfg.systems["legacy"].model_copy(update={"host": ""})
        cfg = cfg.model_copy(update={"systems": {"legacy": legacy_system_no_host}})

        settings = _make_settings(
            "webgui",
            sap_url="https://from-env.example.com/sap/bc/gui/sap/its/webgui",
        )
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl()

        _, kwargs = backend.login.call_args
        assert kwargs["url"] == "https://from-env.example.com/sap/bc/gui/sap/its/webgui"


class TestServerInstructions:
    """Server instructions include available system keys so the LLM can offer choices."""

    def test_instructions_contain_system_keys(self) -> None:
        from sapguimcp.server import _build_instructions

        cfg = _multi_system_config()
        with patch("sapguimcp.server.get_sap_config", return_value=cfg):
            instructions = _build_instructions()

        assert "dev-100" in instructions
        assert "dev-200" in instructions
        assert "Default: 'dev-100'" in instructions

    def test_instructions_mention_choose_tool(self) -> None:
        from sapguimcp.server import _build_instructions

        cfg = _multi_system_config()
        with patch("sapguimcp.server.get_sap_config", return_value=cfg):
            instructions = _build_instructions()

        assert "choose" in instructions

    def test_instructions_graceful_when_config_missing(self) -> None:
        from sapguimcp.server import _build_instructions

        with patch("sapguimcp.server.get_sap_config", side_effect=FileNotFoundError):
            instructions = _build_instructions()

        assert "AVAILABLE SYSTEMS" not in instructions
        assert "sap_login" in instructions  # base instructions still present
