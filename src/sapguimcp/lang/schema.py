"""The language pack schema: ``LanguagePack``, its sections, canonical enums and the merge (#1044).

Every field is required; no field has a default. A pack that omits a field fails mypy and fails
at import. Packs and merged views share the one type ``LanguagePack``.

Each section declares its merge mode as a ``ClassVar`` named ``MERGE`` in its own class body. A
class keyword argument would not work: ``@dataclass(slots=True)`` re-creates the class and drops
it silently.

- ``session_en``: the session pack, then EN (standard SAP shows untranslated texts in the
  secondary language, usually EN).
- ``all``: every registered pack (popups, status-type inference, session pages, key names must
  work regardless of the session language).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar, Literal, TypeVar, cast

from sapguimcp.lang.text import RegexText, Template, Text

MergeMode = Literal["session_en", "all"]
Leaf = Text | RegexText | Template
S = TypeVar("S")


# =============================================================================
# Canonical enums (keys of canonical mappings)
# =============================================================================


class JobStatus(StrEnum):
    """SM37 job status; the values are the normalised status the tools report."""

    SCHEDULED = "Scheduled"
    RELEASED = "Released"
    READY = "Ready"
    ACTIVE = "Active"
    FINISHED = "Finished"
    CANCELED = "Canceled"


class TransportStatus(StrEnum):
    """SE09 request status filter."""

    MODIFIABLE = "Modifiable"
    RELEASED = "Released"


class Visibility(StrEnum):
    """SE24 component visibility."""

    PUBLIC = "Public"
    PROTECTED = "Protected"
    PRIVATE = "Private"


class DumpSection(StrEnum):
    """ST22 dump detail section."""

    WHAT_HAPPENED = "what_happened"
    HOW_TO_CORRECT = "how_to_correct"
    ERROR_ANALYSIS = "error_analysis"


class Key(StrEnum):
    """Canonical keyboard key names, as the desktop key mapping accepts them."""

    CTRL = "Ctrl"
    SHIFT = "Shift"
    ALT = "Alt"
    ENTER = "Enter"
    DELETE = "Delete"
    ESCAPE = "Escape"


def canonical(entries: Mapping[S, Text]) -> Mapping[S, Text]:
    """Freeze a canonical mapping (enum member -> ``Text``)."""
    return MappingProxyType(dict(entries))


# =============================================================================
# Sections merged across every registered pack
# =============================================================================


@dataclass(frozen=True, slots=True)
class PopupSection:
    """Popup texts. Empty until the popup migration (phase 3) moves them here."""

    MERGE: ClassVar[MergeMode] = "all"


@dataclass(frozen=True, slots=True)
class StatusTypeSection:
    """Keywords that infer a message's type. Empty until the status-bar migration (phase 3)."""

    MERGE: ClassVar[MergeMode] = "all"


@dataclass(frozen=True, slots=True)
class SessionPagesSection:
    """Login, logoff and timeout page texts. Empty until the session-pages migration (phase 3)."""

    MERGE: ClassVar[MergeMode] = "all"


@dataclass(frozen=True, slots=True)
class KeysSection:
    """Localized key names, from ``sap_tools._is_keyboard_shortcut`` (F-keys are language-free)."""

    MERGE: ClassVar[MergeMode] = "all"
    names: Mapping[Key, Text]


# =============================================================================
# Sections merged as session pack, then EN
# =============================================================================


@dataclass(frozen=True, slots=True)
class CommonSection:
    """Vocabulary shared by several transactions."""

    MERGE: ClassVar[MergeMode] = "session_en"
    display: Text
    not_found: Text
    does_not_exist: Text
    no_entries: Text
    row_select_hint: Text
    user: Text
    program: Text


@dataclass(frozen=True, slots=True)
class Se09Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    status: Mapping[TransportStatus, Text]
    display_button: Text
    """Case-sensitive on purpose: the WebGUI check scans a whole snapshot, so ``common.display`` is too broad."""
    workbench_requests: Text
    customizing_requests: Text
    expand: Text
    compress: Text
    list_region: Text
    organizer_title: Text
    request_word: Text


