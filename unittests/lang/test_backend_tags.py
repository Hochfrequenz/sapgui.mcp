"""Every language-pack field is tagged with the backend that reads it, and the tag matches the code (#1099).

``lang/backends.py`` holds the tag of each field (desktop, webgui or both). This module derives the
same tag from the source and compares the two, so that the split can delete the other backend's
texts mechanically:

- a new field without a tag fails (the key sets differ),
- a tag that does not match where the field is read fails (a ``webgui`` field read by desktop code,
  a ``both`` field only one backend reads, ...),
- a field nothing reads fails, unless it is listed in ``KNOWN_UNUSED`` (shrink-only).

How a read is found: an attribute access ``<section>.<field>`` on a pack, either spelled out
(``t.se16.hit_count_label``) or through a local alias (``popup = lang.universal().popup`` and later
``popup.close``). A read counts for a backend by where it sits:

- ``backend/desktop/``, ``tools/desktop_wait_predicates.py``, ``tools/table_helpers.py`` and any
  function whose name ends in ``_desktop`` (or has ``_desktop_`` in it): desktop,
- ``backend/webgui/`` (Python and the JS texts it passes through ``for_js()``),
  ``tools/screen_state_helpers.py``, ``tools/browser_tools.py``, ``tools/se37_edit_tools.py``,
  ``tools/quick_report_tools.py`` and any function named ``*_webgui``: webgui,
- everything else (shared tool code, scrapers, models): both.

A field is ``desktop`` or ``webgui`` when every read is of that kind, otherwise ``both``. When a tool
function without a backend suffix reads a field for one backend only, the field is ``both``: shared
code is kept on both sides, so the tag is safe, only less sharp.
"""

import ast
import dataclasses
import re
from collections import defaultdict
from pathlib import Path

from sapguimcp import lang
from sapguimcp.lang.backends import BACKEND_OF, Backend, backend_of
from sapguimcp.lang.schema import iter_leaves, sections

SRC = Path(__file__).resolve().parents[2] / "src" / "sapguimcp"

DESKTOP_FILES = {"tools/desktop_wait_predicates.py", "tools/table_helpers.py"}
WEBGUI_FILES = {
    "tools/screen_state_helpers.py",
    "tools/browser_tools.py",
    "tools/se37_edit_tools.py",
    "tools/quick_report_tools.py",
}
DESKTOP_DIR = "backend/desktop/"
WEBGUI_DIR = "backend/webgui/"

KNOWN_UNUSED = {
    # Harvested SAP texts that no code reads (yet). Delete a field here when it is removed from the packs.
    "sm30.maintain",
    "sm30.display_view",
    "spro.sap_reference_img",
    "spro.search_dialog",
    "spro.search_field",
    "spro.column_hits",
    "spro.column_parent",
    "spro.column_area",
}

EN = lang.pack_for("EN")
SECTION_NAMES = {name for name, _ in sections(EN)}
FIELDS_BY_NAME: dict[str, set[str]] = defaultdict(set)
for _section_name, _section in sections(EN):
    for _field in dataclasses.fields(_section):
        FIELDS_BY_NAME[_field.name].add(_section_name)


def _context(rel_path: str, function: str) -> str:
    """``desktop``, ``webgui`` or ``shared`` for a read in ``function`` of the file at ``rel_path``."""
    if rel_path.startswith(DESKTOP_DIR) or rel_path in DESKTOP_FILES:
        return "desktop"
    if rel_path.startswith(WEBGUI_DIR) or rel_path in WEBGUI_FILES:
        return "webgui"
    if re.search(r"_desktop($|_)", function):
        return "desktop"
    if re.search(r"_webgui($|_)", function):
        return "webgui"
    return "shared"


def _section_aliases(tree: ast.AST) -> dict[str, str]:
    """Local names bound to a pack section: ``popup = lang.universal().popup`` -> ``{"popup": "popup"}``."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute) and node.value.attr in SECTION_NAMES:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    aliases[target.id] = node.value.attr
    return aliases


def _reads_in(rel_path: str, tree: ast.AST) -> dict[str, set[str]]:
    """``"section.field"`` -> the contexts (``desktop`` / ``webgui`` / ``shared``) reading it in this file."""
    aliases = _section_aliases(tree)
    found: dict[str, set[str]] = defaultdict(set)

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = function
            if not function and isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                inner = child.name  # the outermost function names the context
            if isinstance(child, ast.Attribute) and child.attr in FIELDS_BY_NAME:
                owner = child.value
                section = None
                if isinstance(owner, ast.Attribute) and owner.attr in SECTION_NAMES:
                    section = owner.attr
                elif isinstance(owner, ast.Name):
                    section = aliases.get(owner.id)
                if section in FIELDS_BY_NAME[child.attr]:
                    found[f"{section}.{child.attr}"].add(_context(rel_path, inner))
            visit(child, inner)

    visit(tree, "")
    return found


def derive_tags() -> dict[str, Backend | None]:
    """The tag each field gets from the code; ``None`` for a field nothing reads."""
    contexts: dict[str, set[str]] = defaultdict(set)
    for path in sorted(SRC.rglob("*.py")):
        rel_path = path.relative_to(SRC).as_posix()
        if rel_path.startswith("lang/"):
            continue
        for key, found in _reads_in(rel_path, ast.parse(path.read_text(encoding="utf-8"))).items():
            contexts[key] |= found
    tags: dict[str, Backend | None] = {}
    for section_name, section in sections(EN):
        for field in dataclasses.fields(section):
            key = f"{section_name}.{field.name}"
            kinds = contexts.get(key)
            if not kinds:
                tags[key] = None
            elif kinds == {"desktop"}:
                tags[key] = Backend.DESKTOP
            elif kinds == {"webgui"}:
                tags[key] = Backend.WEBGUI
            else:
                tags[key] = Backend.BOTH
    return tags


def test_every_field_has_exactly_one_tag() -> None:
    fields = {f"{name}.{field.name}" for name, section in sections(EN) for field in dataclasses.fields(section)}
    assert fields - set(BACKEND_OF) == set(), "fields without a tag in lang/backends.py"
    assert set(BACKEND_OF) - fields == set(), "tags for fields that no longer exist"


def test_every_leaf_resolves_to_a_tag() -> None:
    for path, _ in iter_leaves(EN):
        assert isinstance(backend_of(path), Backend), path


def test_tags_match_where_the_fields_are_read() -> None:
    derived = derive_tags()
    wrong = {
        key: f"tagged {BACKEND_OF[key].value}, read by {tag.value}"
        for key, tag in derived.items()
        if tag is not None and BACKEND_OF[key] is not tag
    }
    assert wrong == {}, "fix the tag in lang/backends.py (or the read: see the module docstring of this test)"


def test_unused_fields_are_exactly_the_known_ones() -> None:
    unused = {key for key, tag in derive_tags().items() if tag is None}
    assert unused - KNOWN_UNUSED == set(), "nothing reads these fields: use them or delete them from the packs"
    assert KNOWN_UNUSED - unused == set(), "these fields are read now: remove them from KNOWN_UNUSED"


def test_tag_counts_leave_something_to_delete_on_each_side() -> None:
    counts = {backend: sum(1 for tag in BACKEND_OF.values() if tag is backend) for backend in Backend}
    assert counts[Backend.DESKTOP] > 0
    assert counts[Backend.WEBGUI] > 0
