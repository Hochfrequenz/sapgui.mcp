"""Integration test for sap_discover_clients with T000 query."""

from __future__ import annotations

import pytest

from unittests.desktop.conftest import go_home, skip_no_creds, skip_not_sap


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_discover_clients_returns_t000_entries(backend) -> None:
    """discover_clients logs in, queries T000, and returns client list."""
    import os

    connection_name = os.environ.get("SAP_CONNECTION_NAME", "HFQ")
    result = await backend.discover_clients(connection_name)

    assert result["session_id"] is not None, "Expected a session_id"
    assert result["default_client"], "Expected a default_client"
    assert len(result["clients"]) > 0, "Expected at least one client from T000"

    # Each client should have id and description
    for client in result["clients"]:
        assert "id" in client, f"Client missing 'id': {client}"
        assert len(client["id"]) == 3, f"Client id should be 3 digits: {client['id']}"

    # The default client should be in the returned list
    client_ids = [c["id"] for c in result["clients"]]
    assert (
        result["default_client"] in client_ids
    ), f"Default client {result['default_client']} not found in T000 results: {client_ids}"

    await go_home(backend)