@dataclass(frozen=True, slots=True)
class AbapgitSection:
    """Texts of SAP messages and popups around the abapGit report; the report's own output is invariant."""

    MERGE: ClassVar[MergeMode] = "session_en"
    error_keywords: Text
    status_error: Text
    screen_errors: Text
    transport_required: Text
    no_task: Text
    button_labels: Text
    inactive_objects: Text
    se38_initial_title: Text


@dataclass(frozen=True, slots=True)
class QuickReportSection:
    MERGE: ClassVar[MergeMode] = "session_en"
    empty_patterns: Text
    execute_button: Text


@dataclass(frozen=True, slots=True)
class Se11Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    database_table: Text
    data_type: Text
    table_name: Text
    transparent_table: Text
    structure: Text
    short_description: Text
    row_select_full: RegexText
    dictionary_type: RegexText


@dataclass(frozen=True, slots=True)
class Se16Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    hit_count_label: Text
    column_selection: Text
    no_values_found: Text


@dataclass(frozen=True, slots=True)
class Se24Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    class_builder: Text
    initial_screen: Text
    display_title: Template
    object_type: Text
    class_label: Text
    interface_label: Text
    visibility: Mapping[Visibility, Text]
    static: Text
    abstract: Text


@dataclass(frozen=True, slots=True)
class Se37Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    display_title: Template


@dataclass(frozen=True, slots=True)
class Se93Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    dialog_transaction: Text
    report_transaction: Text
    gui_html: Text
    gui_java: Text
    gui_windows: Text
    screen_number: Text
    selection_screen: Text
    start_with_variant: Text
    transaction_code: Text
    transaction_text: Text
    package: Text
    auth_object: Text


@dataclass(frozen=True, slots=True)
class Slg1Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    log_list_screen: Text
    no_logs_found: Text


@dataclass(frozen=True, slots=True)
class Sm30Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    maintain: Text
    table_view: Text
    display_view: Text
    view_not_found: Text
    no_maintenance_dialog: Text
    view_title: Template
    row_count: Template


@dataclass(frozen=True, slots=True)
class Sm37Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    status: Mapping[JobStatus, Text]


@dataclass(frozen=True, slots=True)
class SproSection:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    sap_reference_img: Text
    search_button: Text
    search_dialog: Text
    search_field: Text
    results_dialog: Text
    column_hits: Text
    column_parent: Text
    column_area: Text
    img_heading: Text


@dataclass(frozen=True, slots=True)
class St22Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    section: Mapping[DumpSection, Text]


# =============================================================================
# The pack
# =============================================================================


@dataclass(frozen=True, slots=True)
class LanguagePack:
    """All language-dependent texts of one SAP logon language, or a merged view of several."""

    code: str
    """SAP language key, e.g. ``"DE"``."""
    html_lang: str
    """ISO code the WebGUI page reports in ``<html lang>``, e.g. ``"de"``."""
    logon_dropdown: str
    """Text of the WebGUI logon language dropdown, e.g. ``"Deutsch"``."""
    date_format: str
    """Default date input format as a ``strftime`` pattern (#1043 reads the user's own)."""
    same_as_en: frozenset[str]
    """Field paths whose value deliberately equals EN (checked by the untranslated-field test)."""

    common: CommonSection
    popup: PopupSection
    status_type: StatusTypeSection
    session_pages: SessionPagesSection
    keys: KeysSection
    abapgit: AbapgitSection
    quick_report: QuickReportSection
    se09: Se09Section
    se11: Se11Section
    se16: Se16Section
    se24: Se24Section
    se37: Se37Section
    se93: Se93Section
    slg1: Slg1Section
    sm30: Sm30Section
    sm37: Sm37Section
    spro: SproSection
    st22: St22Section


