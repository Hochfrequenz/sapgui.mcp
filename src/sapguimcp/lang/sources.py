"""Where each pack text comes from in SAP (#1044, spec section 9).

Every field of a language pack (every path of :func:`sapguimcp.lang.schema.iter_leaves`) has one
entry in :data:`SOURCES`. The key names a technical ID in one of SAP's development-metadata text
tables; the text itself differs per logon language, the key does not, so one mapping serves every
pack. ``scripts/harvest_lang_texts.py`` reads the keys to compare a pack with SAP (verify) or to
draft a new pack (draft).

A text without an SAP source is :class:`Manual` with a reason: composed titles, WebGUI framework
texts, texts nobody has looked up yet.

``relation`` says how the pack text relates to SAP's text: ``"equal"`` (the pack holds SAP's text)
or ``"fragment"`` (the pack holds a part of it, e.g. "not found" of a message "&1 not found").
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

Relation = Literal["equal", "fragment"]
DataElementLength = Literal["short", "medium", "long", "heading"]


@dataclass(frozen=True, slots=True)
class DataElement:
    """Data element text (``DD04T``): field labels, column headers."""

    name: str
    length: DataElementLength
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class ScreenText:
    """Screen element text (``D021T``): screen texts, tabs, radio button and checkbox texts."""

    program: str
    screen: str
    field: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class GuiFunction:
    """GUI status function text (``RSMPTEXTS``): buttons, menu entries."""

    program: str
    fcode: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class Message:
    """Message text (``T100``): status-bar messages. ``&1`` .. ``&4`` and ``&`` are placeholders."""

    message_class: str
    number: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class DomainValue:
    """Domain fixed-value text (``DD07T``), e.g. a job status."""

    domain: str
    value: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class Transaction:
    """Transaction title (``TSTCT``)."""

    tcode: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class Manual:
    """No SAP source; the reason says why (or "not yet looked up")."""

    reason: str


Source = DataElement | ScreenText | GuiFunction | Message | DomainValue | Transaction | Manual

NOT_LOOKED_UP = Manual("not yet looked up")

SOURCES: Mapping[str, Source] = MappingProxyType(
    {
        "common.display": NOT_LOOKED_UP,
        "common.not_found": NOT_LOOKED_UP,
        "common.does_not_exist": NOT_LOOKED_UP,
        "common.no_entries": NOT_LOOKED_UP,
        "common.row_select_hint": NOT_LOOKED_UP,
        "common.user": NOT_LOOKED_UP,
        "common.program": NOT_LOOKED_UP,
        "keys.names[Ctrl]": NOT_LOOKED_UP,
        "keys.names[Shift]": NOT_LOOKED_UP,
        "keys.names[Alt]": NOT_LOOKED_UP,
        "keys.names[Enter]": NOT_LOOKED_UP,
        "keys.names[Delete]": NOT_LOOKED_UP,
        "keys.names[Escape]": NOT_LOOKED_UP,
        "se09.status[Modifiable]": NOT_LOOKED_UP,
        "se09.status[Released]": NOT_LOOKED_UP,
        "se11.database_table": NOT_LOOKED_UP,
        "se11.data_type": NOT_LOOKED_UP,
        "se11.table_name": NOT_LOOKED_UP,
        "se11.transparent_table": NOT_LOOKED_UP,
        "se11.structure": NOT_LOOKED_UP,
        "se11.short_description": NOT_LOOKED_UP,
        "se11.row_select_full": NOT_LOOKED_UP,
        "se11.dictionary_type": NOT_LOOKED_UP,
        "se16.hit_count_label": NOT_LOOKED_UP,
        "se16.column_selection": NOT_LOOKED_UP,
        "se16.no_values_found": NOT_LOOKED_UP,
        "se24.class_builder": NOT_LOOKED_UP,
        "se24.initial_screen": NOT_LOOKED_UP,
        "se24.display_title": NOT_LOOKED_UP,
        "se24.object_type": NOT_LOOKED_UP,
        "se24.class_label": NOT_LOOKED_UP,
        "se24.interface_label": NOT_LOOKED_UP,
        "se24.visibility[Public]": NOT_LOOKED_UP,
        "se24.visibility[Protected]": NOT_LOOKED_UP,
        "se24.visibility[Private]": NOT_LOOKED_UP,
        "se24.static": NOT_LOOKED_UP,
        "se24.abstract": NOT_LOOKED_UP,
        "se37.initial_screen": NOT_LOOKED_UP,
        "se37.display_title": NOT_LOOKED_UP,
        "se93.initial_screen": NOT_LOOKED_UP,
        "se93.dialog_transaction": NOT_LOOKED_UP,
        "se93.report_transaction": NOT_LOOKED_UP,
        "se93.gui_html": NOT_LOOKED_UP,
        "se93.gui_java": NOT_LOOKED_UP,
        "se93.gui_windows": NOT_LOOKED_UP,
        "se93.screen_number": NOT_LOOKED_UP,
        "se93.selection_screen": NOT_LOOKED_UP,
        "se93.start_with_variant": NOT_LOOKED_UP,
        "se93.transaction_code": NOT_LOOKED_UP,
        "se93.transaction_text": NOT_LOOKED_UP,
        "se93.package": NOT_LOOKED_UP,
        "se93.auth_object": NOT_LOOKED_UP,
        "slg1.initial_screen": NOT_LOOKED_UP,
        "slg1.log_list_screen": NOT_LOOKED_UP,
        "slg1.no_logs_found": NOT_LOOKED_UP,
        "sm30.initial_screen": NOT_LOOKED_UP,
        "sm30.maintain": NOT_LOOKED_UP,
        "sm30.table_view": NOT_LOOKED_UP,
        "sm30.display_view": NOT_LOOKED_UP,
        "sm37.status[Scheduled]": NOT_LOOKED_UP,
        "sm37.status[Released]": NOT_LOOKED_UP,
        "sm37.status[Ready]": NOT_LOOKED_UP,
        "sm37.status[Active]": NOT_LOOKED_UP,
        "sm37.status[Finished]": NOT_LOOKED_UP,
        "sm37.status[Canceled]": NOT_LOOKED_UP,
        "spro.initial_screen": NOT_LOOKED_UP,
        "spro.sap_reference_img": NOT_LOOKED_UP,
        "spro.search_button": NOT_LOOKED_UP,
        "spro.search_dialog": NOT_LOOKED_UP,
        "spro.search_field": NOT_LOOKED_UP,
        "spro.results_dialog": NOT_LOOKED_UP,
        "spro.column_hits": NOT_LOOKED_UP,
        "spro.column_parent": NOT_LOOKED_UP,
        "spro.column_area": NOT_LOOKED_UP,
        "spro.img_heading": NOT_LOOKED_UP,
        "st22.section[what_happened]": NOT_LOOKED_UP,
        "st22.section[how_to_correct]": NOT_LOOKED_UP,
        "st22.section[error_analysis]": NOT_LOOKED_UP,
    }
)
"""Source of every pack field, keyed by its :func:`~sapguimcp.lang.schema.iter_leaves` path."""
