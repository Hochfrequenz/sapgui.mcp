"""Text fallback of ``extract_status_bar.js`` for a status bar without a type CSS class (#1088)."""

import pytest

from sapguimcp.backend.webgui.backend import _status_bar_arg
from sapguimcp.backend.webgui.js_helpers import load_js
from unittests.lang.node_runner import run_node

RUN_JS = """
const { source, arg, message } = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const span = { textContent: message, matches: () => true };
const area = {
    className: '',
    parentElement: null,
    querySelector: (selector) => (selector.includes('.lsMsgText') ? span : null),
};
global.document = { querySelector: (selector) => (selector === '#LSMSG_AREA' ? area : null) };
process.stdout.write(JSON.stringify((0, eval)(source)(arg)));
"""
"""Runs the script against a fake status area whose only message element holds ``message``."""


def _type_of(message: str) -> str:
    result = run_node(
        RUN_JS, {"source": load_js("extract_status_bar.js"), "arg": _status_bar_arg(), "message": message}
    )
    assert result["message"] == message
    return str(result["type"])


@pytest.mark.parametrize(
    "message",
    [
        "No syntax errors found",
        "Es wurden keine Syntaxfehler gefunden",
        "Das Programm ZTEST enthält keine Syntaxfehler",
    ],
)
def test_successful_syntax_check_is_success(message: str) -> None:
    assert _type_of(message) == "S"


@pytest.mark.parametrize("message", ["Syntax error in program ZTEST", "Syntaxfehler im Programm ZTEST"])
def test_real_syntax_error_stays_error(message: str) -> None:
    assert _type_of(message) == "E"
