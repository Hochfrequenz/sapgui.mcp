"""JavaScript file loading helpers for the WebGUI backend.

Every script takes one object argument (Playwright ``evaluate`` accepts exactly one). Build it with
:func:`script_arg`: language-dependent texts go under ``texts`` in their JS form, plain values next
to it (#1044, spec section 8).
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sapguimcp.lang.text import JsPattern, RegexText, Text


@lru_cache(maxsize=16)
def load_js(filename: str) -> str:
    """Load a JavaScript file from the sapguimcp.backend.webgui.js package."""
    return resources.files("sapguimcp.backend.webgui.js").joinpath(filename).read_text(encoding="utf-8")


@lru_cache(maxsize=8)
def load_js_with_field_utils(filename: str) -> str:
    """Load a JS file with find_field_utils.js prepended."""
    utils = load_js("find_field_utils.js")
    tool = load_js(filename)
    return utils + "\n" + tool


def script_arg(texts: Mapping[str, Text | RegexText] | None = None, **values: object) -> dict[str, object]:
    """The single object argument of a WebGUI script: ``{"texts": {...}, **values}``.

    ``texts`` maps the names the script reads (``texts.<name>.source`` / ``.flags`` /
    ``.variants``) to pack texts; each is converted with ``for_js()``. ``texts`` is always present,
    possibly empty, so every script can destructure ``{ texts, ... }``.
    """
    js_texts: dict[str, JsPattern] = {name: text.for_js() for name, text in (texts or {}).items()}
    return {"texts": js_texts, **values}
