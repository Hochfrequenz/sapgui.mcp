"""Sandboxed Python script execution tool for SAP GUI desktop backend.

Threat model
------------
Defends against accidental LLM mistakes (``import os``, ``open()``, etc.) by
replacing ``__builtins__`` with a hand-curated allowlist.

Does NOT defend against deliberate MRO traversal (``"".__class__.__mro__``).
This is an accepted trade-off for a semi-trusted LLM in an internal developer
tool. If the threat model hardens, swap ``exec()`` for RestrictedPython.

File script execution (``script_path``):
- Only scripts under explicitly configured root directories
  (``SAPGUIMCP_SCRIPT_ROOTS`` env var or ``script_roots`` in settings) may be
  executed; by default the feature is disabled (no roots configured).
- Paths are canonicalized via ``Path.resolve()`` and checked with
  ``is_relative_to(root)`` (case-insensitive on Windows) to prevent directory
  traversal (``..``) and symlink escapes.
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

logger = logging.getLogger(__name__)

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


def _is_relative_to(path: Path, root: Path) -> bool:
    """Check if path is relative to root, case-insensitively on Windows."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        if sys.platform == "win32":
            try:
                Path(os.path.normcase(str(path))).relative_to(Path(os.path.normcase(str(root))))
                return True
            except ValueError:
                return False
        elif isinstance(path, PureWindowsPath) or isinstance(root, PureWindowsPath):
            try:
                PureWindowsPath(str(path).lower()).relative_to(PureWindowsPath(str(root).lower()))
                return True
            except ValueError:
                return False
        return False


def get_configured_script_roots() -> list[Path]:
    """Return configured allowed root directories for script_path execution.

    Roots are retrieved from the ``SAPGUIMCP_SCRIPT_ROOTS`` environment variable
    or the ``script_roots`` setting. Multiple directories are separated by
    ``os.pathsep``. Returns an empty list if no roots are configured (feature disabled).
    """
    raw = os.environ.get("SAPGUIMCP_SCRIPT_ROOTS")
    if not raw:
        try:
            from sapguimcp.models.config import get_settings

            raw = get_settings().script_roots
        except Exception:  # pylint: disable=broad-exception-caught
            raw = ""
    if not raw or not raw.strip():
        return []

    roots: list[Path] = []
    for raw_part in raw.split(os.pathsep):
        part = raw_part.strip().strip("\"'")
        if part:
            roots.append(Path(part))
    return roots


def _resolve_and_validate_script_path(script_path: str, configured_roots: list[Path]) -> Path:
    """Validate and resolve a script file path within configured roots.

    Raises:
        ValueError: If script_path is invalid, outside allowed roots, not a .py file,
            or not found on disk.
    """
    if not configured_roots:
        raise ValueError(
            "script_path is disabled: no script roots configured. "
            "Set SAPGUIMCP_SCRIPT_ROOTS to allow script execution from specific directories."
        )

    if not script_path or not script_path.strip():
        raise ValueError("script_path cannot be empty")

    if "\0" in script_path:
        raise ValueError("Invalid script_path: embedded null byte")

    if script_path.startswith(("\\\\", "//")):
        raise ValueError(f"UNC paths are not allowed: {script_path}")

    candidate = Path(script_path)
    if candidate.suffix.lower() != ".py":
        raise ValueError(f"script_path must have a .py extension: {script_path}")

    if candidate.is_reserved() or (hasattr(os.path, "isreserved") and os.path.isreserved(str(candidate))):
        raise ValueError(f"Device paths and reserved names are not allowed: {script_path}")

    resolved_candidates: list[Path] = []
    if candidate.is_absolute():
        resolved = candidate.resolve()
        for root in configured_roots:
            resolved_root = root.resolve()
            if _is_relative_to(resolved, resolved_root):
                resolved_candidates.append(resolved)
                break
    else:
        cwd_resolved = candidate.resolve()
        for root in configured_roots:
            resolved_root = root.resolve()
            if _is_relative_to(cwd_resolved, resolved_root):
                resolved_candidates.append(cwd_resolved)
                break

        for root in configured_roots:
            resolved_root = root.resolve()
            root_candidate = (resolved_root / candidate).resolve()
            if _is_relative_to(root_candidate, resolved_root):
                resolved_candidates.append(root_candidate)

    if not resolved_candidates:
        configured_str = ", ".join(str(r.resolve()) for r in configured_roots)
        raise ValueError(
            f"script_path {script_path!r} is not within any configured script root. Configured roots: {configured_str}"
        )

    target = next((c for c in resolved_candidates if c.is_file()), resolved_candidates[0])
    if target.is_dir():
        raise ValueError(f"script_path is a directory, not a file: {script_path}")
    if not target.is_file():
        raise ValueError(f"Script file not found: {script_path}")

    if target.suffix.lower() != ".py":
        raise ValueError(f"script_path target must have a .py extension: {script_path}")

    return target


