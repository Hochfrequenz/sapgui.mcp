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
import time
import traceback as _traceback
import types
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path, PureWindowsPath
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from sapguimcp.backend.desktop._com_thread import _FATAL_COM_ERROR_HINTS, _get_com_error_code
from sapguimcp.backend.desktop.models.script_results import SandboxContract, SapRunScriptResult
from sapguimcp.backend.manager import get_backend
from sapguimcp.models.config import get_settings
from sapguimcp.utils import resolve_candidates_within_roots

logger = logging.getLogger(__name__)

MAX_SCRIPT_BYTES = 1024 * 1024
"""Maximum accepted size of a script file read via ``script_path`` (1 MiB)."""

__all__ = [
    "MAX_SCRIPT_BYTES",
    "SAFE_BUILTINS",
    "SANDBOX_CONTRACT_VERSION",
    "get_configured_script_roots",
    "get_sandbox_contract",
    "register_script_tools",
]


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
    "TimeoutError": TimeoutError,
    "NotImplementedError": NotImplementedError,
    # True, False, None are Python 3 keywords; they are NOT in this dict and
    # resolve without going through __builtins__.
}

SANDBOX_CONTRACT_VERSION: int = 2
"""Current version of the sap_run_script sandbox contract.

Bump this whenever a builtin (``SAFE_BUILTINS``) or an injected global name is added or removed.
"""


def _build_sandbox_globals(session: Any, output: Callable[[Any], None], deadline: float) -> dict[str, Any]:
    """Build the globals dict for sandboxed scripts. Single source of truth for injected names.

    *deadline* is a ``time.monotonic()`` value bounding ``wait`` / ``wait_until``.
    """

    def wait(ms: float | int) -> None:
        _wait(ms, deadline)

    def wait_until(element_id: str, timeout_ms: float | int, poll_ms: float | int = 200) -> Any:
        return _wait_until(session, element_id, timeout_ms, poll_ms, deadline)

    return {
        "__builtins__": dict(SAFE_BUILTINS),
        "session": session,
        "output": output,
        "wait": wait,
        "wait_until": wait_until,
    }


def get_sandbox_contract() -> SandboxContract:
    """Return the sandbox execution contract for sap_run_script.

    Bump ``SANDBOX_CONTRACT_VERSION`` whenever a builtin or injected name is added or removed.
    """
    injected = sorted(k for k in _build_sandbox_globals(None, lambda _v: None, math.inf) if k != "__builtins__")
    return SandboxContract(
        version=SANDBOX_CONTRACT_VERSION,
        allowed_builtins=sorted(k for k in SAFE_BUILTINS if not k.startswith("_")),
        injected_names=injected,
    )


_CONTRACT = get_sandbox_contract()
_ALLOWED_BUILTINS_SUMMARY = ", ".join(_CONTRACT.allowed_builtins)
_INJECTED_NAMES_SUMMARY = ", ".join(f"``{name}``" for name in _CONTRACT.injected_names)


def get_configured_script_roots() -> list[Path]:
    """Return configured allowed root directories for script_path execution.

    Roots come from the ``SCRIPT_ROOTS`` setting, separated by ``os.pathsep``.
    Returns an empty list if none are configured (feature disabled).

    Roots are admin-trusted configuration and must be absolute paths; relative
    roots (or a bare drive such as ``C:``) would depend on the server's working
    directory and are skipped with a warning. A UNC/network root is allowed if
    the administrator configures one - only UNC/device paths in the caller's
    ``script_path`` are rejected.
    """
    raw = get_settings().script_roots
    roots: list[Path] = []
    for raw_part in raw.split(os.pathsep):
        part = raw_part.strip().strip("\"'")
        if not part:
            continue
        root = Path(part)
        if not root.is_absolute():
            logger.warning("Ignoring SCRIPT_ROOTS entry %r: script roots must be absolute paths", part)
            continue
        roots.append(root)
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
        raise ValueError(f"UNC and device paths are not allowed: {script_path}")

    if sys.platform == "win32" and ":" in os.path.splitdrive(script_path)[1]:
        raise ValueError(f"Alternate data streams are not allowed: {script_path}")

    candidate = Path(script_path)
    if candidate.suffix.lower() != ".py":
        raise ValueError(f"script_path must have a .py extension: {script_path}")

    if _is_reserved_name(script_path):
        raise ValueError(f"Invalid or reserved Windows file name: {script_path}")

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


