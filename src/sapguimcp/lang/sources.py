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
        "common.not_found": Message("EU", "046", relation="fragment"),
        "common.does_not_exist": Message("TK", "054", relation="fragment"),
        "common.no_entries": Manual(
            "SAP text differs: ECC release has 'Es wurden keine Einträge gemäß Selektion gefunden' (SV 004),"
            " pack DE has 'Keine Einträge gefunden'"
        ),
        "common.row_select_hint": NOT_LOOKED_UP,
        "common.user": DataElement("XUBNAME", "medium"),
        "common.program": DataElement("PROGNAME", "short"),
        "keys.names[Ctrl]": NOT_LOOKED_UP,
        "keys.names[Shift]": NOT_LOOKED_UP,
        "keys.names[Alt]": NOT_LOOKED_UP,
        "keys.names[Enter]": NOT_LOOKED_UP,
        "keys.names[Delete]": NOT_LOOKED_UP,
        "keys.names[Escape]": NOT_LOOKED_UP,
        "se09.status[Modifiable]": DomainValue("TRSTATUS", "D"),
        "se09.status[Released]": DomainValue("TRSTATUS", "R"),
        "se11.database_table": ScreenText("SAPLSD_ENTRY", "1000", "RSRD1-TBMA"),
        "se11.data_type": DataElement("DATATYPE_D", "medium"),
        "se11.table_name": DataElement("TABNAME", "medium"),
        "se11.transparent_table": NOT_LOOKED_UP,
        "se11.structure": NOT_LOOKED_UP,
        "se11.short_description": Manual(
            "SAP text differs: EN data element DDTEXT is 'Short text', pack has 'Short Description'"
        ),
        "se11.row_select_full": NOT_LOOKED_UP,
        "se11.dictionary_type": NOT_LOOKED_UP,
        "se16.hit_count_label": NOT_LOOKED_UP,
        "se16.column_selection": NOT_LOOKED_UP,
        "se16.no_values_found": NOT_LOOKED_UP,
        "se24.class_builder": NOT_LOOKED_UP,
        "se24.initial_screen": NOT_LOOKED_UP,
        "se24.display_title": NOT_LOOKED_UP,
        "se24.object_type": NOT_LOOKED_UP,
        "se24.class_label": ScreenText("SAPLSEOD", "1000", "DY_1000-CHECK_CLASS"),
        "se24.interface_label": NOT_LOOKED_UP,
        "se24.visibility[Public]": NOT_LOOKED_UP,
        "se24.visibility[Protected]": NOT_LOOKED_UP,
        "se24.visibility[Private]": NOT_LOOKED_UP,
        "se24.static": ScreenText("SAPLSEOD", "0351", "DY_0203-CHECK_CLASS_METHOD"),
        "se24.abstract": Manual("screen text SAPLSEOD 0351 VSEOMETHOD-MTDABSTRCT exists on the S/4HANA release only"),
        "se24.constant": DomainValue("SEOATTDECL", "2"),
        "se24.class_field_label": Manual("input field label/title of the class builder initial screen"),
        "se24.methods_tab": Manual("tab title of the class builder tab strip"),
        "se24.attributes_tab": Manual("tab title of the class builder tab strip"),
        "se24.interfaces_tab": Manual("tab title of the class builder tab strip"),
        "se24.properties_tab": Manual("tab title of the class builder tab strip"),
        "se24.source_button": Manual("button text of the class builder method list"),
        "se24.method_column": Manual("table control column title of the methods tab"),
        "se24.attribute_column": Manual("table control column title of the attributes tab"),
        "se24.kind_column": Manual("table control column title of the methods and attributes tabs"),
        "se24.visibility_column": Manual("table control column title of the methods and attributes tabs"),
        "se24.description_column": Manual("table control column title of the class builder tabs"),
        "se24.type_ref_column": Manual("table control column title of the attributes tab"),
        "se24.initial_value_column": Manual("table control column title of the attributes tab"),
        "se37.initial_screen": NOT_LOOKED_UP,
        "se37.display_title": NOT_LOOKED_UP,
        "se37.function_builder": Manual("title fragment of the function builder"),
        "se37.fm_field_label": NOT_LOOKED_UP,
        "se37.not_found": NOT_LOOKED_UP,
        "se37.attributes_tab": Manual("tab title of the function builder tab strip"),
        "se37.import_tab": Manual("tab title of the function builder tab strip"),
        "se37.export_tab": Manual("tab title of the function builder tab strip"),
        "se37.changing_tab": Manual("tab title of the function builder tab strip"),
        "se37.tables_tab": Manual("tab title of the function builder tab strip"),
        "se37.exceptions_tab": Manual("tab title of the function builder tab strip"),
        "se37.source_tab": Manual("tab title of the function builder tab strip"),
        "se37.parameter_name_column": Manual("table control column title of the signature tabs"),
        "se37.typing_column": Manual("table control column title of the signature tabs"),
        "se37.type_ref_column": Manual("table control column title of the signature tabs"),
        "se37.default_column": Manual("table control column title of the signature tabs"),
        "se37.optional_column": Manual("table control column title of the signature tabs"),
        "se37.pass_value_column": Manual("table control column title of the signature tabs"),
        "se37.short_text_column": Manual("table control column title of the signature and exception tabs"),
        "se37.exception_column": Manual("table control column title of the exceptions tab"),
        "se38.initial_screen": Manual("title fragment of the ABAP editor initial screen"),
        "se38.program_field_title": Manual("title attribute of the program name input"),
        "se93.initial_screen": NOT_LOOKED_UP,
        "se93.dialog_transaction": NOT_LOOKED_UP,
        "se93.report_transaction": NOT_LOOKED_UP,
        "se93.gui_html": ScreenText("SAPLSRT2", "0700", "D700_TCODE_WEBGUI"),
        "se93.gui_java": ScreenText("SAPLSRT2", "0700", "D700_TCODE_PLATGUI"),
        "se93.gui_windows": ScreenText("SAPLSRT2", "0700", "D700_TCODE_WINGUI"),
        "se93.screen_number": Manual(
            "SAP text differs: EN screen text is 'Dynpro Number' on the S/4HANA release "
            "('Screen number' on the ECC release); pack has 'Screen number'"
        ),
        "se93.selection_screen": ScreenText("SAPLSEUK", "0320", "TSTC-DYPNO"),
        "se93.start_with_variant": ScreenText("SAPLSEUK", "0320", "RSSTCD-REPO_VARI"),
        "se93.transaction_code": ScreenText("SAPLSEUK", "0310", "TSTC-TCODE"),
        "se93.transaction_text": ScreenText("SAPLSEUK", "0310", "TSTCT-TTEXT"),
        "se93.package": DataElement("DEVCLASS", "medium"),
        "se93.auth_object": ScreenText("SAPLSEUK", "0310", "TSTCA-OBJCT"),
        "slg1.initial_screen": NOT_LOOKED_UP,
        "slg1.log_list_screen": NOT_LOOKED_UP,
        "slg1.no_logs_found": Message("BL", "208", relation="fragment"),
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
