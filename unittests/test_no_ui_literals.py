"""No SAP UI literal outside the language packs (#1044, spec section 10).

Scans ``src/sapguimcp/**/*.py`` (outside ``lang/``) and ``backend/webgui/js/*.js`` for string
literals that look like SAP screen text, with three rules:

1. **Sink rule** (AST): a literal passed to a UI sink (``click_button``, ``get_by_role(name=...)``,
   a local ``*_bilingual`` helper, a ``text=`` / ``has-text(...)`` / ``[title*=...]`` selector),
   compared with ``in`` / ``==`` / ``startswith`` / ``re.*`` against a name that looks like screen
   text (``title``, ``status``, ``label``, ...), or used as a key of ``row.get(...)`` / ``row[...]``.
2. **Value rule**: a literal that contains, as whole words and case-folded, a variant of five or
   more characters of any registered language pack. It skips the server's own messages (f-string
   parts, ``raise`` arguments, ``error=`` / ``message=`` values), identifiers, CSS selectors and
   prose of more than six words; the sink rule still applies to those.
3. **JS rule**: a string or regex literal used with ``includes``, ``===``, ``match``, ``test``,
   ``replace``, ..., or in a ``title*=`` / ``has-text`` selector, in ``.js`` files and in JS
   functions held in Python strings (``evaluate_javascript("() => {...}")``).

Skipped everywhere: docstrings, logging calls, ``description=`` keyword arguments, and literals that
are code (no letters, one character, ``snake_case``, ALL CAPS, only DOM/ARIA vocabulary).

Exemptions are keyed by file and literal, never by line:

- ``unittests/lang_baseline.json`` is shrink-only: ``{file: {literal: count}}``, where ``count`` is
  how many (not skipped, not ``lang-ok``) literals in that file have exactly that value. A new hit
  fails, and so does an entry whose count no longer matches. Phase-3 migrations only delete or lower
  entries; ``uv run python unittests/test_no_ui_literals.py --prune`` does that and never adds one.
- ``# lang-ok: <reason>`` (``// lang-ok: <reason>`` in JS) on any line of the literal is a permanent
  exemption for literals that are code identifiers or the server's own messages. A pack added later
  may need new ``lang-ok`` comments, never a baseline entry.
"""

import ast
import io
import json
import re
import sys
import textwrap
import tokenize
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

from sapguimcp import lang
from sapguimcp.lang.schema import iter_leaves
from sapguimcp.lang.text import Template, Text

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "sapguimcp"
LANG_DIR = SRC / "lang"
JS_DIR = SRC / "backend" / "webgui" / "js"
BASELINE = Path(__file__).with_name("lang_baseline.json")

MIN_VALUE_LENGTH = 5
MAX_VALUE_WORDS = 6
"""Longer literals are prose (messages, docs); the value rule leaves them to the sink rule."""
MESSAGE_KEYWORDS = frozenset({"error", "message", "msg", "hint", "reason", "details", "suggestion"})
CSS_SELECTOR = re.compile(r"\s*(?:[.#\[]|[a-z]+[.#\[:])|.*\[(?:class|id|name|role|lsdata|ct|data-[\w-]+)[*^$|~]?=")
IDENTIFIER = re.compile(r"[a-z]+(?:-[a-z]+)*|[A-Za-z]:\\.*")
"""``active``, ``data-program``, a Windows path: code, not screen text."""

