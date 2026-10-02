"""MCP resource for discovering the sap_run_script sandbox contract."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sapguimcp.tools.script_tools import get_sandbox_contract

if TYPE_CHECKING:
    from fastmcp import FastMCP

__all__ = ["register_sandbox_resources"]


def register_sandbox_resources(mcp: FastMCP) -> None:
    """Register sandbox contract resource with the MCP server."""

    @mcp.resource("sandbox://sap_run_script", mime_type="application/json")
    def get_sandbox_contract_resource() -> str:
        """
        Get the sap_run_script sandbox contract.

        Returns allowed builtins, injected names, and the contract version.

        Returns:
            JSON string describing the sandbox contract.
        """
        contract = get_sandbox_contract()
        return json.dumps(contract.model_dump(mode="json"))
