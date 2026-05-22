"""
General-purpose COM evaluate tool for SAP GUI desktop backend.

Mirrors browser_evaluate for WebGUI — gives the LLM an escape hatch
to perform arbitrary COM operations on SAP GUI elements by their ID.

Workflow: LLM calls sap_com_snapshot -> reads element IDs -> calls
sap_com_evaluate with operations on those elements.
"""

import json
import logging
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from sapguimcp.backend.desktop.models.com_results import ComEvaluateResult, ComOperation, ComSnapshotResult
from sapguimcp.backend.manager import get_backend

logger = logging.getLogger(__name__)

__all__ = ["register_com_tools", "FindByNameRef"]


class FindByNameRef(BaseModel):
    """Reference to resolve an element via SAP's FindByName API."""

    name: str = Field(description="SAP field name (e.g. 'BUT000-NAME_LAST')")
    type_name: str = Field(description="SAP GUI type name (e.g. 'GuiTextField')")


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
        default=None,
        description=(
            "For 'set': single-element list with the value, e.g. ['hello']. "
            "For 'call': positional args, e.g. [0, 'MATNR']. Not used for 'get'."
        ),
    )
    find_by_name: FindByNameRef | None = Field(
        default=None,
        description=(
            "Alternative element lookup via FindByName. "
            "When set, element_id is the container to search within (e.g. 'wnd[0]/usr')."
        ),
    )


def _safe_attr(obj: Any, name: str) -> str:
    """Safely read a COM attribute, returning empty string on any failure."""
    try:
        return str(getattr(obj, name, ""))
    except Exception:  # pylint: disable=broad-exception-caught
        return ""