SINK_CALLS = frozenset(
    {
        "click_button",
        "click_tab",
        "fill_field",
        "fill_form",
        "set_checkbox",
        "select_dropdown",
        "get_by_text",
        "get_by_label",
        "get_by_title",
        "get_by_placeholder",
    }
)
"""Calls whose string arguments are screen texts (positional, keyword, or dict keys)."""
SINK_CALL_PATTERN = re.compile(r"bilingual|^_?click_\w*(?:button|tab)|^find_button")
"""Local helpers that click or set by label: ``_click_tab_bilingual``, ``_click_display_button``, ..."""
SINK_KEYWORDS = frozenset({"has_text", "has_not_text"})
"""``locator(..., has_text=...)``; ``name=`` counts only in ``get_by_role``."""
CONTEXT_NAME = re.compile(r"title|heading|snapshot|status|msg|message|text|label|header|kind|level", re.IGNORECASE)
ROW_NAME = re.compile(r"(?:^|_)rows?(?:$|_)", re.IGNORECASE)
STRING_METHODS = frozenset({"startswith", "endswith", "find", "rfind", "index", "count", "split", "partition"})
TRANSPARENT_METHODS = frozenset({"lower", "upper", "casefold", "strip", "lstrip", "rstrip"})
RE_FUNCTIONS = frozenset({"search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split"})
LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "log"})
LOG_RECEIVER = re.compile(r"^_?(?:log|logger|logging|LOGGER|LOG)$|_logger$|_log$")
SELECTOR = re.compile(
    r"""(?:(?<![\w.-])text=(?!=)|has-text\(|:text(?:-is)?\(|\[(?:title|aria-label|placeholder)[*^$|~]?=)\s*['"]?([^'"\])]*)"""
)
INLINE_JS = re.compile(r"\s*\(?\s*(?:async\s+)?(?:\([^()]*\)|[A-Za-z_$][\w$]*)\s*=>|\s*\(?\s*function\b")
"""A Python string holding a JS function for ``evaluate_javascript``; scanned with the JS rule."""
LANG_OK = re.compile(r"(?:#|//)\s*lang-ok:\s*\S")

TECHNICAL_WORDS = frozenset(
    " ".join(
        (
            # ARIA roles (snapshot syntax)
            "alert article banner button cell checkbox columnheader combobox dialog document generic grid",
            "gridcell group heading img link list listbox listitem main menu menubar menuitem navigation",
            "note option paragraph radio region row rowgroup rowheader separator status tab table tablist",
            "tabpanel textbox toolbar tooltip tree treeitem",
            # CSS values, tag names, input types, typeof results, event names, literals
            "block flex hidden inline none visible visibility collapse",
            "input select textarea span div form script style noscript iframe body",
            "text password submit reset file",
            "string number boolean object undefined function",
            "click dblclick change focus blur keydown keyup",
            "true false null",
        )
    ).split()
)
"""Lower-case DOM, ARIA and JS vocabulary; a literal made only of these words is code."""
_NOT_WORDS = re.compile(r"\\[A-Za-z]|\[(?![^\]]*=)[^\]]*\]|\{\w*\}")
"""Regex escapes (``\\s``), character classes (``[A-Z0-9_]``, not ``[title*=...]``), placeholders."""


@dataclass(frozen=True, order=True)
class Hit:
    """One flagged literal; ``rule`` names the rule that flagged it."""

    path: str
    line: int
    literal: str
    rule: str


# ---------------------------------------------------------------------------
# Shared filters
# ---------------------------------------------------------------------------


@cache
def pack_variants() -> tuple[str, ...]:
    """Case-folded variants of five or more characters from every registered pack (keys excluded)."""
    found: set[str] = set()
    for code in lang.supported_languages():
        for path, leaf in iter_leaves(lang.pack_for(code)):
            if path.startswith("keys."):
                continue  # canonical key names (Enter, Delete) are the press_key API, not screen text
            if isinstance(leaf, Text):
                found.update(leaf.variants)
            elif isinstance(leaf, Template):
                for variant in leaf.variants:
                    found.update(re.split(r"\{[A-Za-z_]\w*\}", variant))
    return tuple(sorted({v.strip().casefold() for v in found if len(v.strip()) >= MIN_VALUE_LENGTH}))


@cache
def _pack_pattern() -> re.Pattern[str]:
    body = "|".join(re.escape(v) for v in sorted(pack_variants(), key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)")


def matches_pack(literal: str) -> bool:
    """Value rule: a pack variant occurs in ``literal`` as whole words, case-folded."""
    if IDENTIFIER.fullmatch(literal) or CSS_SELECTOR.match(literal) or len(literal.split()) > MAX_VALUE_WORDS:
        return False  # identifiers ("active"), CSS selectors, prose; screen text there is a sink hit
    return _pack_pattern().search(literal.casefold()) is not None


def is_technical(literal: str) -> bool:
    """Code, not screen text: no letters, one character, an identifier, or only technical words."""
    words = re.findall(r"[^\W\d_]+", _NOT_WORDS.sub(" ", literal))
    if not words or len(literal.strip()) == 1:
        return True
    if re.fullmatch(r"\w+", literal) and "_" in literal:
        return True  # snake_case / CONSTANT_NAME
    return all(word.isupper() or word in TECHNICAL_WORDS for word in words)


def _header_like(literal: str) -> bool:
    """SAP column headers start with a capital letter (``Methode``, ``Parameter Name``)."""
    return literal[:1].isupper()


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def _identifier(node: ast.AST) -> str | None:
    """The name a context check looks at: ``title``, ``self.title``, ``title.lower()``, ``rows[0]``."""
    while True:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in TRANSPARENT_METHODS
        ):
            node = node.func.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        else:
            break
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_context(node: ast.AST) -> bool:
    name = _identifier(node)
    return name is not None and CONTEXT_NAME.search(name) is not None


