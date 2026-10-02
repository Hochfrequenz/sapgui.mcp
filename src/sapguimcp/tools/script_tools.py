"""Sandboxed Python script execution tool for SAP GUI desktop backend.

Threat model
------------
Defends against accidental LLM mistakes (``import os``, ``open()``, etc.) by
replacing ``__builtins__`` with a hand-curated allowlist.

Does NOT defend against deliberate MRO traversal (``"".__class__.__mro__``).
This is an accepted trade-off for a semi-trusted LLM in an internal developer
tool. If the threat model hardens, swap ``exec()`` for RestrictedPython.

File script execution (``script_path``):
- Only scripts under explicitly configured root directories (``SCRIPT_ROOTS``
  setting) may be executed; by default the feature is disabled (no roots
  configured). Relative paths are resolved against the roots in order (never
  the process cwd); the first root containing an existing file wins.
- Paths are canonicalized via ``Path.resolve()`` and checked for containment
  (see ``sapguimcp.utils.is_path_within_root``; case-insensitive on Windows)
  to prevent directory traversal (``..``) and symlink/junction escapes.
- Files larger than ``MAX_SCRIPT_BYTES`` (1 MiB) are refused.
- ``params`` is only accepted together with ``script_path``.
- A race between the containment check and the file read (TOCTOU, e.g. a link
  swapped in between) is out of the threat model, like the rest of the sandbox.
- Only ``.py`` files are accepted (checked for both source path and resolved
  target).
- UNC paths (``\\\\`` or ``//``) and Windows device paths / reserved names are
  explicitly rejected.
- Optional ``expected_sha256`` checks the file's SHA-256 digest before anything
  runs or reaches the COM thread.
- Sandboxed execution is identical for both file scripts and inline scripts
  (same ``SAFE_BUILTINS``, no ``import``, same ``session`` / ``output()``
  contract).
"""

import ast
import asyncio
import hashlib
import json
import logging
import math
import ntpath
import os
import sys
import traceback as _traceback
import types
from datetime import timedelta
from pathlib import Path, PureWindowsPath
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from sapguimcp.backend.desktop.models.script_results import SapRunScriptResult
from sapguimcp.backend.manager import get_backend
from sapguimcp.models.config import get_settings
from sapguimcp.utils import resolve_candidates_within_roots

logger = logging.getLogger(__name__)

MAX_SCRIPT_BYTES = 1024 * 1024
"""Maximum accepted size of a script file read via ``script_path`` (1 MiB)."""

__all__ = ["get_configured_script_roots", "register_script_tools"]


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


def get_configured_script_roots() -> list[Path]:
    """Return configured allowed root directories for script_path execution.

    Roots come from the ``SCRIPT_ROOTS`` setting, separated by ``os.pathsep``.
    Returns an empty list if none are configured (feature disabled).
    """
    raw = get_settings().script_roots
    roots: list[Path] = []
    for raw_part in raw.split(os.pathsep):
        part = raw_part.strip().strip("\"'")
        if part:
            roots.append(Path(part))
    return roots


def _is_reserved_name(path: str) -> bool:
    """Whether *path* contains a Windows reserved device name (``CON``, ``NUL``, ...).

    Checked on every platform: such paths are never legitimate script names.
    ``Path.is_reserved()`` is deprecated since 3.13, so use ``ntpath.isreserved``
    (3.13+, available on all platforms) and fall back to ``PureWindowsPath``.
    """
    isreserved = getattr(ntpath, "isreserved", None)
    if isreserved is not None:
        return bool(isreserved(path))
    return PureWindowsPath(path).is_reserved()


