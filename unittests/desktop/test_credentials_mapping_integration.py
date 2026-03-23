"""Integration test for per-system credential mapping (SAP_CREDENTIALS)."""

from __future__ import annotations

import json
import os

import pytest
from dotenv import load_dotenv
from sapsucker import SapGui

from sapwebguimcp.backend.desktop import DesktopBackend
from sapwebguimcp.backend.desktop._com_thread import ComThread
from sapwebguimcp.models.config import get_settings
from unittests.conftest import is_sap_integration_test_machine
from unittests.desktop.conftest import skip_no_creds, skip_not_sap


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_discover_clients_uses_credentials_mapping() -> None:
    """discover_clients resolves credentials from SAP_CREDENTIALS mapping."""
    load_dotenv()
    connection_name = os.environ["SAP_CONNECTION_NAME"]
    user = os.environ["SAP_USER"]
    password = os.environ["SAP_PASSWORD"]

    # Set SAP_CREDENTIALS with the correct credentials for this connection
    mapping = {connection_name: {"user": user, "password": password}}
    os.environ["SAP_CREDENTIALS"] = json.dumps(mapping)
    # Clear global credentials to prove the mapping is used
    os.environ["SAP_USER"] = ""
    os.environ["SAP_PASSWORD"] = ""

    com = ComThread()
    backend = DesktopBackend(com_thread=com)
    try:
        # Login via the backend fixture to establish the base session
        r = await backend.login(
            "x",
            user,
            password,
            os.environ.get("SAP_MANDANT", "100"),
            os.environ.get("SAP_LANGUAGE", "DE"),
        )
        assert r.success, f"Base login failed: {r.error}"

        result = await backend.discover_clients(connection_name)
        assert result["session_id"] is not None
        assert len(result["clients"]) > 0, "Credentials mapping worked — T000 returned clients"
    finally:
        # Cleanup: close connections and restore env
        try:
            app = await com.run(lambda: SapGui.connect())
            raw_conns = await com.run(lambda: app.com.Children)
            count = await com.run(lambda: raw_conns.Count)
            for i in range(count - 1, -1, -1):
                try:
                    await com.run(lambda i=i: raw_conns(i).CloseConnection())
                except Exception:
                    pass
        except Exception:
            pass
        com.shutdown()
        # Restore env
        os.environ["SAP_USER"] = user
        os.environ["SAP_PASSWORD"] = password
        if "SAP_CREDENTIALS" in os.environ:
            del os.environ["SAP_CREDENTIALS"]


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_discover_clients_fails_with_wrong_mapping_password() -> None:
    """discover_clients fails when SAP_CREDENTIALS has wrong password — proves mapping is used."""
    load_dotenv()
    connection_name = os.environ["SAP_CONNECTION_NAME"]
    user = os.environ["SAP_USER"]
    password = os.environ["SAP_PASSWORD"]

    # Set SAP_CREDENTIALS with WRONG password
    mapping = {connection_name: {"user": user, "password": "WRONG_PASSWORD_12345"}}
    os.environ["SAP_CREDENTIALS"] = json.dumps(mapping)
    os.environ["SAP_USER"] = ""
    os.environ["SAP_PASSWORD"] = ""

    com = ComThread()
    backend = DesktopBackend(com_thread=com)
    try:
        # Login with correct creds for base session
        r = await backend.login(
            "x",
            user,
            password,
            os.environ.get("SAP_MANDANT", "100"),
            os.environ.get("SAP_LANGUAGE", "DE"),
        )
        assert r.success, f"Base login failed: {r.error}"

        # discover_clients should fail because mapping has wrong password
        with pytest.raises(Exception, match="(?i)login|password|logon|anmeld"):
            await backend.discover_clients(connection_name)
    finally:
        try:
            app = await com.run(lambda: SapGui.connect())
            raw_conns = await com.run(lambda: app.com.Children)
            count = await com.run(lambda: raw_conns.Count)
            for i in range(count - 1, -1, -1):
                try:
                    await com.run(lambda i=i: raw_conns(i).CloseConnection())
                except Exception:
                    pass
        except Exception:
            pass
        com.shutdown()
        os.environ["SAP_USER"] = user
        os.environ["SAP_PASSWORD"] = password
        if "SAP_CREDENTIALS" in os.environ:
            del os.environ["SAP_CREDENTIALS"]