def _literals(node: ast.AST) -> list[ast.Constant]:
    """String constants of a literal operand: ``"x"``, ``("x", "y")``, ``["x"]``, ``{"x"}``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node]
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return [elt for elt in node.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
    return []


def _all_strings(node: ast.AST) -> list[ast.Constant]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _skipped(tree: ast.Module) -> set[int]:
    """ids of string constants in docstrings, logging calls and ``description=`` arguments."""
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            skipped.add(id(node.value))  # docstrings and other bare string statements
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in LOG_METHODS:
                receiver = _identifier(func.value)
                if receiver is not None and LOG_RECEIVER.search(receiver):
                    skipped.update(id(n) for n in _all_strings(node))
            for keyword in node.keywords:
                if keyword.arg == "description":
                    skipped.update(id(n) for n in _all_strings(keyword.value))
    return skipped


def _messages(tree: ast.Module) -> set[int]:
    """ids of the server's own messages, which the value rule skips.

    f-string parts, ``raise`` arguments, ``error=`` / ``message=`` / ... keyword values, the values
    of such keys in dict literals (``{"error": "..."}``) and ``.get("error", "...")`` defaults.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr | ast.Raise):
            found.update(id(n) for n in _all_strings(node))
        elif isinstance(node, ast.keyword) and node.arg in MESSAGE_KEYWORDS:
            found.update(id(n) for n in _all_strings(node.value))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in MESSAGE_KEYWORDS:
                    found.update(id(n) for n in _all_strings(value))
        elif isinstance(node, ast.Call) and _call_name(node) == "get" and len(node.args) == 2:
            key = node.args[0]
            if isinstance(key, ast.Constant) and key.value in MESSAGE_KEYWORDS:
                found.update(id(n) for n in _all_strings(node.args[1]))
    return found


class _Flag:
    """Collects ``id(constant) -> rule``; the first rule that flags a constant wins."""

    def __init__(self) -> None:
        self.hits: dict[int, str] = {}

    def __call__(self, nodes: list[ast.Constant], rule: str) -> None:
        for node in nodes:
            self.hits.setdefault(id(node), rule)


def _call_sinks(node: ast.Call, flag: _Flag) -> None:
    name = _call_name(node)
    func = node.func
    if name in SINK_CALLS or (name and SINK_CALL_PATTERN.search(name)):
        for value in [*node.args, *(keyword.value for keyword in node.keywords)]:
            flag(_literals(value), "sink-call")
            if isinstance(value, ast.Dict):  # fill_form({"Label": ...}), bilingual_target(fields_de={...})
                flag([k for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)], "sink-call")
    for keyword in node.keywords:
        if keyword.arg in SINK_KEYWORDS or (keyword.arg == "name" and name == "get_by_role"):
            flag(_literals(keyword.value), "sink-keyword")
    if not isinstance(func, ast.Attribute):
        return
    if func.attr in STRING_METHODS and _is_context(func.value):
        for arg in node.args:
            flag(_literals(arg), "compare")
    is_re = isinstance(func.value, ast.Name) and func.value.id == "re" and func.attr in RE_FUNCTIONS
    if is_re and node.args and any(_is_context(arg) for arg in node.args[1:]):
        flag(_all_strings(node.args[0]), "regex")
    if func.attr == "get" and node.args and ROW_NAME.search(_identifier(func.value) or ""):
        flag([n for n in _literals(node.args[0]) if _header_like(n.value)], "row-key")


