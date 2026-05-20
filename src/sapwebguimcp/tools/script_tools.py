"""Sandboxed Python script execution tool for SAP GUI desktop backend.

Threat model
------------
Defends against accidental LLM mistakes (``import os``, ``open()``, etc.) by
replacing ``__builtins__`` with a hand-curated allowlist.

Does NOT defend against deliberate MRO traversal (``"".__class__.__mro__``).
This is an accepted trade-off for a semi-trusted LLM in an internal developer
tool. If the threat model hardens, swap ``exec()`` for RestrictedPython.
"""

import json
import logging
import traceback as _traceback
from typing import Any

from fastmcp import FastMCP

from sapwebguimcp.backend.desktop.models.script_results import SapRunScriptResult
from sapwebguimcp.backend.manager import get_backend

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


def _run_in_sandbox(script: str, session: Any) -> SapRunScriptResult:
    """Execute *script* in a restricted namespace on the calling thread.

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
        exec(compile(script, "<sap_script>", "exec"), restricted_globals)  # noqa: S102
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
    # TODO: implement in Task 3 — will use Annotated, Field, ToolAnnotations
    pass
