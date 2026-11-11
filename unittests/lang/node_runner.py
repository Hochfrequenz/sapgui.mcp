"""Run JavaScript checks in Node for the language-pack guards (#1044, phase 2c).

Prefers the Node runtime that Playwright ships with its driver (always installed: Playwright is a
runtime dependency), then ``node`` on ``PATH``. Without either, the calling test is skipped
locally and fails in CI, so the JS guard cannot vanish silently.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

CHECK_PATTERNS_JS = """
const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const results = items.map(({ path, source, flags, matches = [], rejects = [] }) => {
    try {
        const re = new RegExp(source, flags);
        return {
            path,
            error: null,
            missed: matches.filter((s) => !re.test(s)),
            wrongly_matched: rejects.filter((s) => re.test(s)),
        };
    } catch (e) {
        return { path, error: String(e.message), missed: [], wrongly_matched: [] };
    }
});
process.stdout.write(JSON.stringify(results));
"""
"""Reads ``[{path, source, flags, matches, rejects}]`` from stdin, writes one result per item."""


def node_executable() -> str | None:
    """Playwright's bundled Node, else ``node`` on ``PATH``, else ``None``."""
    try:
        from playwright._impl._driver import compute_driver_executable  # noqa: PLC0415  # private API

        node = Path(compute_driver_executable()[0])
        if node.is_file():
            return str(node)
    except (ImportError, AttributeError, IndexError, TypeError):
        pass
    return shutil.which("node")


def run_node(script: str, payload: object) -> Any:
    """Run ``script`` with ``payload`` as JSON on stdin and return its JSON stdout."""
    node = node_executable()
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("no Node.js runtime found; the JS guards must run in CI")
        pytest.skip("no Node.js runtime found")
    result = subprocess.run(  # noqa: S603  # fixed script, our own executable lookup
        [node, "-e", script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def check_patterns(items: list[dict[str, object]]) -> list[dict[str, Any]]:
    """Compile each item's ``source``/``flags`` in Node; return only the items with a problem."""
    results: list[dict[str, Any]] = run_node(CHECK_PATTERNS_JS, items)
    return [r for r in results if r["error"] or r["missed"] or r["wrongly_matched"]]