def _sink_hits(tree: ast.Module) -> dict[int, str]:
    """ids of string constants the sink rule flags, with the sub-rule that flagged them."""
    flag = _Flag()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            _call_sinks(node, flag)
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for left, op, right in zip(operands, node.ops, operands[1:], strict=False):
                if isinstance(op, ast.In | ast.NotIn | ast.Eq | ast.NotEq):
                    if _is_context(right):
                        flag(_literals(left), "compare")
                    if _is_context(left):
                        flag(_literals(right), "compare")
        elif isinstance(node, ast.Subscript) and ROW_NAME.search(_identifier(node.value) or ""):
            flag([n for n in _literals(node.slice) if _header_like(n.value)], "row-key")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            match = SELECTOR.search(node.value)
            if match and match.group(1).strip() and "{" not in match.group(1):
                flag([node], "selector")
    return flag.hits


def _lang_ok_lines(source: str) -> set[int]:
    return {
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT and LANG_OK.match(token.string)
    }


def scan_python(path: Path, relative: str) -> tuple[list[Hit], Counter[str]]:
    return scan_python_source(path.read_text(encoding="utf-8"), relative)


def scan_python_source(source: str, relative: str) -> tuple[list[Hit], Counter[str]]:
    """Hits in Python source, and how often each literal occurs (skipped and lang-ok ones not counted)."""
    tree = ast.parse(source, filename=relative)
    skipped = _skipped(tree)
    sinks = _sink_hits(tree)
    messages = _messages(tree)
    ok_lines = _lang_ok_lines(source)
    counts: Counter[str] = Counter()
    hits: list[Hit] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or not node.value.strip():
            continue
        if id(node) in skipped or ok_lines & set(range(node.lineno, (node.end_lineno or node.lineno) + 1)):
            continue
        if INLINE_JS.match(node.value):
            inner_hits, inner_counts = scan_js_source(node.value, relative, node.lineno)
            hits.extend(inner_hits)
            counts.update(inner_counts)
            continue
        counts[node.value] += 1
        rule = sinks.get(id(node)) or ("value" if id(node) not in messages and matches_pack(node.value) else None)
        if rule is not None and not is_technical(node.value):
            hits.append(Hit(relative, node.lineno, node.value, rule))
    return hits, counts


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS_TOKEN = re.compile(
    r"""
    (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<str>'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*")
  | (?P<tmpl>`(?:\\.|[^`\\])*`)
  | (?P<ident>[A-Za-z_$][\w$]*)
  | (?P<num>\d[\w.]*)
  | (?P<op>===|!==|==|!=|=>|\?\.|&&|\|\||[{}()\[\];,.<>+\-*%=!?:&|^~@\#])
  | (?P<slash>/)
  | (?P<ws>\s+)
    """,
    re.VERBOSE | re.DOTALL,
)
_REGEX_BODY = re.compile(r"/(?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n\[])+/[a-z]*")
_REGEX_AFTER = frozenset({"(", ",", "=", ":", "[", "!", "&&", "||", "?", "{", "}", ";", "return", "=>"})
JS_METHODS = frozenset(
    {"includes", "match", "matchAll", "test", "replace", "replaceAll", "indexOf", "startsWith", "endsWith", "search"}
)
JS_ARRAY_METHODS = JS_METHODS | {"some", "find", "filter", "every"}
JS_EQUALITY = frozenset({"===", "!==", "==", "!="})


@dataclass(frozen=True)
class _Tok:
    kind: str
    text: str
    line: int


def _js_tokens(source: str) -> tuple[list[_Tok], set[int]]:
    """Tokens of JS source and the lines that carry a ``// lang-ok: <reason>`` comment."""
    tokens: list[_Tok] = []
    ok_lines: set[int] = set()
    position, line = 0, 1
    while position < len(source):
        if source[position] == "/" and not source.startswith(("//", "/*"), position):
            previous = tokens[-1] if tokens else None
            if previous is None or previous.text in _REGEX_AFTER or previous.text in JS_EQUALITY:
                regex = _REGEX_BODY.match(source, position)
                if regex:
                    tokens.append(_Tok("regex", regex.group(), line))
                    position = regex.end()
                    continue
        match = _JS_TOKEN.match(source, position)
        if match is None:
            raise ValueError(f"cannot tokenize JS at line {line}: {source[position : position + 20]!r}")
        kind, text = match.lastgroup or "", match.group()
        if kind == "comment":
            if LANG_OK.match(text):
                ok_lines.add(line)
        elif kind != "ws":
            tokens.append(_Tok("op" if kind == "slash" else kind, text, line))
        line += text.count("\n")
        position = match.end()
    return tokens, ok_lines


