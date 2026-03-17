"""
General-purpose COM evaluate tool for SAP GUI desktop backend.

Mirrors browser_evaluate for WebGUI — gives the LLM an escape hatch
to perform arbitrary COM operations on SAP GUI elements by their ID.

Workflow: LLM calls sap_get_snapshot -> reads element IDs -> calls
sap_com_evaluate with operations on those elements.
"""

import json
import logging
from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models.com_results import ComEvaluateResult, ComOperation
from sapwebguimcp.tools._backend_utils import _is_desktop_backend

logger = logging.getLogger(__name__)

__all__ = ["register_com_tools"]


class ComOperationInput(BaseModel):
    """A single COM operation to execute."""

    element_id: str = Field(description="SAP GUI element path (e.g., 'wnd[0]/usr/txtFIELD')")
    action: Literal["get", "set", "call"] = Field(
        description="'get' (read property), 'set' (write property), or 'call' (invoke method)"
    )
    property_or_method: str = Field(
        description="COM property or method name (e.g., 'Text', 'SendVKey', 'GetCellValue')"
    )
    args: list[str | int | bool | float] | None = Field(
        default=None, description="Arguments for 'set' (value) or 'call' (method args)"
    )


def _serialize_com_result(value: Any) -> str:
    """Serialize a COM return value to JSON string.

    COM can return primitives, collections, or COM objects.
    """
    if value is None:
        return "null"
    if isinstance(value, (str, int, float, bool)):
        return json.dumps(value)
    # Try JSON serialization first
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def _execute_single_op(  # pylint: disable=too-many-return-statements
    session: Any, op: ComOperationInput
) -> ComOperation:
    """Execute a single COM operation on the COM thread (synchronous)."""
    try:
        elem = session.find_by_id(op.element_id)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return ComOperation(
            success=False,
            error=f"Element not found: {op.element_id} ({exc})",
            element_id=op.element_id,
            action=op.action,
            property_or_method=op.property_or_method,
        )

    # Unwrap Python wrapper to get raw COM dispatch object
    raw: Any = getattr(elem, "com", getattr(elem, "_com", elem))

    try:
        if op.action == "get":
            value = getattr(raw, op.property_or_method)
            return ComOperation(
                element_id=op.element_id,
                action=op.action,
                property_or_method=op.property_or_method,
                result=_serialize_com_result(value),
            )

        if op.action == "set":
            set_value = op.args[0] if op.args else ""
            setattr(raw, op.property_or_method, set_value)
            # Read back the value to confirm
            read_back = getattr(raw, op.property_or_method)
            return ComOperation(
                element_id=op.element_id,
                action=op.action,
                property_or_method=op.property_or_method,
                result=_serialize_com_result(read_back),
            )

        # action == "call"
        method = getattr(raw, op.property_or_method)
        result = method(*(op.args or []))
        return ComOperation(
            element_id=op.element_id,
            action=op.action,
            property_or_method=op.property_or_method,
            result=_serialize_com_result(result),
        )

    except Exception as exc:  # pylint: disable=broad-exception-caught
        return ComOperation(
            success=False,
            error=f"{op.action} {op.property_or_method} on {op.element_id}: {exc}",
            element_id=op.element_id,
            action=op.action,
            property_or_method=op.property_or_method,
        )


def register_com_tools(mcp: FastMCP) -> None:
    """Register COM evaluate tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            openWorldHint=False,
        ),
        description=(
            "Execute COM operations on SAP GUI elements (desktop backend only). "
            "Use sap_get_snapshot first to see element IDs, then call this tool. "
            "Supports batch: multiple operations in a single call (e.g., fill 3 fields + click a button). "
            "Use with caution — this has full access to the SAP GUI scripting interface. "
            "Prefer SAP-specific tools (sap_se16_query, sap_se37_lookup, etc.) when available.\n\n"
            "**Actions:**\n"
            "- `get`: Read a property (e.g., Text, Selected, RowCount)\n"
            "- `set`: Write a property (e.g., Text='value', Selected=True)\n"
            "- `call`: Invoke a method (e.g., SendVKey(0), GetCellValue(0, 'COL'))\n\n"
            "**Examples:**\n"
            "```json\n"
            '{"operations": [\n'
            '  {"element_id": "wnd[0]/usr/txtFIELD", "action": "set",\n'
            '   "property_or_method": "Text", "args": ["value"]},\n'
            '  {"element_id": "wnd[0]", "action": "call", "property_or_method": "SendVKey", "args": [0]}\n'
            "]}\n"
            "```"
        ),
    )
    async def sap_com_evaluate(
        operations: list[ComOperationInput],
        session: str | None = None,
        agent_id: str | None = None,
    ) -> ComEvaluateResult:
        """
        Execute one or more COM operations on SAP GUI elements.

        Args:
            operations: List of operations to execute sequentially.
                Each operation has: element_id, action (get/set/call),
                property_or_method, and optional args.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            ComEvaluateResult with results for each operation.
        """
        if not operations:
            return ComEvaluateResult.failure("No operations provided")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_com_evaluate")
        except ValueError as e:
            return ComEvaluateResult.failure(f"Session error: {e}")

        if not _is_desktop_backend(backend):
            return ComEvaluateResult.failure(
                "sap_com_evaluate is only available on the desktop backend. "
                + "Use browser_evaluate for WebGUI."
            )

        from sapwebguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        assert isinstance(backend, DesktopBackend)  # noqa: S101
        desktop_session = backend._require_session()  # pylint: disable=protected-access
        com = backend._com  # pylint: disable=protected-access

        def _run_all() -> list[ComOperation]:
            results: list[ComOperation] = []
            for op in operations:
                results.append(_execute_single_op(desktop_session, op))
            return results

        try:
            op_results = await com.run(_run_all)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("sap_com_evaluate failed")
            return ComEvaluateResult.failure(f"COM execution error: {exc}")

        # Per-operation errors are visible in each ComOperation.
        # Top-level success=True as long as the batch executed (even if some ops failed).
        return ComEvaluateResult(operations=op_results)
