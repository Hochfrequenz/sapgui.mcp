"""SAP integration benchmarks for sap_get_capabilities response.

Requires SAP WebGUI credentials. Run with:
    pytest unittests/webgui/test_benchmark_capabilities_sap.py -v -s

See also: docs/test-plan-compact-sap-knowledge.md
"""

import json
import os

import pytest
from mcp import ClientSession

from unittests.conftest import has_sap_webgui_creds


def _approx_tokens(text: str) -> int:
    """Rough token estimate: chars / 4."""
    return len(text) // 4


pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not has_sap_webgui_creds(), reason="SAP WebGUI credentials not configured"),
]


class TestCapabilitiesSAPBenchmark:
    """
    Behavioral benchmarks that run against a live SAP system.

    These tests verify that the compacted knowledge still produces correct
    guidance in real SAP scenarios.
    """

    async def test_capabilities_response_over_mcp(self, sap_mcp_client: ClientSession) -> None:
        """Measure actual capabilities response size over MCP protocol."""
        result = await sap_mcp_client.call_tool("sap_get_capabilities", {})
        assert result.content

        text = result.content[0].text  # type: ignore[union-attr]
        data = json.loads(text)

        assert data["success"] is True

        response_size = len(text)
        approx_tokens = _approx_tokens(text)
        tool_count = len(data["tools"])
        knowledge_size = len(data.get("sap_knowledge", ""))

        print(f"\n{'='*60}")
        print(f"SAP BENCHMARK: Live sap_get_capabilities response")
        print(f"{'='*60}")
        print(f"Response:  {response_size:>8,} chars  (~{approx_tokens:,} tokens)")
        print(f"Tools:     {tool_count}")
        print(f"Knowledge: {knowledge_size:>8,} chars  (~{_approx_tokens(data.get('sap_knowledge', '')):,} tokens)")
        print(f"{'='*60}")

        # Compact target: below 10,000 tokens
        assert approx_tokens < 10000, f"Response too large: ~{approx_tokens} tokens"

    async def test_login_still_recommends_capabilities(self, sap_mcp_client: ClientSession) -> None:
        """After login, guidance still mentions sap_get_capabilities."""
        # sap_login reads credentials from environment (SAP_USER, SAP_PASSWORD, SAP_LANGUAGE)
        # Only url and client are explicit parameters
        login_args = {
            "url": os.environ["SAP_URL"],
            "client": os.environ["SAP_MANDANT"],
        }

        result = await sap_mcp_client.call_tool("sap_login", login_args)
        assert result.content
        text = result.content[0].text  # type: ignore[union-attr]
        data = json.loads(text)

        assert data["success"] is True, f"Login failed: {data.get('error')}"
        assert "sap_get_capabilities" in data.get("guidance", ""), (
            "Login guidance should still recommend calling sap_get_capabilities"
        )

    async def test_shortcuts_section_actionable(self, sap_mcp_client: ClientSession) -> None:
        """Verify compact knowledge still contains all common shortcuts."""
        result = await sap_mcp_client.call_tool("sap_get_capabilities", {})
        text = result.content[0].text  # type: ignore[union-attr]
        data = json.loads(text)
        knowledge = data["sap_knowledge"]

        for shortcut in ["F3", "F8", "Ctrl+S", "Shift+F3", "F4"]:
            assert shortcut in knowledge, f"Shortcut {shortcut} missing from knowledge"

    async def test_multi_session_tools_still_listed(self, sap_mcp_client: ClientSession) -> None:
        """Session management tools must still be discoverable."""
        result = await sap_mcp_client.call_tool("sap_get_capabilities", {})
        text = result.content[0].text  # type: ignore[union-attr]
        data = json.loads(text)

        tool_names = {t["name"] for t in data["tools"]}
        session_tools = {"sap_session_list", "sap_session_close", "sap_session_bind", "sap_session_release"}
        missing = session_tools - tool_names
        assert not missing, f"Session tools missing from capabilities: {missing}"

        # Knowledge should mention session concept
        knowledge = data["sap_knowledge"]
        assert "Multi-Session" in knowledge
        assert "session" in knowledge.lower()

    async def test_catalog_search_guidance_present(self, sap_mcp_client: ClientSession) -> None:
        """Verify catalog-first guidance survived compaction."""
        result = await sap_mcp_client.call_tool("sap_get_capabilities", {})
        text = result.content[0].text  # type: ignore[union-attr]
        data = json.loads(text)
        knowledge = data["sap_knowledge"]

        assert "search_transactions" in knowledge, "Catalog search guidance missing"
        assert "BEFORE guessing" in knowledge, "Catalog-first emphasis missing"

    async def test_state_bleeding_recovery_guidance(self, sap_mcp_client: ClientSession) -> None:
        """Verify state bleeding recovery guidance survived compaction."""
        result = await sap_mcp_client.call_tool("sap_get_capabilities", {})
        text = result.content[0].text  # type: ignore[union-attr]
        data = json.loads(text)
        knowledge = data["sap_knowledge"]

        assert "reset_first=True" in knowledge, "State bleeding fix missing"
        assert "State Bleeding" in knowledge, "State bleeding section missing"

    async def test_abapgit_preference_guidance(self, sap_mcp_client: ClientSession) -> None:
        """Verify abapGit preference survived compaction."""
        result = await sap_mcp_client.call_tool("sap_get_capabilities", {})
        text = result.content[0].text  # type: ignore[union-attr]
        data = json.loads(text)
        knowledge = data["sap_knowledge"]

        assert "abapGit" in knowledge, "abapGit mention missing"
        assert "preferred" in knowledge.lower() or "bevorzugt" in knowledge.lower(), (
            "abapGit preference guidance missing"
        )