def scan_js(path: Path, relative: str) -> tuple[list[Hit], Counter[str]]:
    return scan_js_source(path.read_text(encoding="utf-8"), relative)


def scan_js_source(source: str, relative: str, first_line: int = 1) -> tuple[list[Hit], Counter[str]]:
    """JS rule and value rule over JS source: a ``.js`` file or a JS function inside a Python string."""
    tokens, ok_lines = _js_tokens(source)
    counts: Counter[str] = Counter()
    hits: list[Hit] = []
    for index, token in enumerate(tokens):
        if token.kind not in {"str", "regex", "tmpl"} or token.line in ok_lines:
            continue
        value = token.text if token.kind == "regex" else token.text[1:-1]
        if not value.strip():
            continue
        counts[value] += 1
        rule = _js_rule(tokens, index, value)
        if rule is None and token.kind == "str" and not _js_message(tokens, index) and matches_pack(value):
            rule = "value"
        words = value[1 : value.rindex("/")] if token.kind == "regex" else value
        if rule is not None and not is_technical(words):
            hits.append(Hit(relative, first_line + token.line - 1, value, rule))
    return hits, counts


def _js_message(tokens: list[_Tok], index: int) -> bool:
    """``throw new Error('...')`` or ``{error: '...'}``: the script's own message."""
    before = [t.text for t in tokens[max(index - 2, 0) : index]]
    return before == ["Error", "("] or (len(before) == 2 and before[1] == ":" and before[0] in MESSAGE_KEYWORDS)


def _js_rule(tokens: list[_Tok], index: int, value: str) -> str | None:
    def text(offset: int) -> str:
        position = index + offset
        return tokens[position].text if 0 <= position < len(tokens) else ""

    match = SELECTOR.search(value)
    if match and match.group(1).strip() and "${" not in match.group(1):
        return "js-selector"
    if text(-1) in JS_EQUALITY or text(1) in JS_EQUALITY:
        return "js-equality"
    called = text(-1) == "(" and text(-2) in JS_METHODS and text(-3) in {".", "?."}
    if called or (text(1) in {".", "?."} and text(2) in JS_METHODS):
        return "js-method"
    return "js-array" if _in_array_receiver(tokens, index) else None


def _in_array_receiver(tokens: list[_Tok], index: int) -> bool:
    """The literal is an element of ``[...]`` that is the receiver of ``.includes()`` / ``.some()`` / ..."""
    depth = 0
    for position in range(index - 1, -1, -1):
        current = tokens[position].text
        if current in {"]", ")", "}"}:
            depth += 1
        elif current in {"(", "{"}:
            if depth == 0:
                return False
            depth -= 1
        elif current == "[":
            if depth:
                depth -= 1
                continue
            close, inner = position + 1, 1
            while close < len(tokens) and inner:
                inner += {"[": 1, "]": -1}.get(tokens[close].text, 0)
                close += 1
            follow = [t.text for t in tokens[close : close + 2]]
            return len(follow) == 2 and follow[0] in {".", "?."} and follow[1] in JS_ARRAY_METHODS
    return False


# ---------------------------------------------------------------------------
# The scan and the baseline
# ---------------------------------------------------------------------------


def scanned_files() -> list[Path]:
    python = [p for p in SRC.rglob("*.py") if not p.is_relative_to(LANG_DIR)]
    return sorted([*python, *JS_DIR.glob("*.js")])


def scan() -> tuple[list[Hit], dict[str, Counter[str]]]:
    """Every hit (sorted) and the literal counts per file, over all scanned files."""
    hits: list[Hit] = []
    counts: dict[str, Counter[str]] = {}
    for path in scanned_files():
        relative = path.relative_to(ROOT).as_posix()
        file_hits, file_counts = (scan_js if path.suffix == ".js" else scan_python)(path, relative)
        hits.extend(file_hits)
        counts[relative] = file_counts
    return sorted(hits), counts


def load_baseline() -> dict[str, dict[str, int]]:
    baseline: dict[str, dict[str, int]] = json.loads(BASELINE.read_text(encoding="utf-8"))
    return baseline


def canonical_json(baseline: dict[str, dict[str, int]]) -> str:
    """The one accepted spelling of the baseline: files and literals sorted, no empty files."""
    ordered = {path: dict(sorted(entries.items())) for path, entries in sorted(baseline.items()) if entries}
    return json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"