@dataclass(frozen=True, slots=True)
class UniversalView:
    """The ``all`` sections merged over every registered pack, independent of any session.

    Its own type with exactly the four ``all`` sections, not a ``LanguagePack``: mypy then rejects
    parsing a transaction screen (a ``session_en`` section) against every language.
    """

    popup: PopupSection
    status_type: StatusTypeSection
    session_pages: SessionPagesSection
    keys: KeysSection


PackLike = LanguagePack | UniversalView
"""What the walkers accept: a pack, a merged view of it, or the universal view."""


# =============================================================================
# Walking and merging
# =============================================================================


def sections(pack: PackLike) -> Iterator[tuple[str, Any]]:
    """``(name, section)`` for every section field of ``pack`` (skips scalar pack fields)."""
    for field in dataclasses.fields(pack):
        value = getattr(pack, field.name)
        if dataclasses.is_dataclass(value):
            yield field.name, value


def iter_leaves(pack: PackLike) -> Iterator[tuple[str, Leaf]]:
    """Every text of ``pack`` with its path: ``se16.hit_count_label``, ``sm37.status[Ready]``."""
    for section_name, section in sections(pack):
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            path = f"{section_name}.{field.name}"
            if isinstance(value, Mapping):
                for key, leaf in value.items():
                    yield f"{path}[{key}]", leaf
            else:
                yield path, value


def resolve(pack: PackLike, path: str) -> Leaf:
    """The text at ``path`` (as produced by :func:`iter_leaves`); ``KeyError`` if there is none."""
    for leaf_path, leaf in iter_leaves(pack):
        if leaf_path == path:
            return leaf
    raise KeyError(path)


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _merge_leaves(leaves: Sequence[Leaf]) -> Leaf:
    first = leaves[0]
    for other in leaves[1:]:
        if type(other) is not type(first):
            raise TypeError(f"cannot merge {type(first).__name__} with {type(other).__name__}")
    if isinstance(first, Text):
        texts = cast("Sequence[Text]", leaves)
        if any((t.fold, t.word) != (first.fold, first.word) for t in texts):
            raise ValueError(f"Text flags differ: {texts!r}")
        return Text(_unique([v for t in texts for v in t.variants]), fold=first.fold, word=first.word)
    if isinstance(first, RegexText):
        regexes = cast("Sequence[RegexText]", leaves)
        if any(r.fold != first.fold for r in regexes):
            raise ValueError(f"RegexText flags differ: {regexes!r}")
        return RegexText(_unique([p for r in regexes for p in r.patterns]), fold=first.fold)
    templates = cast("Sequence[Template]", leaves)
    if any(t.fold != first.fold for t in templates):
        raise ValueError(f"Template flags differ: {templates!r}")
    return Template(_unique([v for t in templates for v in t.variants]), fold=first.fold)


def merge(items: Sequence[S]) -> S:
    """Field-wise merge of packs or sections, first item first.

    Texts concatenate their variants (de-duplicated, order kept); canonical mappings merge per
    key; nested dataclasses merge field by field; anything else (pack code, ``html_lang``,
    ``same_as_en``, ...) is taken from the first item.
    """
    if not items:
        raise ValueError("merge needs at least one item")
    first = items[0]
    if isinstance(first, Text | RegexText | Template):
        return cast("S", _merge_leaves(cast("Sequence[Leaf]", items)))
    if isinstance(first, Mapping):
        mappings = cast("Sequence[Mapping[object, object]]", items)
        keys = _unique_keys(mappings)
        return cast("S", MappingProxyType({key: merge([m[key] for m in mappings if key in m]) for key in keys}))
    if dataclasses.is_dataclass(first) and not isinstance(first, type):
        values = {
            field.name: merge([getattr(item, field.name) for item in items]) for field in dataclasses.fields(first)
        }
        return cast("S", type(first)(**values))
    return first


def _unique_keys(mappings: Sequence[Mapping[object, object]]) -> list[object]:
    keys: dict[object, None] = {}
    for mapping in mappings:
        keys.update(dict.fromkeys(mapping))
    return list(keys)
