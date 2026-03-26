"""Benchmark tests for sap_get_capabilities response size.

Compares the original (detailed) vs. compact sap_knowledge.md variants.
Unit tests run without SAP; integration tests require SAP credentials.

See also: docs/test-plan-compact-sap-knowledge.md
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sapwebguimcp.server import mcp

# ---------------------------------------------------------------------------
# Test data paths
# ---------------------------------------------------------------------------

_TESTDATA = Path(__file__).parent / "webgui" / "testdata"
_KNOWLEDGE_ORIGINAL = _TESTDATA / "sap_knowledge_original.md"
_KNOWLEDGE_COMPACT = _TESTDATA / "sap_knowledge_compact.md"


def _load_knowledge(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _approx_tokens(text: str) -> int:
    """Rough token estimate: chars / 4 (conservative for English/mixed content)."""
    return len(text) // 4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _call_capabilities_with_knowledge(knowledge_content: str) -> dict:
    """Call sap_get_capabilities with mocked knowledge content, return JSON dict."""
    mock_file = MagicMock()
    mock_file.read_text.return_value = knowledge_content

    mock_package = MagicMock()
    mock_package.joinpath.return_value = mock_file

    with patch("sapwebguimcp.tools.sap_tools.resources") as mock_resources:
        mock_resources.files.return_value = mock_package

        tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
        result = asyncio.run(tools["sap_get_capabilities"].fn())

    return json.loads(result.model_dump_json())


# ===========================================================================
# Unit benchmarks (no SAP needed)
# ===========================================================================


class TestCapabilitiesResponseSize:
    """Measure and compare response sizes for both knowledge variants."""

    @pytest.fixture(scope="class")
    def original_response(self) -> dict:
        return _call_capabilities_with_knowledge(_load_knowledge(_KNOWLEDGE_ORIGINAL))

    @pytest.fixture(scope="class")
    def compact_response(self) -> dict:
        return _call_capabilities_with_knowledge(_load_knowledge(_KNOWLEDGE_COMPACT))

    def test_both_variants_succeed(self, original_response: dict, compact_response: dict) -> None:
        assert original_response["success"] is True
        assert compact_response["success"] is True

    def test_tool_count_identical(self, original_response: dict, compact_response: dict) -> None:
        """Both variants must return the same tools."""
        orig_tools = {t["name"] for t in original_response["tools"]}
        compact_tools = {t["name"] for t in compact_response["tools"]}
        assert orig_tools == compact_tools, f"Tool difference: {orig_tools ^ compact_tools}"

    def test_compact_is_smaller(self, original_response: dict, compact_response: dict) -> None:
        orig_size = len(json.dumps(original_response))
        compact_size = len(json.dumps(compact_response))
        reduction_pct = (1 - compact_size / orig_size) * 100

        print(f"\n{'='*60}")
        print(f"BENCHMARK: sap_get_capabilities response size")
        print(f"{'='*60}")
        print(f"Original:  {orig_size:>8,} chars  (~{_approx_tokens(json.dumps(original_response)):,} tokens)")
        print(f"Compact:   {compact_size:>8,} chars  (~{_approx_tokens(json.dumps(compact_response)):,} tokens)")
        print(f"Reduction: {orig_size - compact_size:>8,} chars  ({reduction_pct:.1f}%)")
        print(f"{'='*60}")

        assert compact_size < orig_size, "Compact response should be smaller"

    def test_compact_knowledge_below_target(self, compact_response: dict) -> None:
        """Compact response should be below 10,000 tokens (down from ~11,900)."""
        full_json = json.dumps(compact_response)
        approx = _approx_tokens(full_json)
        print(f"\nCompact total: ~{approx:,} tokens (target: <10,000)")
        assert approx < 10000, f"Response too large: ~{approx} tokens"

    def test_knowledge_size_breakdown(self) -> None:
        """Show token breakdown for each knowledge variant."""
        original = _load_knowledge(_KNOWLEDGE_ORIGINAL)
        compact = _load_knowledge(_KNOWLEDGE_COMPACT)

        print(f"\n{'='*60}")
        print(f"BENCHMARK: sap_knowledge.md size comparison")
        print(f"{'='*60}")
        print(f"Original:  {len(original):>8,} chars  {original.count(chr(10)):>4} lines  ~{_approx_tokens(original):,} tokens")
        print(f"Compact:   {len(compact):>8,} chars  {compact.count(chr(10)):>4} lines  ~{_approx_tokens(compact):,} tokens")
        print(f"Reduction: {len(original) - len(compact):>8,} chars  ({(1 - len(compact)/len(original))*100:.1f}%)")
        print(f"{'='*60}")

    def test_core_sections_preserved_in_compact(self, compact_response: dict) -> None:
        """Verify that critical behavioral guidance survived compaction."""
        knowledge = compact_response["sap_knowledge"]

        # These sections MUST be present — they drive core LLM behavior
        required_fragments = [
            "search_transactions",        # Catalog-first guidance
            "browser_evaluate",           # MCP > manual eval
            "Keyboard Shortcuts",         # Shortcuts reference
            "sap_get_shortcuts",          # Tool reference in shortcuts
            "reset_first=True",           # State bleeding recovery
            "State Bleeding",             # Debugging section
            "abapGit",                    # Git-preferred guidance
            "Multi-Session",              # Parallel agent awareness
            "sap_session_list",           # Session management
            "Stateful Selection Screens", # Selection screen warning
            "help.sap.com",              # SAP Help Portal workaround
            "sap_get_form_fields",        # Form state tools
        ]

        missing = [f for f in required_fragments if f not in knowledge]
        assert not missing, f"Core guidance missing from compact knowledge: {missing}"

    def test_removed_details_absent_in_compact(self, compact_response: dict) -> None:
        """Verify that detailed content was actually removed."""
        knowledge = compact_response["sap_knowledge"]

        # These verbose details should be GONE in compact version
        removed_fragments = [
            "Install abapGit in SAP",           # Setup steps
            "ZABAPGIT_STANDALONE",              # Finding abapGit in SAP
            "ZCL_MY_CLASS.clas.abap",           # File naming error example
            "git mv src/ZCL_MY_CLASS",          # Fix example
            "Write code in Claude Code",        # Workflow step-by-step
            "Pull status unknown",              # Known issue detail (kept as brief mention)
            "System → Erzeugen Modus",          # Performance tip
            "one Git repository corresponds",   # Scope explanation
            "sap_session_bind(session_id=",     # Workflow code example
            "subagent-1",                       # Sub-agent example
            "sap_fill_form({\"Name\"",          # Code example
            "Focus grid before pagination",     # ALV implementation detail
            "Row deduplication via set",         # ALV implementation detail
            "~7 rows/second",                   # ALV performance stat
        ]

        still_present = [f for f in removed_fragments if f in knowledge]
        assert not still_present, f"Detailed content not removed: {still_present}"


# SAP integration benchmarks live in unittests/webgui/test_benchmark_capabilities_sap.py
# (requires sap_mcp_client fixture from webgui/conftest.py)