def new_hits(hits: list[Hit], baseline: dict[str, dict[str, int]]) -> list[str]:
    return [
        f"{hit.path}:{hit.line}: {hit.literal!r} ({hit.rule}): move it into a language pack, or mark a code "
        "identifier or the server's own message with '# lang-ok: <reason>'"
        for hit in hits
        if hit.literal not in baseline.get(hit.path, {})
    ]


def stale_entries(counts: dict[str, Counter[str]], baseline: dict[str, dict[str, int]]) -> list[str]:
    found: list[str] = []
    for path, entries in sorted(baseline.items()):
        for literal, expected in sorted(entries.items()):
            actual = counts.get(path, Counter())[literal]
            if actual > expected:
                found.append(f"{path}: {literal!r} occurs {actual}x, the baseline allows {expected}x: a new site")
            elif actual < expected:
                found.append(
                    f"{path}: {literal!r} occurs {actual}x, the baseline says {expected}x: shrink the entry "
                    "(uv run python unittests/test_no_ui_literals.py --prune)"
                )
    return found


def prune(baseline: dict[str, dict[str, int]], counts: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    """Lower every count to what the code still has and drop zeros. Never adds an entry."""
    pruned = {
        path: {literal: min(count, counts.get(path, Counter())[literal]) for literal, count in entries.items()}
        for path, entries in baseline.items()
    }
    return {path: {literal: count for literal, count in entries.items() if count} for path, entries in pruned.items()}


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scanned() -> tuple[list[Hit], dict[str, Counter[str]]]:
    return scan()


def test_no_new_ui_literals(scanned: tuple[list[Hit], dict[str, Counter[str]]]) -> None:
    hits, _ = scanned
    found = new_hits(hits, load_baseline())
    assert not found, "\n".join(found)


def test_baseline_only_shrinks(scanned: tuple[list[Hit], dict[str, Counter[str]]]) -> None:
    _, counts = scanned
    found = stale_entries(counts, load_baseline())
    assert not found, "\n".join(found)


def test_baseline_is_canonical() -> None:
    assert BASELINE.read_text(encoding="utf-8") == canonical_json(load_baseline())


def test_breakpoint_tools_stays_on_the_baseline() -> None:
    """``breakpoint_tools.py`` is off-limits (spec, Goal): its literals stay exempt via the baseline."""
    assert "src/sapguimcp/tools/breakpoint_tools.py" in load_baseline()


def test_every_lang_ok_names_a_reason() -> None:
    bare = [
        f"{path.relative_to(ROOT).as_posix()}:{number}"
        for path in scanned_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if "lang-ok" in line and not LANG_OK.search(line)
    ]
    assert not bare, f"'lang-ok' needs a reason ('# lang-ok: <reason>'): {bare}"


# ---------------------------------------------------------------------------
# The rules, on small sources
# ---------------------------------------------------------------------------


def _python(source: str) -> list[tuple[str, str]]:
    hits, _ = scan_python_source(textwrap.dedent(source), "x.py")
    return [(hit.literal, hit.rule) for hit in hits]


def _js(source: str) -> list[tuple[str, str]]:
    hits, _ = scan_js_source(textwrap.dedent(source), "x.js")
    return [(hit.literal, hit.rule) for hit in hits]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('click_button(session, "Sichern")', [("Sichern", "sink-call")]),
        (
            'await _set_checkbox_bilingual(b, "Änderbar", "Modifiable", True)',
            [("Änderbar", "sink-call"), ("Modifiable", "sink-call")],
        ),
        ('page.get_by_role("button", name="Weiter")', [("Weiter", "sink-keyword")]),
        ('ok = "einstieg" in title.lower()', [("einstieg", "compare")]),
        ('ok = window_title.startswith(("Pflegen", "Maintain"))', [("Pflegen", "compare"), ("Maintain", "compare")]),
        ('m = re.search("Eintrag", status_text)', [("Eintrag", "regex")]),
        ('value = row.get("Methode", row.get("Method"))', [("Methode", "row-key"), ("Method", "row-key")]),
        ("SELECTOR = \"span[title*='Einstellungen']\"", [("span[title*='Einstellungen']", "selector")]),
        ('LABELS = ("Anzahl Treffer", "Number of Hits")', [("Anzahl Treffer", "value"), ("Number of Hits", "value")]),
    ],
)
def test_python_rules_flag_screen_text(source: str, expected: list[tuple[str, str]]) -> None:
    assert _python(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        '"""Anzahl Treffer is read from the SE16 screen."""',
        'logger.info("Number of Hits: %s", hits)',
        'x = Field(default=None, description="Number of Hits shown by SE16")',
        'raise ValueError("Number of Hits not found")',
        'result = Result(error=f"Program {name} not found")',
        'ok = "Sichern" in data',
        'ok = status == "E"',
        'ok = kind in ("button", "checkbox")',
        'value = row.get("time")',
        "selector = f\"[title*='{label}']\"",
        'key = "active"',
        'threading.Thread(target=run, name="sapgui-com-worker")',
        'click_button(session, "Sichern")  # lang-ok: test fixture text',
    ],
)
def test_python_rules_skip_code_and_messages(source: str) -> None:
    assert _python(source) == []


