"""JavaScript file loading helpers for the WebGUI backend."""

from functools import lru_cache
from importlib import resources


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
