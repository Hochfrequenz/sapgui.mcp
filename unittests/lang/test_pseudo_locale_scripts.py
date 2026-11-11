"""Pseudo-locale harness for the WebGUI page scripts (#1044, spec section 10).

The companion of ``test_pseudo_locale_parsers.py`` for the code that reads the page itself: every
captured HTML snapshot is loaded into headless Chromium as captured (under its language) and
rewritten into the pseudo language (under the unmerged pseudo pack), and the read-only backend
calls that run the page scripts must return the same result: status bar
(``extract_status_bar.js``), popup detection (``check_popup.js``), field and button discovery,
form fields, screen info and table data.

One browser serves the whole module; the results are collected once and asserted per snapshot.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from playwright.async_api import Page, async_playwright

from sapguimcp import lang
from sapguimcp.backend.webgui.backend import WebGuiBackend

from . import pseudo_fixtures as pf
from .test_pseudo_locale_parsers import _difference, _plain

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

SNAPSHOTS = Path(__file__).parent.parent / "webgui" / "testdata" / "html_snapshots"
NAMES = sorted(path.name for path in SNAPSHOTS.glob("*.html"))

_CALLS: dict[str, Callable[[WebGuiBackend], Awaitable[Any]]] = {
    "status_bar": lambda backend: backend.get_status_bar(),
    "popup": lambda backend: backend.check_popup(),
    "fields": lambda backend: backend.discover_fields(),
    "buttons": lambda backend: backend.discover_buttons(),
    "form_fields": lambda backend: backend.get_form_fields(),
    "screen_info": lambda backend: backend.get_screen_info(),
    "table": lambda backend: backend.read_table(),
}

_SPLIT_BUTTON_TEXT = (
    "the message bar's button text is split over two elements (its access key is underlined), so "
    "the rewriting, which works on one text node at a time, leaves it in real spelling while the "
    "script reads the joined text; the status bar cannot be compared on this capture"
)
_STATUS_BAR_SKIPPED: dict[str, str] = dict.fromkeys(
    (
        "easy_access_de.html",
        "easy_access_en.html",
        "emmacl_initial_de.html",
        "emmacl_initial_en.html",
        "emmacl_results_filtered_en.html",
        "settings_dialog_de.html",
        "settings_dialog_en.html",
        "sm37_initial_de.html",
        "sm37_initial_en.html",
        "status_bar_error_de.html",
        "status_bar_error_en.html",
    ),
    _SPLIT_BUTTON_TEXT,
)
"""Captures whose status bar is left out of the comparison, with the reason (a limit of the
rewriting, not of the script). Every other call is still compared on them."""


async def _results(page: Page, document: str) -> dict[str, Any]:
    await page.set_content(document, wait_until="domcontentloaded")
    backend = WebGuiBackend(page)
    results: dict[str, Any] = {}
    for name, call in _CALLS.items():
        try:
            results[name] = _plain(await call(backend))
        except Exception as error:  # pylint: disable=broad-exception-caught  # an error is a result to compare too
            results[name] = {"raised": type(error).__name__}
    return results


async def _collect() -> dict[str, tuple[dict[str, Any], dict[str, Any], int]] | str:
    """``{snapshot: (real, pseudo, replaced)}``, or the reason Chromium cannot be launched."""
    collected: dict[str, tuple[dict[str, Any], dict[str, Any], int]] = {}
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"))
        except Exception as error:  # pylint: disable=broad-exception-caught
            return f"Chromium cannot be launched here: {str(error).splitlines()[0]}"
        try:
            context = await browser.new_context(java_script_enabled=False)
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            for name in NAMES:
                language = name.removesuffix(".html")[-2:].upper()
                document = pf.unwrap_envelope((SNAPSHOTS / name).read_text(encoding="utf-8"), "html")
                assert not pf.PSEUDO_LETTERS & set(document), name
                rewrite = pf.rewrite_html(document, language)
                with lang.use(language):
                    real = await _results(page, document)
                with pf.pseudo_session(language):
                    pseudo = pf.restore(await _results(page, rewrite.text))
                collected[name] = (real, pseudo, rewrite.replaced)
        finally:
            await browser.close()
    return collected


@pytest.fixture(scope="module")
def collected() -> dict[str, tuple[dict[str, Any], dict[str, Any], int]]:
    logging.disable(logging.CRITICAL)  # the backend logs every call that a static page cannot answer
    try:
        result = asyncio.run(_collect())
    finally:
        logging.disable(logging.NOTSET)
    if isinstance(result, str):
        if os.environ.get("CI"):
            pytest.fail(result)  # CI installs Chromium; a silent skip would leave the scripts untested
        pytest.skip(result)
    return result


@pytest.mark.parametrize("name", NAMES)
def test_script_result_is_the_same_in_the_pseudo_language(
    name: str, collected: dict[str, tuple[dict[str, Any], dict[str, Any], int]]
) -> None:
    real, pseudo, replaced = collected[name]
    assert replaced, "no pack text was rewritten in this capture"
    differing = {
        call: _difference(real[call], pseudo[call])
        for call in real
        if real[call] != pseudo[call] and not (call == "status_bar" and name in _STATUS_BAR_SKIPPED)
    }
    assert not differing, f"{name}: the result depends on a real spelling in\n" + "\n".join(
        f"- {call}\n{text}" for call, text in differing.items()
    )


def test_the_status_bar_skips_are_still_needed(
    collected: dict[str, tuple[dict[str, Any], dict[str, Any], int]],
) -> None:
    stale = [
        name for name in _STATUS_BAR_SKIPPED if collected[name][0]["status_bar"] == collected[name][1]["status_bar"]
    ]
    assert not stale, f"compare the status bar again on {stale}"


@pytest.mark.parametrize("name", NAMES)
def test_html_is_rebuilt_unchanged_without_a_text_change(name: str) -> None:
    """The HTML rewriter touches nothing but the text it is asked to change."""
    document = pf.unwrap_envelope((SNAPSHOTS / name).read_text(encoding="utf-8"), "html")
    assert pf.rebuild_html(document, lambda text: text) == document