def test_lang_ok_needs_a_reason() -> None:
    assert _python('click_button(session, "Sichern")  # lang-ok') == [("Sichern", "sink-call")]


def test_lang_ok_covers_every_line_of_a_multiline_literal() -> None:
    source = 'click_button(s, """Sichern\nund Weiter""")  # lang-ok: test fixture text\n'
    assert _python(source) == []


def test_inline_javascript_in_python_uses_the_js_rule() -> None:
    source = 'JS = """() => {\n    return text === \'Anzeigen\';\n}"""\n'
    hits, counts = scan_python_source(source, "x.py")
    assert [(hit.literal, hit.rule, hit.line) for hit in hits] == [("Anzeigen", "js-equality", 2)]
    assert counts["Anzeigen"] == 1


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("if (['ja', 'nein'].includes(t)) {}", [("ja", "js-array"), ("nein", "js-array")]),
        ("if (/Meldungsleiste/.test(x)) {}", [("/Meldungsleiste/", "js-method")]),
        ("if (el.title === 'Schließen') {}", [("Schließen", "js-equality")]),
        ("const c = document.querySelector(\"[title*='Schlie']\");", [("[title*='Schlie']", "js-selector")]),
        ("const s = text.replace('Meldungsleiste', '');", [("Meldungsleiste", "js-method")]),
    ],
)
def test_js_rule_flags_screen_text(source: str, expected: list[tuple[str, str]]) -> None:
    assert _js(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "if (el.tagName === 'INPUT') {}",
        "if (style.display === 'none') {}",
        r"const t = text.replace(/\s+/g, ' ');",
        "throw new Error('Program not found');",
        "return {error: 'Number of Hits not found'};",
        "// if (t === 'Anzeigen') {}",
        "if (t === 'Anzeigen') {}  // lang-ok: test fixture text",
    ],
)
def test_js_rule_skips_code_and_messages(source: str) -> None:
    assert _js(source) == []


def test_value_rule_matches_whole_words_only() -> None:
    assert matches_pack("Number of Hits")
    assert not matches_pack("Number of Hitsfoo")
    assert not matches_pack("SEOCLASS-CLSNAME")  # "class" inside a technical name


def test_baseline_reports_new_sites_and_shrinking() -> None:
    counts = {"a.py": Counter({"Sichern": 2, "Pflegen": 1})}
    baseline = {"a.py": {"Sichern": 1, "Pflegen": 2, "Weg": 1}}
    found = stale_entries(counts, baseline)
    assert len(found) == 3
    assert "a new site" in found[1]  # sorted: Pflegen, Sichern, Weg
    assert prune(baseline, counts) == {"a.py": {"Sichern": 1, "Pflegen": 1}}


def test_new_hits_ignores_baselined_literals() -> None:
    hits = [Hit("a.py", 3, "Sichern", "sink-call"), Hit("a.py", 4, "Pflegen", "sink-call")]
    assert len(new_hits(hits, {"a.py": {"Sichern": 1}})) == 1


if __name__ == "__main__":
    if sys.argv[1:] != ["--prune"]:
        raise SystemExit("usage: uv run python unittests/test_no_ui_literals.py --prune")
    BASELINE.write_text(canonical_json(prune(load_baseline(), scan()[1])), encoding="utf-8", newline="\n")
