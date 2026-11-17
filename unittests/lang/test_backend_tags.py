"""Every language-pack field is tagged with the backend that reads it, and the tag matches the code (#1099).

``lang/backends.py`` holds the tag of each field (desktop, webgui or both). This module derives the
same tag from the source and compares the two, so that the split can delete the other backend's
texts mechanically:

- a new field without a tag fails (the key sets differ),
- a tag that does not match where the field is read fails (a ``webgui`` field read by desktop code,
  a ``both`` field only one backend reads, ...),
- a field nothing reads fails, unless it is listed in ``KNOWN_UNUSED`` (shrink-only).

How a read is found: an attribute access ``<section>.<field>`` on a pack, either spelled out
(``t.se16.hit_count_label``) or through a local alias (``popup = lang.universal().popup``, also
``popup: Popup = ...``, and later ``popup.close``). Aliases are scoped to the outermost function
that binds them, so a name that is rebound to something else in another function is not confused.
A read counts for a backend by where it sits:

- ``backend/desktop/`` and any function whose name ends in ``_desktop`` (or has ``_desktop_`` in
  it): desktop,
- ``backend/webgui/`` (Python and the JS texts it passes through ``for_js()``),
  ``tools/browser_tools.py``, ``tools/se37_edit_tools.py``, ``tools/quick_report_tools.py`` (the
  WebGUI-only tools) and any function named ``*_webgui``: webgui,
- everything else (shared tool code, scrapers, models): both.

Shared code also calls into the backend folders (tool code imports the WebGUI parsers, for example
``map_visibility``, and calls them for both backends). So a function under ``backend/desktop/`` or
``backend/webgui/`` is *exposed* when its name is referenced, by a name or attribute access, from
code of another context, and its reads then count as shared (both). Exposure is transitive: the
functions an exposed function references are exposed too. This is a plain name match across
files, so a name collision only makes a field ``both``, which is the safe side.

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

WEBGUI_FILES = {
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
    """``desktop``, ``webgui`` or ``shared`` for code in ``function`` of the file at ``rel_path``."""
    if rel_path.startswith(DESKTOP_DIR):
        return "desktop"
    if rel_path.startswith(WEBGUI_DIR) or rel_path in WEBGUI_FILES:
        return "webgui"
    if re.search(r"_desktop($|_)", function):
        return "desktop"
    if re.search(r"_webgui($|_)", function):
        return "webgui"
    return "shared"


def _is_function(node: ast.AST) -> bool:
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)


def _units(tree: ast.AST) -> list[tuple[str, list[ast.AST], bool]]:
    """Outermost functions (methods too) as ``(name, nodes, is_module_level)``, plus ``""`` for the rest."""
    units: list[tuple[str, list[ast.AST], bool]] = []
    rest: list[ast.AST] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if _is_function(child):
                units.append((getattr(child, "name"), [child], node is tree))  # noqa: B009
            else:
                rest.append(child)
                walk(child)  # reaches the methods of a class and the functions of a ``with`` or ``if``

    walk(tree)
    units.append(("", rest, False))
    return units


def _walk(root: ast.AST, skip_functions: bool) -> list[ast.AST]:
    """``ast.walk``, optionally without entering functions (the module-level rest has none of its own)."""
    nodes = [root]
    for node in nodes:
        nodes.extend(child for child in ast.iter_child_nodes(node) if not (skip_functions and _is_function(child)))
    return nodes


def _aliases(nodes: list[ast.AST], skip_functions: bool) -> dict[str, str]:
    """Names bound to a pack section: ``popup = lang.universal().popup`` -> ``{"popup": "popup"}``."""
    aliases: dict[str, str] = {}
    for root in nodes:
        for node in _walk(root, skip_functions):
            value: ast.AST | None = None
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                value, targets = node.value, node.targets
            elif isinstance(node, ast.AnnAssign):
                value, targets = node.value, [node.target]
            if isinstance(value, ast.Attribute) and value.attr in SECTION_NAMES:
                for target in targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = value.attr
    return aliases


@dataclasses.dataclass
class _Unit:
    """One outermost function (or the module-level rest) of a file."""

    rel_path: str
    name: str
    context: str
    reads: set[str]
    references: set[str]
    module_level: bool


def _scan() -> list[_Unit]:
    found: list[_Unit] = []
    for path in sorted(SRC.rglob("*.py")):
        rel_path = path.relative_to(SRC).as_posix()
        if rel_path.startswith("lang/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, nodes, module_level in _units(tree):
            aliases = _aliases(nodes, skip_functions=not name)
            unit = _Unit(rel_path, name, _context(rel_path, name), set(), set(), module_level)
            for root in nodes:
                for node in _walk(root, skip_functions=not name):
                    if isinstance(node, ast.Name):
                        unit.references.add(node.id)
                    elif isinstance(node, ast.Attribute):
                        unit.references.add(node.attr)
                        if node.attr in FIELDS_BY_NAME:
                            owner = node.value
                            section = None
                            if isinstance(owner, ast.Attribute) and owner.attr in SECTION_NAMES:
                                section = owner.attr
                            elif isinstance(owner, ast.Name):
                                section = aliases.get(owner.id)
                            if section in FIELDS_BY_NAME[node.attr]:
                                unit.reads.add(f"{section}.{node.attr}")
            found.append(unit)
    return found


def _exposed_names(units: list[_Unit]) -> set[str]:
    """Names of backend-folder functions that code of another context references, transitively."""
    defined: dict[str, list[_Unit]] = defaultdict(list)
    for unit in units:
        if unit.module_level and unit.rel_path.startswith((DESKTOP_DIR, WEBGUI_DIR)):
            defined[unit.name].append(unit)
    exposed: set[str] = set()
    for unit in units:
        for name in unit.references & defined.keys():
            if any(target.context != unit.context for target in defined[name]):
                exposed.add(name)
    pending = list(exposed)
    while pending:
        for target in defined[pending.pop()]:
            for name in target.references & defined.keys():
                if name not in exposed:
                    exposed.add(name)
                    pending.append(name)
    return exposed


def derive_tags() -> dict[str, Backend | None]:
    """The tag each field gets from the code; ``None`` for a field nothing reads."""
    units = _scan()
    exposed = _exposed_names(units)
    contexts: dict[str, set[str]] = defaultdict(set)
    for unit in units:
        in_backend = unit.rel_path.startswith((DESKTOP_DIR, WEBGUI_DIR))
        context = "shared" if in_backend and unit.module_level and unit.name in exposed else unit.context
        for key in unit.reads:
            contexts[key].add(context)
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
