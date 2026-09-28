"""Tests for sandboxed output_file handling in MCP tools."""

import asyncio
import errno
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from sapguimcp.models import SE16FileSummary, SE16Result, SE16Row
from sapguimcp.models.se09_models import TransportListResult, TransportRequest
from sapguimcp.models.sm30_models import SM30Row, SM30ViewResult
from sapguimcp.tools.se09_tools import register_se09_tools
from sapguimcp.tools.se16_tools import register_se16_tools
from sapguimcp.tools.sm30_tools import register_sm30_tools
from sapguimcp.utils import resolve_output_file_path, write_json_output_file


def _tool_fn(mcp: FastMCP, tool_name: str):
    return mcp._local_provider._components[f"tool:{tool_name}@"].fn


def _se16_result() -> SE16Result:
    return SE16Result(
        table="T000",
        total_hits=1,
        returned_rows=1,
        truncated=False,
        columns=["MANDT"],
        rows=[SE16Row(data={"MANDT": "100"})],
        retrieved_at=datetime.now(UTC),
    )


def _sm30_result() -> SM30ViewResult:
    return SM30ViewResult(
        view_name="V_T005",
        description="Countries",
        view_type="flat",
        columns=["LAND1"],
        rows=[SM30Row(values={"LAND1": "DE"})],
        row_count=1,
        retrieved_at=datetime.now(UTC),
    )


def _se09_result() -> TransportListResult:
    return TransportListResult(
        requests=[TransportRequest(request_number="DEVK900100")],
        request_count=1,
        retrieved_at=datetime.now(UTC),
    )


def test_resolve_output_file_path_rejects_parent_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="working directory"):
        resolve_output_file_path("../escape.json")


