"""Sandboxed Python script execution tool for SAP GUI desktop backend.

Threat model
------------
Defends against accidental LLM mistakes (``import os``, ``open()``, etc.) by
replacing ``__builtins__`` with a hand-curated allowlist.

Does NOT defend against deliberate MRO traversal (``"".__class__.__mro__``).
This is an accepted trade-off for a semi-trusted LLM in an internal developer
tool. If the threat model hardens, swap ``exec()`` for RestrictedPython.
"""

import asyncio
import json
import logging
import traceback as _traceback
import types
from datetime import timedelta
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from sapguimcp.backend.desktop.models.script_results import SapRunScriptResult
from sapguimcp.backend.manager import get_backend

logger = logging.getLogger(__name__)

__all__ = ["register_script_tools"]


def _blocked_import(*args: Any, **kwargs: Any) -> None:
    """Raise NameError when a script tries to import anything.

    CPython's import opcode looks up ``__import__`` in ``__builtins__`` by key.
    When ``__builtins__`` is a plain dict (not the builtins module), an absent
    ``__import__`` key raises ``ImportError: __import__ not found`` — not the
    more informative ``NameError`` the spec requires.  Providing this stub
    forces the correct error type and message.
    """
    raise NameError("__import__ is not available in sap_run_script scripts")


SAFE_BUILTINS: dict[str, Any] = {
    # Block import with an explicit NameError (see _blocked_import docstring)
    "__import__": _blocked_import,
    # Iteration / sequences
    "range": range,
    "len": len,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "reversed": reversed,
    "list": list,
    "tuple": tuple,
    "dict": dict,
    "set": set,
    # Numeric / string
    "int": int,
    "float": float,
    "bool": bool,
    "str": str,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "sum": sum,
    # Logic
    "any": any,
    "all": all,
    "isinstance": isinstance,
    "getattr": getattr,
    # Exceptions — scripts may raise or catch these
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "TypeError": TypeError,
    "IndexError": IndexError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "NotImplementedError": NotImplementedError,
    # True, False, None are Python 3 keywords; they are NOT in this dict and
    # resolve without going through __builtins__.
}


def _run_in_sandbox(code: types.CodeType, session: Any) -> SapRunScriptResult:
    """Execute *code* in a restricted namespace on the calling thread.

    Must be called from the COM thread (inside ``com.run(lambda)``).
    """
    collected: list[Any] = []

    def _output(value: Any) -> None:
        try:
            json.dumps(value)
            collected.append(value)
        except (TypeError, ValueError):
            collected.append(str(value))

    restricted_globals: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "session": session,
        "output": _output,
    }

    try:
        exec(code, restricted_globals)  # noqa: S102  # pylint: disable=exec-used
        if not collected:
            logger.debug("sap_run_script: script completed with no output")
        return SapRunScriptResult(output=collected)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return SapRunScriptResult.failure(
            error=f"{type(exc).__name__}: {exc}",
            output=collected,
            error_traceback=_traceback.format_exc(),
        )


def register_script_tools(mcp: FastMCP) -> None:
    """Register sap_run_script with the MCP server (desktop backend only)."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            openWorldHint=False,
        ),
        description=(
            "Execute a Python script against the live SAP GUI session (desktop backend only).\n\n"
            "The script receives:\n"
            "- ``session``: sapsucker ``GuiSession`` — use ``session.find_by_id(id)`` to reach "
            "elements, then read/write their properties and call methods directly.\n"
            "- ``output(value)``: call this to collect results. All values are returned in order.\n\n"
            "**Always call ``output()`` at least once** with a summary — a script that never "
            "calls ``output()`` returns an empty list with no indication of what happened.\n\n"
            "``import`` and ``print`` are not available. Use ``output()`` instead of ``print()``.\n\n"
            "Full Python control flow works: ``for``, ``if``/``else``, ``while``, ``try``/``except``, "
            "list comprehensions, function definitions.\n\n"
            "**When to use this tool vs ``sap_com_evaluate``:** prefer ``sap_com_evaluate`` for "
            "fixed-step sequences (known number of operations). Use ``sap_run_script`` when the "
            "number of operations depends on a runtime value (e.g. iterating all rows in a grid, "
            "scanning tree nodes, branching based on a field value read mid-sequence) or when "
            "processing a known list of items with the same repeated operation — bulk creation, "
            "batch updates — where looping inside a single script avoids repeated round-trips and "
            "significantly reduces token cost.\n\n"
            "If the script raises an unhandled exception, ``success=False`` and ``output`` contains "
            "whatever was collected before the error — partial results are preserved.\n"
            "**On failure:** inspect ``error`` (exception type + message) and ``error_traceback`` "
            "to understand what went wrong, then either fix the script and retry, or fall back to "
            "``sap_com_evaluate`` for individual operations. If the error mentions an element ID "
            "that was not found, call ``sap_com_snapshot`` first to verify the correct ID.\n\n"
            "The ``timeout`` parameter (default 30 s) limits how long the tool waits for the script "
            "to finish. If the timeout fires, ``success=False`` is returned immediately; the COM "
            "thread may still be running — restart the session if SAP becomes unresponsive.\n\n"
            "Example:\n"
            "```python\n"
            "grid = session.find_by_id('wnd[0]/usr/cntlGRID/shellcont/shell')\n"
            "errors = [grid.get_cell_value(r, 'VBELN') for r in range(grid.row_count)\n"
            "          if grid.get_cell_value(r, 'STATUS') == 'Error']\n"
            "output({'error_count': len(errors), 'docs': errors})\n"
            "```"
        ),
    )
    async def sap_run_script(  # pylint: disable=too-many-return-statements
        script: Annotated[str, Field(description="Python script body to execute")],
        session: Annotated[str | None, Field(description="Session ID (e.g. 's1'). None = primary.")] = None,
        agent_id: Annotated[str | None, Field(description="Agent identifier for binding check.")] = None,
        timeout: Annotated[
            int,
            Field(
                description="Maximum seconds to wait for the script to complete. Defaults to 30.",
                ge=1,
            ),
        ] = 30,
    ) -> SapRunScriptResult:
        # Compile first — reject invalid Python before touching backend or COM thread.
        try:
            code = compile(script, "<sap_script>", "exec")
        except (SyntaxError, ValueError) as exc:
            return SapRunScriptResult.failure(f"{type(exc).__name__}: {exc}")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_run_script")
        except ValueError as exc:
            return SapRunScriptResult.failure(str(exc))

        if backend.backend_type != "desktop":
            return SapRunScriptResult.failure(
                "sap_run_script is only available on the desktop backend. Use browser_evaluate for WebGUI."
            )

        from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        if not isinstance(backend, DesktopBackend):
            return SapRunScriptResult.failure("Internal error: expected DesktopBackend")

        desktop_session = backend.require_session()
        com = backend.com
        timeout_td = timedelta(seconds=timeout)

        try:
            return await asyncio.wait_for(
                com.run(lambda: _run_in_sandbox(code, desktop_session)),
                timeout=timeout_td.total_seconds(),
            )
        except asyncio.TimeoutError:
            return SapRunScriptResult.failure(
                f"Script timed out after {timeout_td.seconds}s. "
                "The COM thread may still be running — restart the session if SAP is unresponsive."
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("sap_run_script: COM execution error")
            return SapRunScriptResult.failure(f"COM execution error: {exc}")