def _resolve_and_validate_script_path(script_path: str, configured_roots: list[Path]) -> Path:
    """Validate and resolve a script file path within configured roots.

    Absolute paths must lie inside a root. Relative paths are resolved against
    the roots in order (never the process cwd); the first root containing an
    existing file wins.

    Raises:
        ValueError: If script_path is invalid, outside allowed roots, not a .py file,
            or not found on disk.
    """
    if not configured_roots:
        raise ValueError(
            "script_path is disabled: no script roots configured. "
            "Set SCRIPT_ROOTS to allow script execution from specific directories."
        )

    if not script_path or not script_path.strip():
        raise ValueError("script_path cannot be empty")

    if "\0" in script_path:
        raise ValueError("Invalid script_path: embedded null byte")

    if script_path.startswith(("\\\\", "//")):
        raise ValueError(f"UNC paths are not allowed: {script_path}")

    if sys.platform == "win32" and ":" in os.path.splitdrive(script_path)[1]:
        raise ValueError(f"Alternate data streams are not allowed: {script_path}")

    candidate = Path(script_path)
    if candidate.suffix.lower() != ".py":
        raise ValueError(f"script_path must have a .py extension: {script_path}")

    if _is_reserved_name(script_path):
        raise ValueError(f"Device paths and reserved names are not allowed: {script_path}")

    located = resolve_candidates_within_roots(candidate, configured_roots)
    if not located:
        configured_str = ", ".join(str(r.resolve()) for r in configured_roots)
        raise ValueError(
            f"script_path {script_path!r} is not within any configured script root. Configured roots: {configured_str}"
        )

    target = next((c for c in located if c.is_file()), None)
    if target is None:
        if any(c.is_dir() for c in located):
            raise ValueError(f"script_path is a directory, not a file: {script_path}")
        raise ValueError(f"Script file not found: {script_path}")

    if target.suffix.lower() != ".py":
        raise ValueError(f"script_path target must have a .py extension: {script_path}")

    return target


def _value_to_ast(value: Any) -> ast.expr:
    """Build an AST expression for a JSON-like value (no repr/parse round trip)."""
    if value is None or isinstance(value, (bool, int, str)):
        return ast.Constant(value=value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite float is not allowed in params: {value!r}")
        return ast.Constant(value=value)
    if isinstance(value, list):
        return ast.List(elts=[_value_to_ast(v) for v in value], ctx=ast.Load())
    if isinstance(value, dict):
        keys: list[ast.expr | None] = []
        for k in value:
            if not isinstance(k, str):
                raise ValueError(f"params dict keys must be strings, got {type(k).__name__}")
            keys.append(ast.Constant(value=k))
        return ast.Dict(keys=keys, values=[_value_to_ast(v) for v in value.values()])
    raise ValueError(f"Unsupported params value type: {type(value).__name__}")


def _merge_params(tree: ast.Module, params: dict[str, Any]) -> None:
    """Merge parameter overrides into top-level PARAMS dict in the script AST.

    Only JSON-like values (None, bool, int, finite float, str, list, dict with
    str keys) are accepted.

    Raises:
        ValueError: If params contains unknown keys or non-JSON-like, non-finite
            or too deeply nested values, if top-level PARAMS is missing, or if
            PARAMS is not a dict literal.
    """
    if not params:
        return

    params_stmts: list[tuple[ast.Assign | ast.AnnAssign, ast.Dict]] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "PARAMS" for target in stmt.targets):
                if not isinstance(stmt.value, ast.Dict):
                    raise ValueError("Top-level 'PARAMS' must be a dict literal")
                params_stmts.append((stmt, stmt.value))
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == "PARAMS":
            if stmt.value is None or not isinstance(stmt.value, ast.Dict):
                raise ValueError("Top-level 'PARAMS' must be a dict literal")
            params_stmts.append((stmt, stmt.value))

    if not params_stmts:
        raise ValueError(
            f"Script does not define a top-level 'PARAMS' dict, but params were provided: "
            f"{', '.join(repr(k) for k in sorted(params.keys()))}"
        )

    if len(params_stmts) > 1:
        raise ValueError("Multiple top-level 'PARAMS' assignments found in script")

    _, dict_node = params_stmts[0]
    key_indices: dict[str, int] = {}
    for i, key_expr in enumerate(dict_node.keys):
        if isinstance(key_expr, ast.Constant) and isinstance(key_expr.value, str):
            key_indices[key_expr.value] = i

    unknown_keys = sorted(set(params.keys()) - set(key_indices.keys()))
    if unknown_keys:
        valid_keys = ", ".join(repr(k) for k in sorted(key_indices.keys()))
        unknown_str = ", ".join(repr(k) for k in unknown_keys)
        raise ValueError(f"Unknown params: {unknown_str}. Valid keys are: {valid_keys}")

    for param_key, param_val in params.items():
        idx = key_indices[param_key]
        try:
            dict_node.values[idx] = _value_to_ast(param_val)
        except RecursionError as exc:
            raise ValueError(f"params value for {param_key!r} is nested too deeply") from exc

    ast.fix_missing_locations(tree)


