"""Guard: every pack text has a JS form that compiles in Node and matches its own variants (#1044, 2c)."""

from sapguimcp import lang
from sapguimcp.lang.schema import PackLike, iter_leaves
from sapguimcp.lang.text import RegexText, Text
from unittests.lang.node_runner import check_patterns


def _items() -> list[dict[str, object]]:
    views: list[tuple[str, PackLike]] = [(code, lang.pack_for(code)) for code in lang.supported_languages()]
    views += [(f"{code} view", lang.view_for(code)) for code in lang.supported_languages()]
    views.append(("universal", lang.universal()))
    items: list[dict[str, object]] = []
    for name, pack in views:
        for path, leaf in iter_leaves(pack):
            if isinstance(leaf, Text):
                items.append({**leaf.for_js(), "path": f"{name}: {path}", "matches": list(leaf.variants)})
            elif isinstance(leaf, RegexText):
                items.append({**leaf.for_js(), "path": f"{name}: {path}"})
    return items


def test_every_pack_text_compiles_in_javascript() -> None:
    assert check_patterns(_items()) == []
