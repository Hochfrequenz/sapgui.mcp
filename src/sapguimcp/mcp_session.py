"""Protocol-era aware access to the MCP client session behind a fastmcp Context.

MCP 2026-07-28 (SEP-2322, SEP-2575) dropped the handshake and with it the session:
every request is self-contained. fastmcp 4 still offers ``ctx.session_id`` there, but
mints a new one for every request, so anything keyed on it would treat each tool call
as a new client.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from mcp.types.version import MODERN_PROTOCOL_VERSIONS

if TYPE_CHECKING:
    from fastmcp import Context

# This server only runs over stdio, where one process serves exactly one client —
# so on session-less connections a per-process id identifies the client session.
_PROCESS_SESSION_ID = str(uuid.uuid4())


def is_modern_connection(ctx: Context) -> bool:
    """True on a 2026-07-28 connection: no server-initiated requests, no session."""
    request_context = getattr(ctx, "request_context", None)
    return request_context is not None and request_context.protocol_version in MODERN_PROTOCOL_VERSIONS


def get_mcp_session_id(ctx: Context | None) -> str | None:
    """Stable id of the MCP client session behind ``ctx``, for per-session state.

    Handshake-era connections use ``ctx.session_id``. On 2026-07-28 connections that
    changes on every request, which would reset per-session call sequences, lose the
    SAP identity recorded at login, defeat the per-session feedback rate limit and add
    a new entry to the session registry on every tool call — so the per-process id is
    used instead.
    """
    if ctx is None:
        return None
    if is_modern_connection(ctx):
        return _PROCESS_SESSION_ID
    return getattr(ctx, "session_id", None)