def _run_in_sandbox(
    code: types.CodeType,
    session: Any,
    script_path: str | None = None,
    script_sha256: str | None = None,
) -> SapRunScriptResult:
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
        "__builtins__": dict(SAFE_BUILTINS),
        "session": session,
        "output": _output,
    }

    try:
        exec(code, restricted_globals)  # noqa: S102  # pylint: disable=exec-used
        if not collected:
            logger.debug("sap_run_script: script completed with no output")
        return SapRunScriptResult(
            output=collected,
            script_path=script_path,
            script_sha256=script_sha256,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return SapRunScriptResult.failure(
            error=f"{type(exc).__name__}: {exc}",
            output=collected,
            error_traceback=_traceback.format_exc(),
            script_path=script_path,
            script_sha256=script_sha256,
        )


def register_script_tools(mcp: FastMCP) -> None:
    """Register sap_run_script with the MCP server (desktop backend only)."""

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            open_world_hint=False,
        ),
        description=(
            "Execute a Python script against the live SAP GUI session (desktop backend only).\n\n"
            "Provide either ``script`` (inline Python source) or ``script_path`` (path to a ``.py`` "
            "file on the MCP host), but not both.\n\n"
            "**Prefer ``script_path`` for shipped, tested, versioned scripts.** Using ``script_path`` "
            "avoids wasting model context and tokens reading and re-emitting script text, prevents model "
            "truncation or unauthorized rewriting, and allows verifying script integrity with "
            "``expected_sha256``. Parameters can be passed via ``params`` to override defaults in the "
            "script's top-level ``PARAMS`` dict (``params`` is rejected with inline ``script``). "
            "``script_path`` only works for files under the directories configured in the "
            "``SCRIPT_ROOTS`` setting; relative paths are resolved against those roots in order "
            "(first matching root wins). Script files are limited to 1 MiB.\n\n"
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
            "**Concurrency note:** All sessions of one SAP GUI connection share a single-threaded "
            "COM scripting engine. Parallel `sap_run_script` loops on that same connection are "
            "serialized (no speedup). For bulk work on one connection, prefer one script with a "
            "larger loop. Parallelism helps only across genuinely separate connections.\n\n"
            "If the script raises an unhandled exception, ``success=False`` and ``output`` contains "
            "whatever was collected before the error — partial results are preserved.\n"
            "**On failure:** inspect ``error`` (exception type + message) and ``error_traceback`` "
            "to understand what went wrong. For ad-hoc inline scripts, fix the script and retry, "
            "or fall back to ``sap_com_evaluate`` for individual operations. (For shipped scripts "
            "executed via ``script_path``, do not rewrite the script; adjust ``params`` or report the "
            "failure.) If the error mentions an element ID that was not found, call ``sap_com_snapshot`` "
            "first to verify the correct ID.\n\n"
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
    async def sap_run_script(  # pylint: disable=too-many-return-statements,too-many-arguments,too-many-locals
        script: Annotated[
            str | None,
            Field(description="Python script body to execute (mutually exclusive with script_path)"),
        ] = None,
        script_path: Annotated[
            str | None,
            Field(
                description=(
                    "Path to a .py script file on the MCP host (mutually exclusive with script). "
                    "Must reside within a configured script root (SCRIPT_ROOTS). Relative paths are "
                    "resolved against the configured roots in order (never the server's working "
                    "directory); the first root containing the file wins."
                )
            ),
        ] = None,
        params: Annotated[
            dict[str, Any] | None,
            Field(
                description=(
                    "Parameter overrides merged into the script's top-level PARAMS dict. "
                    "All keys must exist in the script's PARAMS definition. Only valid with script_path "
                    "(rejected for inline script). Values must be JSON-like and finite."
                )
            ),
        ] = None,
        expected_sha256: Annotated[
            str | None,
            Field(
                description=(
                    "Optional SHA-256 hex digest of the script file. "
                    "Execution is refused if the file's hash does not match."
                )
            ),
        ] = None,
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
        target_file: Path | None = None
        script_sha256: str | None = None

        def _fail(message: str) -> SapRunScriptResult:
            """Failure result carrying the script file identity known so far."""
            return SapRunScriptResult.failure(
                message,
                script_path=str(target_file) if target_file else None,
                script_sha256=script_sha256,
            )

        if script is None and script_path is None:
            return _fail("Exactly one of 'script' or 'script_path' must be provided.")

        if script is not None and script_path is not None:
            return _fail("Cannot specify both 'script' and 'script_path'.")

        source_code: str
        if script_path is not None:
            roots = get_configured_script_roots()
            try:
                target_file = _resolve_and_validate_script_path(script_path, roots)
            except ValueError as exc:
                return _fail(str(exc))

            try:
                with target_file.open("rb") as fh:
                    raw_bytes = fh.read(MAX_SCRIPT_BYTES + 1)
            except OSError as exc:
                return _fail(f"Failed to read script file {script_path!r}: {exc}")

            if len(raw_bytes) > MAX_SCRIPT_BYTES:
                return _fail(f"Script file {script_path!r} exceeds the maximum size of {MAX_SCRIPT_BYTES} bytes")

            script_sha256 = hashlib.sha256(raw_bytes).hexdigest()

            if expected_sha256 is not None and script_sha256.lower() != expected_sha256.strip().lower():
                exp = expected_sha256.strip().lower()
                return _fail(f"SHA-256 mismatch for {script_path}: expected {exp}, got {script_sha256}")

            try:
                source_code = raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                return _fail(f"Failed to decode script file {script_path!r} as UTF-8: {exc}")

            source_name = str(target_file)
        elif script is not None:
            if expected_sha256 is not None:
                return _fail("'expected_sha256' is only valid with 'script_path'")
            if params is not None:
                return _fail("'params' is only valid with 'script_path'")
            source_name = "<sap_script>"
            source_code = script
        else:  # pragma: no cover - guarded by the checks above
            return _fail("Exactly one of 'script' or 'script_path' must be provided.")

        try:
            tree = ast.parse(source_code, filename=source_name)
        except (SyntaxError, ValueError, RecursionError) as exc:
            return _fail(f"{type(exc).__name__}: {exc}")

        if params is not None:
            try:
                _merge_params(tree, params)
            except ValueError as exc:
                return _fail(str(exc))

        try:
            code = compile(tree, source_name, "exec")
        except (SyntaxError, ValueError, RecursionError) as exc:
            return _fail(f"{type(exc).__name__}: {exc}")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_run_script")
        except ValueError as exc:
            return _fail(str(exc))

        if backend.backend_type != "desktop":
            return _fail("sap_run_script is only available on the desktop backend. Use browser_evaluate for WebGUI.")

        from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        if not isinstance(backend, DesktopBackend):
            return _fail("Internal error: expected DesktopBackend")

        desktop_session = backend.require_session()
        com = backend.com
        timeout_td = timedelta(seconds=timeout)
        current_script_path = str(target_file) if target_file else None

        try:
            return await asyncio.wait_for(
                com.run(
                    lambda: _run_in_sandbox(
                        code,
                        desktop_session,
                        script_path=current_script_path,
                        script_sha256=script_sha256,
                    )
                ),
                timeout=timeout_td.total_seconds(),
            )
        except asyncio.TimeoutError:
            return _fail(
                f"Script timed out after {timeout_td.seconds}s. "
                "The COM thread may still be running — restart the session if SAP is unresponsive."
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("sap_run_script: COM execution error")
            return _fail(f"COM execution error: {exc}")
