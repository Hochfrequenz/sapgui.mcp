"""Text fallback of ``extract_status_bar.js`` for a status bar without a type CSS class (#1088)."""

import pytest

from sapguimcp.backend.webgui.backend import _status_bar_arg
from sapguimcp.backend.webgui.js_helpers import load_js
from unittests.lang.node_runner import run_node

RUN_JS = """
const { source, arg, cases } = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const fn = (0, eval)(source);
const results = cases.map(({ message, className }) => {
    const span = { textContent: message, matches: () => true };
    const area = {
        className,
        parentElement: null,
        querySelector: (selector) => (selector.includes('.lsMsgText') ? span : null),
    };
    global.document = { querySelector: (selector) => (selector === '#LSMSG_AREA' ? area : null) };
    return fn(arg);
});
process.stdout.write(JSON.stringify(results));
"""
"""Runs the script once per case against a fake status area whose only message element holds the message."""

# (message, CSS class of the status area, expected type)
CASES = [
    ("No syntax errors found", "", "S"),
    ("Es wurden keine Syntaxfehler gefunden", "", "S"),
    ("Es wurde kein Syntaxfehler gefunden", "", "S"),
    ("Das Programm ZTEST enthält keine Syntaxfehler", "", "S"),
    ("No syntax errors, but some warnings exist", "", "W"),
    ("Es wurden keine Syntaxfehler gefunden, aber es liegen Warnungen vor", "", "W"),
    ("Syntax error in program ZTEST", "", "E"),
    ("Syntaxfehler im Programm ZTEST", "", "E"),
    # a type CSS class wins over the text
    ("No syntax errors found", "lsMessageBar error", "E"),
]


@pytest.fixture(scope="module")
def types() -> dict[tuple[str, str], str]:
    cases = [{"message": m, "className": c} for m, c, _ in CASES]
    payload = {"source": load_js("extract_status_bar.js"), "arg": _status_bar_arg(), "cases": cases}
    results = run_node(RUN_JS, payload)
    assert [r["message"] for r in results] == [m for m, _, _ in CASES]
    return {(m, c): r["type"] for (m, c, _), r in zip(CASES, results, strict=True)}


@pytest.mark.parametrize(("message", "class_name", "expected"), CASES)
def test_status_bar_type(types: dict[tuple[str, str], str], message: str, class_name: str, expected: str) -> None:
    assert types[(message, class_name)] == expected
