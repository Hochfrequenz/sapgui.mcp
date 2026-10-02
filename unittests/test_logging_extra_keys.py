"""Guard against ``extra`` keys that collide with ``logging.LogRecord`` attributes.

``logging`` raises ``KeyError("Attempt to overwrite ... in LogRecord")`` when an ``extra`` dict
contains a reserved key such as ``message`` or ``name``. That happens only when the record is
actually emitted, so the bug hides at INFO level and surfaces in error paths or with DEBUG
logging enabled.
"""

import ast
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.tools import se11_tools

_SRC = Path(__file__).resolve().parents[1] / "src" / "sapguimcp"
_RESERVED = set(logging.LogRecord("n", logging.INFO, "p", 0, "m", (), None).__dict__) | {"message", "asctime"}


def _reserved_extra_keys() -> list[str]:
    hits: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "extra" or not isinstance(kw.value, ast.Dict):
                    continue
                for key in kw.value.keys:
                    if isinstance(key, ast.Constant) and key.value in _RESERVED:
                        hits.append(f"{path.relative_to(_SRC.parent)}:{node.lineno} extra key {key.value!r}")
    return hits


def test_no_log_extra_key_collides_with_logrecord_attributes() -> None:
    assert _reserved_extra_keys() == []


@pytest.mark.anyio
async def test_se11_desktop_batch_reports_lookup_errors_instead_of_raising() -> None:
    """A failing desktop SE11 lookup ends up in ``errors``; logging it must not raise (KeyError on 'name')."""
    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=MagicMock(success=True))
    backend.wait_for_ready = AsyncMock()
    with patch.object(se11_tools, "_lookup_se11_desktop", AsyncMock(side_effect=RuntimeError("boom"))):
        result = await se11_tools._lookup_batch_se11_desktop(backend, ["T000"], "table")
    assert result.success is False
    assert len(result.errors) == 1
    assert "boom" in result.errors[0].error