def _merge_params(tree: ast.Module, params: dict[str, Any]) -> None:
    """Merge parameter overrides into top-level PARAMS dict in the script AST.

    Raises:
        ValueError: If params contains unknown keys, if top-level PARAMS is
            missing, or if PARAMS is not a dict literal.
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
        val_expr = ast.parse(repr(param_val), mode="eval").body
        dict_node.values[idx] = val_expr

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
            "script's top-level ``PARAMS`` dict.\n\n"
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
                    "Must reside within a configured script root (SAPGUIMCP_SCRIPT_ROOTS)."
                )
            ),
        ] = None,
        params: Annotated[
            dict[str, Any] | None,
            Field(
                description=(
                    "Parameter overrides merged into the script's top-level PARAMS dict. "
                    "All keys must exist in the script's PARAMS definition."
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
        if script is None and script_path is None:
            return SapRunScriptResult.failure("Exactly one of 'script' or 'script_path' must be provided.")

        if script is not None and script_path is not None:
            return SapRunScriptResult.failure("Cannot specify both 'script' and 'script_path'.")

        target_file: Path | None = None
        script_sha256: str | None = None

        if script_path is not None:
            roots = get_configured_script_roots()
            try:
                target_file = _resolve_and_validate_script_path(script_path, roots)
            except ValueError as exc:
                return SapRunScriptResult.failure(str(exc))

            try:
                raw_bytes = target_file.read_bytes()
            except (OSError, PermissionError) as exc:
                return SapRunScriptResult.failure(
                    f"Failed to read script file {script_path!r}: {exc}",
                    script_path=str(target_file),
                )

            script_sha256 = hashlib.sha256(raw_bytes).hexdigest()

            if expected_sha256 is not None and script_sha256.lower() != expected_sha256.strip().lower():
                exp = expected_sha256.strip().lower()
                return SapRunScriptResult.failure(
                    f"SHA-256 mismatch for {script_path}: expected {exp}, got {script_sha256}",
                    script_path=str(target_file),
                    script_sha256=script_sha256,
                )

            try:
                script_content = raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                return SapRunScriptResult.failure(
                    f"Failed to decode script file {script_path!r} as UTF-8: {exc}",
                    script_path=str(target_file),
                    script_sha256=script_sha256,
                )

            source_name = str(target_file)
            source_code = script_content
        else:
            if expected_sha256 is not None:
                return SapRunScriptResult.failure("'expected_sha256' is only valid with 'script_path'")
            source_name = "<sap_script>"
            source_code = script  # type: ignore[assignment]

        try:
            tree = ast.parse(source_code, filename=source_name)
        except (SyntaxError, ValueError) as exc:
            return SapRunScriptResult.failure(
                f"{type(exc).__name__}: {exc}",
                script_path=str(target_file) if target_file else None,
                script_sha256=script_sha256,
            )

        if params is not None:
            try:
                _merge_params(tree, params)
            except ValueError as exc:
                return SapRunScriptResult.failure(
                    str(exc),
                    script_path=str(target_file) if target_file else None,
                    script_sha256=script_sha256,
                )

        try:
            code = compile(tree, source_name, "exec")
        except (SyntaxError, ValueError) as exc:
            return SapRunScriptResult.failure(
                f"{type(exc).__name__}: {exc}",
                script_path=str(target_file) if target_file else None,
                script_sha256=script_sha256,
            )

        current_script_path = str(target_file) if target_file else None

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_run_script")
        except ValueError as exc:
            return SapRunScriptResult.failure(
                str(exc),
                script_path=current_script_path,
                script_sha256=script_sha256,
            )

        if backend.backend_type != "desktop":
            return SapRunScriptResult.failure(
                "sap_run_script is only available on the desktop backend. Use browser_evaluate for WebGUI.",
                script_path=current_script_path,
                script_sha256=script_sha256,
            )

        from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        if not isinstance(backend, DesktopBackend):
            return SapRunScriptResult.failure(
                "Internal error: expected DesktopBackend",
                script_path=current_script_path,
                script_sha256=script_sha256,
            )

        desktop_session = backend.require_session()
        com = backend.com
        timeout_td = timedelta(seconds=timeout)

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
            return SapRunScriptResult.failure(
                f"Script timed out after {timeout_td.seconds}s. "
                "The COM thread may still be running — restart the session if SAP is unresponsive.",
                script_path=current_script_path,
                script_sha256=script_sha256,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("sap_run_script: COM execution error")
            return SapRunScriptResult.failure(
                f"COM execution error: {exc}",
                script_path=current_script_path,
                script_sha256=script_sha256,
            )