def _check_duration(name: str, value: Any, *, allow_zero: bool) -> float:
    """Validate a millisecond value: real finite number (not bool), non-negative (or positive)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be a finite number (value is too large or not a number)")
    if allow_zero and value < 0:
        raise ValueError(f"{name} must be non-negative")
    if not allow_zero and value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return float(value)


def _wait(ms: float | int, deadline: float) -> None:
    """Pause script execution for *ms* milliseconds.

    Raises ``TimeoutError`` without sleeping if the pause would run past the
    sandbox *deadline* (a ``time.monotonic()`` value derived from the tool timeout).
    """
    seconds = _check_duration("wait duration", ms, allow_zero=True) / 1000.0
    if time.monotonic() + seconds > deadline:
        raise TimeoutError("wait(...) would exceed the tool timeout")
    time.sleep(seconds)


def _wait_until(
    session: Any,
    element_id: str,
    timeout_ms: float | int,
    poll_ms: float | int = 200,
    deadline: float = math.inf,
) -> Any:
    """Poll for an element by ID until found or until timeout elapses.

    Args:
        session: Live GuiSession object.
        element_id: ID path of the target SAP GUI element.
        timeout_ms: Maximum time to wait in milliseconds.
        poll_ms: Polling interval in milliseconds (default: 200).
        deadline: Sandbox deadline (``time.monotonic()`` value) from the tool timeout.

    Returns:
        The resolved element if found, or None if *timeout_ms* elapses first.

    Raises:
        TimeoutError: if the sandbox *deadline* (the tool ``timeout``) is reached before
            the element is found and before *timeout_ms* elapsed.
        Exception: a fatal COM connection error (see ``_FATAL_COM_ERROR_HINTS``) is re-raised immediately.
    """
    timeout_s = _check_duration("timeout_ms", timeout_ms, allow_zero=True) / 1000.0
    poll_s = _check_duration("poll_ms", poll_ms, allow_zero=False) / 1000.0

    own_deadline = time.monotonic() + timeout_s
    sandbox_binding = deadline < own_deadline
    effective_deadline = min(own_deadline, deadline)
    last_exc: Exception | None = None

    while True:
        try:
            elem = session.find_by_id(element_id, raise_error=False)
            if elem is not None:
                return elem
        except Exception as exc:  # pylint: disable=broad-exception-caught
            code = _get_com_error_code(exc)
            if code is not None and code in _FATAL_COM_ERROR_HINTS:
                raise
            last_exc = exc

        now = time.monotonic()
        if now >= effective_deadline:
            if last_exc is not None:
                logger.debug("wait_until(%r) timed out; last lookup error: %r", element_id, last_exc)
            if sandbox_binding:
                raise TimeoutError(f"wait_until({element_id!r}) hit the tool timeout before the element appeared")
            return None

        time.sleep(min(poll_s, effective_deadline - now))


def _run_in_sandbox(
    code: types.CodeType,
    session: Any,
    script_path: str | None = None,
    script_sha256: str | None = None,
    *,
    deadline: float,
) -> SapRunScriptResult:
    """Execute *code* in a restricted namespace on the calling thread.

    Must be called from the COM thread (inside ``com.run(lambda)``).
    *deadline* is a ``time.monotonic()`` value; ``wait``/``wait_until`` never run past it.
    """
    collected: list[Any] = []

    def _output(value: Any) -> None:
        try:
            json.dumps(value)
            collected.append(value)
        except (TypeError, ValueError):
            collected.append(str(value))

    restricted_globals = _build_sandbox_globals(session, _output, deadline)

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
            "- ``output(value)``: call this to collect results. All values are returned in order.\n"
            "- ``wait(ms)``: pause execution for ``ms`` milliseconds.\n"
            "- ``wait_until(element_id, timeout_ms, poll_ms=200)``: poll for an element by ID "
            "until ``session.find_by_id`` succeeds, returning the element; returns ``None`` if "
            "``timeout_ms`` elapses. Both ``wait`` and ``wait_until`` raise ``TimeoutError`` "
            "(catchable in the script) instead of running past the tool ``timeout``; waits block "
            "the connection's COM thread, so keep them short.\n\n"
            "**Always call ``output()`` at least once** with a summary — a script that never "
            "calls ``output()`` returns an empty list with no indication of what happened.\n\n"
            f"**Sandbox contract (v{SANDBOX_CONTRACT_VERSION}):**\n"
            f"- Allowed builtins: {_ALLOWED_BUILTINS_SUMMARY}\n"
            f"- Injected names: {_INJECTED_NAMES_SUMMARY} (use ``output()`` instead of ``print()`` "
            "and ``wait()`` instead of ``time.sleep()``)\n"
            "- All other builtins (e.g. ``print``, ``ord``, ``divmod``, ``open``, ``eval``) "
            "and ``import`` are blocked.\n"
            "- Full contract discoverable via resource ``sandbox://sap_run_script``.\n\n"
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
            except (OSError, RuntimeError) as exc:
                # e.g. symlink loops or unreadable path components during resolution
                return _fail(f"Cannot resolve script_path {script_path!r}: {exc}")

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

        # Same clock origin as asyncio.wait_for below: the deadline covers queue time too.
        deadline = time.monotonic() + timeout

        try:

            def _run() -> SapRunScriptResult:
                return _run_in_sandbox(
                    code,
                    desktop_session,
                    script_path=current_script_path,
                    script_sha256=script_sha256,
                    deadline=deadline,
                )

            return await asyncio.wait_for(
                com.run(_run),
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