def test_write_json_output_file_rejects_symlinked_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    real_dir = tmp_path / "real"
    link_path = tmp_path / "linked"
    real_dir.mkdir()

    try:
        link_path.symlink_to(real_dir, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(ValueError, match="symlinks"):
        write_json_output_file("linked/result.json", {"ok": True})


def test_resolve_output_file_path_uses_configured_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When OUTPUT_DIR is set, it sandboxes writes instead of the process cwd.

    Without this, an MCP client's server process cwd is usually unrelated to
    the user's project, so absolute output_file paths into that project would
    be rejected (issue #887).
    """
    configured_dir = tmp_path / "configured"
    configured_dir.mkdir()
    monkeypatch.chdir(tmp_path)  # cwd is deliberately a different directory
    monkeypatch.setenv("OUTPUT_DIR", str(configured_dir))

    resolved = resolve_output_file_path("result.json")

    assert resolved == configured_dir / "result.json"


def test_resolve_output_file_path_defaults_to_cwd_when_output_dir_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)

    resolved = resolve_output_file_path("result.json")

    assert resolved == tmp_path / "result.json"


def test_write_json_output_file_rejects_dangling_symlinked_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dangling symlink's target doesn't exist, so ``Path.exists()`` (which follows
    the link) reports False -- ``is_symlink()`` must be checked on its own, or this
    component slips past the check and ``mkdir(parents=True)`` follows it outside
    the sandbox."""
    monkeypatch.chdir(tmp_path)
    link_path = tmp_path / "dangling"

    try:
        link_path.symlink_to(tmp_path / "does-not-exist", target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    assert not link_path.exists()  # dangling: exists() follows the link and finds nothing
    assert link_path.is_symlink()

    with pytest.raises(ValueError, match="symlinks"):
        write_json_output_file("dangling/result.json", {"ok": True})


@pytest.mark.skipif(
    sys.platform == "win32" or not getattr(os, "supports_dir_fd", set()),
    reason="the O_NOFOLLOW/O_DIRECTORY path only runs where dir_fd is supported",
)
def test_write_json_output_file_preserves_non_symlink_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A permission error opening a parent directory must surface as-is, not get
    reported as "must not traverse symlinks" -- that message is reserved for the
    specific ELOOP case (a real symlink under O_NOFOLLOW)."""
    monkeypatch.chdir(tmp_path)
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir(mode=0o000)

    try:
        with pytest.raises(OSError, match="Permission denied") as exc_info:
            write_json_output_file("blocked/result.json", {"ok": True})
        assert exc_info.value.errno != errno.ELOOP
        assert not isinstance(exc_info.value, ValueError)
    finally:
        blocked_dir.chmod(0o755)


def test_se16_query_preserves_result_when_output_write_fails_with_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``write_json_output_file`` can raise plain ``OSError`` (disk full, permission
    denied, ...), not just ``ValueError`` -- the tool must still return the
    successful lookup's data with success=False rather than crash (issue #895)."""
    monkeypatch.chdir(tmp_path)

    mcp = FastMCP("test")
    register_se16_tools(mcp)
    tool_fn = _tool_fn(mcp, "sap_se16_query")

    with (
        patch(
            "sapguimcp.tools.se16_tools.get_backend",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
        patch(
            "sapguimcp.tools.se16_tools._execute_se16_query",
            new_callable=AsyncMock,
            return_value=_se16_result(),
        ),
        patch(
            "sapguimcp.tools.se16_tools.write_json_output_file",
            side_effect=OSError("disk full"),
        ),
    ):
        result = asyncio.run(
            tool_fn(
                ctx=MagicMock(),
                table="T000",
                filters=None,
                max_hits=100,
                output_file="se16.json",
                session=None,
                agent_id=None,
            )
        )

    assert result.success is False
    assert result.error == "disk full"
    assert result.table == "T000"
    assert result.rows[0].data == {"MANDT": "100"}


def test_se16_query_writes_output_within_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    output_file = "nested/se16_result.json"

    mcp = FastMCP("test")
    register_se16_tools(mcp)
    tool_fn = _tool_fn(mcp, "sap_se16_query")

    with (
        patch(
            "sapguimcp.tools.se16_tools.get_backend",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
        patch(
            "sapguimcp.tools.se16_tools._execute_se16_query",
            new_callable=AsyncMock,
            return_value=_se16_result(),
        ),
    ):
        result = asyncio.run(
            tool_fn(
                ctx=MagicMock(),
                table="T000",
                filters=None,
                max_hits=100,
                output_file=output_file,
                session=None,
                agent_id=None,
            )
        )

    assert isinstance(result, SE16FileSummary)
    assert result.success is True
    written_path = tmp_path / output_file
    assert Path(result.output_file) == written_path
    assert written_path.exists()
    assert json.loads(written_path.read_text(encoding="utf-8"))["table"] == "T000"


def test_sm30_lookup_rejects_output_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    mcp = FastMCP("test")
    register_sm30_tools(mcp)
    tool_fn = _tool_fn(mcp, "sap_sm30_lookup")
    mock_get_backend = AsyncMock()

    with patch("sapguimcp.tools.sm30_tools.get_backend", mock_get_backend):
        result = asyncio.run(
            tool_fn(
                view_name="V_T005",
                output_file="../escape.json",
                session=None,
                agent_id=None,
            )
        )

    assert result.success is False
    assert "working directory" in result.error
    mock_get_backend.assert_not_called()


def test_se09_lookup_rejects_absolute_output_path_outside_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent / "escape.json"

    mcp = FastMCP("test")
    register_se09_tools(mcp)
    tool_fn = _tool_fn(mcp, "sap_se09_lookup")
    mock_get_backend = AsyncMock()

    with patch("sapguimcp.tools.se09_tools.get_backend", mock_get_backend):
        result = asyncio.run(
            tool_fn(
                username=None,
                request_type="all",
                status="modifiable",
                include_objects=False,
                output_file=str(outside_path),
                session=None,
                agent_id=None,
            )
        )

    assert result.success is False
    assert "working directory" in result.error
    mock_get_backend.assert_not_called()


def test_se16_query_preserves_result_when_output_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    mcp = FastMCP("test")
    register_se16_tools(mcp)
    tool_fn = _tool_fn(mcp, "sap_se16_query")

    with (
        patch(
            "sapguimcp.tools.se16_tools.get_backend",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
        patch(
            "sapguimcp.tools.se16_tools._execute_se16_query",
            new_callable=AsyncMock,
            return_value=_se16_result(),
        ),
        patch(
            "sapguimcp.tools.se16_tools.write_json_output_file",
            side_effect=ValueError("write blocked"),
        ),
    ):
        result = asyncio.run(
            tool_fn(
                ctx=MagicMock(),
                table="T000",
                filters=None,
                max_hits=100,
                output_file="se16.json",
                session=None,
                agent_id=None,
            )
        )

    assert result.success is False
    assert result.error == "write blocked"
    assert result.table == "T000"
    assert result.returned_rows == 1
    assert result.rows[0].data == {"MANDT": "100"}