def _serialize_com_result(value: Any) -> str:
    """Serialize a COM return value to JSON string.

    COM can return primitives, collections, or COM objects.
    Collections (objects with .Count and .Item) are serialized as JSON arrays.
    """
    if value is None:
        return "null"
    if isinstance(value, (str, int, float, bool)):
        return json.dumps(value)
    # Try COM collection serialization
    try:
        count = value.Count
        if isinstance(count, int) and count >= 0:
            cap = min(count, 100)
            items = []
            for i in range(cap):
                item = value.Item(i)
                items.append(
                    {
                        "Id": _safe_attr(item, "Id"),
                        "Type": _safe_attr(item, "Type"),
                        "Name": _safe_attr(item, "Name"),
                        "Text": _safe_attr(item, "Text"),
                    }
                )
            return json.dumps(items)
    except Exception:  # pylint: disable=broad-exception-caught
        pass  # Not a well-behaved collection, fall through
    # Fallback
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def _execute_single_op(  # pylint: disable=too-many-return-statements,too-many-locals
    session: Any, op: ComOperationInput
) -> ComOperation:
    """Execute a single COM operation on the COM thread (synchronous)."""
    # --- Element resolution ---
    try:
        if op.find_by_name is not None:
            container = session.find_by_id(op.element_id)
            raw_container: Any = getattr(container, "com", getattr(container, "_com", container))
            resolved = raw_container.FindByName(op.find_by_name.name, op.find_by_name.type_name)
            if resolved is None:
                return ComOperation(
                    success=False,
                    error=(
                        f"FindByName({op.find_by_name.name!r}, {op.find_by_name.type_name!r}) "
                        f"returned nothing in {op.element_id}"
                    ),
                    element_id=op.element_id,
                    action=op.action,
                    property_or_method=op.property_or_method,
                )
            raw = resolved  # Already a raw COM object
        else:
            elem = session.find_by_id(op.element_id)
            raw = getattr(elem, "com", getattr(elem, "_com", elem))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return ComOperation(
            success=False,
            error=f"Element not found: {op.element_id} ({exc})",
            element_id=op.element_id,
            action=op.action,
            property_or_method=op.property_or_method,
        )

    # --- Chained property traversal ---
    parts = op.property_or_method.split(".")
    # Safety: block upward traversal
    if any(p.lower() == "parent" for p in parts):
        return ComOperation(
            success=False,
            error="'Parent' traversal is blocked for safety. Access elements directly by ID.",
            element_id=op.element_id,
            action=op.action,
            property_or_method=op.property_or_method,
        )

    try:
        # Traverse to the target object
        obj = raw
        for part in parts[:-1]:
            obj = getattr(obj, part)
        final = parts[-1]

        if op.action == "get":
            value = getattr(obj, final)
            return ComOperation(
                element_id=op.element_id,
                action=op.action,
                property_or_method=op.property_or_method,
                result=_serialize_com_result(value),
            )

        if op.action == "set":
            set_value = op.args[0] if op.args else ""
            setattr(obj, final, set_value)
            read_back = getattr(obj, final)
            return ComOperation(
                element_id=op.element_id,
                action=op.action,
                property_or_method=op.property_or_method,
                result=_serialize_com_result(read_back),
            )

        # action == "call"
        method = getattr(obj, final)
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
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Get the SAP GUI element tree with element IDs (desktop backend only). "
            "Returns an indented tree of all elements on the current screen. "
            "Each line shows: type, name, and text value. "
            "Use the element paths as element_id in sap_com_evaluate.\n\n"
            "**depth** controls how many tree levels to return (default 3). "
            "Increase depth to see deeper nested elements. "
            "When truncated, the response shows how many elements were hidden.\n\n"
            "Example output:\n"
            "```\n"
            "GuiMainWindow[wnd[0]]: 'SAP Easy Access'\n"
            "  GuiOkCodeField[tbar[0]/okcd]: ''\n"
            "  GuiTextField[usr/txtFIELD]: 'value'\n"
            "```\n"
            "The path in brackets (e.g., `wnd[0]/usr/txtFIELD`) is the element_id."
        ),
    )
    async def sap_com_snapshot(
        depth: Annotated[int, Field(ge=1)] = 3,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> ComSnapshotResult:
        """
        Get the SAP GUI element tree with element IDs.

        Args:
            depth: Number of tree levels to return (default 3).
                Increase to see deeper nested elements.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            ComSnapshotResult with the element tree as text and truncation metadata.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_com_snapshot")
        except ValueError as e:
            return ComSnapshotResult.failure(str(e))

        if not backend.backend_type == "desktop":
            return ComSnapshotResult.failure(
                "sap_com_snapshot is only available on the desktop backend. " + "Use browser_snapshot for WebGUI."
            )

        from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        assert isinstance(backend, DesktopBackend)  # Guaranteed by _is_desktop_backend check above
        snapshot, max_depth_found, elements_hidden = await backend.get_snapshot_with_depth(depth=depth)
        return ComSnapshotResult(
            snapshot=str(snapshot),
            depth_shown=depth,
            max_depth_found=max_depth_found or None,
            elements_hidden=elements_hidden or None,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            openWorldHint=False,
        ),
        description=(
            "Execute COM operations on SAP GUI elements (desktop backend only). "
            "This is the general-purpose escape hatch — use it when no specific tool exists.\n\n"
            "**Workflow:** Call `sap_com_snapshot` to see element IDs, then use this tool.\n\n"
            "**Actions:**\n"
            "- `get`: Read a property (args not needed)\n"
            '- `set`: Write a property (args = single-element list with value, e.g. `["hello"]`)\n'
            '- `call`: Call a method (args = positional arguments, e.g. `[0, "COL"]`)\n\n'
            "**Element IDs:** copy the `id=...` suffix emitted on each line of "
            "`sap_com_snapshot` verbatim — do NOT hand-construct paths from the "
            "indented tree. The snapshot strips the absolute `/app/con[N]/ses[N]/` "
            "prefix for you so the value is drop-in. Interactive fields, shells, "
            "dock shells, buttons, the main window, the OkCode field and the status "
            "bar all carry an `id=`. Pure containers (user area, scroll container, "
            "...) omit it to keep the snapshot compact.\n\n"
            "Docked controls (trees, ALV grids, editors) live at varying paths like "
            "`wnd[0]/shellcont/shell`, `wnd[0]/usr/shellcont/shell`, or "
            "`wnd[0]/usr/cntlNAME/shellcont/shell` depending on how the dynpro "
            "embeds them — do not guess, copy the `id=...` from the snapshot.\n\n"
            "**FindByName** (for BDT screens like BP where fields aren't in the snapshot):\n"
            "Use `find_by_name` with the SAP **internal field name** and type — "
            "that's the technical name (e.g. `BUT000-NAME_LAST`), NOT the visible "
            "label text (e.g. 'Last Name'). Passing a visible label produces "
            "`Error 620: control not found by name`.\n"
            "Set `element_id` to the container (usually `wnd[0]/usr`).\n"
            'Example: `{"element_id": "wnd[0]/usr", "find_by_name": '
            '{"name": "BUT000-NAME_LAST", "type_name": "GuiTextField"}, '
            '"action": "set", "property_or_method": "Text", "args": ["Smith"]}`\n\n'
            "**Chained properties:** Use dot notation (e.g. `Children.Count`, `Children.Item`). "
            "`Parent` is blocked for safety.\n\n"
            "**VKey codes** for SendVKey: 0=Enter, 2=F2, 3=F3/Back, 5=F5, 7=F7/Display, "
            "8=F8/Execute, 11=F11/Save, 12=F12/Cancel.\n\n"
            "**Batch:** Operations run sequentially. If op N fails, ops 1..N-1 already took effect. "
            "Check each operation's `success` field.\n\n"
            "**Example** (fill field + press Enter):\n"
            "```json\n"
            '{"operations": [\n'
            '  {"element_id": "wnd[0]/usr/txtRS38M-PROGRAMM",\n'
            '   "action": "set", "property_or_method": "Text",\n'
            '   "args": ["ZTEST"]},\n'
            '  {"element_id": "wnd[0]",\n'
            '   "action": "call", "property_or_method": "SendVKey",\n'
            '   "args": [0]}\n'
            "]}\n"
            "```\n\n"
            "**Results:** Each operation returns a JSON-encoded `result` field. "
            'Strings appear as `"hello"`, numbers as `42`, null as `null`. '
            "`set` reads back the value after writing.\n\n"
            "Prefer SAP-specific tools (sap_se16_query, sap_se37_lookup, etc.) when available."
        ),
    )
    async def sap_com_evaluate(
        operations: list[ComOperationInput],
        session: str | None = None,
        agent_id: str | None = None,
    ) -> ComEvaluateResult:
        """
        Execute one or more COM operations on SAP GUI elements.

        Operations execute sequentially on the COM thread. If operation N fails,
        operations 1..N-1 have already been applied (side effects persist).
        Each operation in the response has its own ``success`` flag.

        Args:
            operations: List of operations to execute sequentially.
                Each operation has: element_id, action (get/set/call),
                property_or_method, and optional args.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            ComEvaluateResult with per-operation results. Top-level success=True
            even if individual operations failed — check each operation's success.
        """
        if not operations:
            return ComEvaluateResult.failure("No operations provided")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_com_evaluate")
        except ValueError as e:
            return ComEvaluateResult.failure(f"Session error: {e}")

        if not backend.backend_type == "desktop":
            return ComEvaluateResult.failure(
                "sap_com_evaluate is only available on the desktop backend. " + "Use browser_evaluate for WebGUI."
            )

        from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        assert isinstance(backend, DesktopBackend)  # noqa: S101
        desktop_session = backend.require_session()
        com = backend.com

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
