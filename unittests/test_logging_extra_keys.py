"""Guard against ``extra`` keys that collide with ``logging.LogRecord`` attributes.

``logging`` raises ``KeyError("Attempt to overwrite ... in LogRecord")`` when an ``extra`` dict
contains a reserved key such as ``message`` or ``name``. That happens only when the record is
actually emitted, so the bug hides at INFO level and surfaces in error paths or with DEBUG
logging enabled.

Only literal ``extra={...}`` and ``extra=dict(...)`` arguments are checked; an ``extra`` passed as
a variable or built by another call is not.
"""

import ast
import logging
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "sapguimcp"


_RESERVED = set(logging.LogRecord("n", logging.INFO, "p", 0, "m", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def _reserved_extra_keys() -> list[str]:
    hits: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "extra":
                    continue
                keys: list[str] = []
                if isinstance(kw.value, ast.Dict):
                    keys = [k.value for k in kw.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                elif (
                    isinstance(kw.value, ast.Call)
                    and isinstance(kw.value.func, ast.Name)
                    and kw.value.func.id == "dict"
                ):
                    keys = [k.arg for k in kw.value.keywords if k.arg]
                hits.extend(
                    f"{path.relative_to(_SRC.parent)}:{node.lineno} extra key {key!r}"
                    for key in keys
                    if key in _RESERVED
                )
    return hits


def test_no_log_extra_key_collides_with_logrecord_attributes() -> None:
    assert _reserved_extra_keys() == []
