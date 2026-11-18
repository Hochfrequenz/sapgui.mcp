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
        "popup.abapgit_error_keywords": Manual("abapGit UI text"),
        "abapgit.status_error": Manual("abapGit UI text"),
        "abapgit.screen_errors": Manual("abapGit UI text"),
        "popup.abapgit_transport_required": Manual("abapGit UI text"),
        "popup.abapgit_no_task": Manual("abapGit UI text"),
        "popup.abapgit_button_labels": Manual("abapGit UI text"),
        "popup.abapgit_inactive_objects": Manual("abapGit UI text"),
        "catalog.screen_header": Manual(
            "SE16 column header of the TSTC screen number (DYPNO); EN seen in a WebGUI capture"
        ),
        "common.display": ScreenText("SAPLSEOD", "1000", "PUSH_DISPLAY", relation="fragment"),
        "common.not_found": Message("EU", "046", relation="fragment"),
        "common.does_not_exist": Message("TK", "054", relation="fragment"),
        "common.no_entries": Manual(
            "SAP text differs: ECC release has 'Es wurden keine Einträge gemäß Selektion gefunden' (SV 004),"
            " pack DE has 'Keine Einträge gefunden'"
        ),
        "common.user": DataElement("XUBNAME", "medium"),
        "common.program": DataElement("PROGNAME", "short"),
        "popup.type_error": Manual("keyword list classifying popups by title or text"),
        "popup.type_info": Manual("keyword list classifying popups by title or text"),
        "popup.type_confirm": Manual("keyword list classifying popups by title or text"),
        "popup.inactive_objects": Manual("popup title seen live; no matching text in D021T, T100 or RSMPTEXTS"),
        "popup.original_language_hint": Manual("regex over the desktop window title of the same popup"),
        "popup.maintain_in_original": ScreenText("SAPLSETX", "0100", "PUSH1"),
        "status_type.activation_confirmed": Manual("fragment of several activation messages"),
        "status_type.activation_denied": Manual("negating fragments of activation messages"),
        "session_pages.debugger_window": Manual("SAP GUI window title of the ABAP debugger"),
        "keys.names[Ctrl]": Manual("keyboard key name of the SAP GUI client, not in SAP's text tables"),
        "keys.names[Shift]": Manual("keyboard key name of the SAP GUI client, not in SAP's text tables"),
        "keys.names[Alt]": Manual("keyboard key name of the SAP GUI client, not in SAP's text tables"),
        "keys.names[Enter]": Manual("keyboard key name of the SAP GUI client, not in SAP's text tables"),
        "keys.names[Delete]": Manual("keyboard key name of the SAP GUI client, not in SAP's text tables"),
        "keys.names[Escape]": Manual("keyboard key name of the SAP GUI client, not in SAP's text tables"),
        "se09.status[Modifiable]": DomainValue("TRSTATUS", "D"),
        "se09.status[Released]": DomainValue("TRSTATUS", "R"),
        "se09.display_button": ScreenText("SAPLSEOD", "1000", "PUSH_DISPLAY", relation="fragment"),
        "se09.workbench_requests": Manual(
            "SAP text differs: TRFUNCTION K is the singular 'Workbench-Auftrag' / 'Workbench Request'; the SE09"
            " tree node holds the plural"
        ),
        "se09.customizing_requests": Manual(
            "SAP text differs: TRFUNCTION W is the singular 'Customizing-Auftrag' / 'Customizing Request'; the"
            " SE09 tree node holds the plural"
        ),
        "se09.expand": Manual("tree toolbar tooltip, generic text of many GUI statuses"),
        "se09.compress": Manual("tree toolbar tooltip, generic text of many GUI statuses"),
        "se11.table_name": DataElement("TABNAME", "medium"),
        "se16.results_title": Manual("composed title fragment of the result list"),
        "se24.initial_screen": Manual(
            "window title of the class builder initial screen (titlebar, not in the supported text tables)"
        ),
        "se24.object_type": ScreenText("SAPLSEOD", "1000", "*DY_1000-CLIF"),
        "se24.interface_label": ScreenText("SAPLSEOD", "1000", "DY_1000-CHECK_INTERFACE"),
        "se24.visibility[Public]": DomainValue("SEOEXPOSE", "2"),
        "se24.visibility[Protected]": DomainValue("SEOEXPOSE", "1"),
        "se24.visibility[Private]": DomainValue("SEOEXPOSE", "0"),
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
        "se37.fm_field_label": ScreenText("SAPLSEUF", "0100", "NAME1"),
        "se37.attributes_tab": Manual("tab title of the function builder tab strip"),
        "se37.import_tab": Manual("tab title of the function builder tab strip"),
        "se37.export_tab": Manual("tab title of the function builder tab strip"),
        "se37.changing_tab": Manual("tab title of the function builder tab strip"),
        "se37.tables_tab": Manual("tab title of the function builder tab strip"),
        "se37.exceptions_tab": Manual("tab title of the function builder tab strip"),
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
        "se93.transaction_code": ScreenText("SAPLSEUK", "0310", "TSTC-TCODE"),
        # The variants besides BL 208 are shorter fragments the desktop tool always accepted (no T100 source).
        "slg1.no_logs_found": Message("BL", "208", relation="fragment"),
        "slg1.log_object": Manual("selection text of report SBAL_DISPLAY (text pool), not in D021T"),
        "slg1.log_subobject": Manual("selection text of report SBAL_DISPLAY (text pool), not in D021T"),
        "slg1.external_id": Manual("selection text of report SBAL_DISPLAY (text pool), not in D021T"),
        "slg1.log_number": Manual("list column title of the log grid, not looked up"),
        "slg1.col_date": Manual("list column title of the log grid, not looked up"),
        "slg1.col_time": Manual("list column title of the log grid, not looked up"),
        "slg1.col_messages": Manual("list column title of the log grid, not looked up"),
        "sm30.maintain": Manual(
            "SAP text differs: EN screen text SAPMSVMA 0100 UPDATE_PUSH is 'Edit' on the S/4HANA release "
            "('Maintain' on the ECC release); pack has 'Maintain'"
        ),
        "sm30.table_view": ScreenText("SAPMSVMA", "0100", "VIEWNAME"),
        "sm30.display_view": Manual("view-type word inside the composed SM30 titles"),
        "sm37.status[Scheduled]": ScreenText("SAPLBTCH", "2170", "BTCH2170-PRELIM"),
        "sm37.status[Released]": ScreenText("SAPLBTCH", "2170", "BTCH2170-SCHEDUL"),
        "sm37.status[Ready]": ScreenText("SAPLBTCH", "2170", "BTCH2170-READY"),
        "sm37.status[Active]": ScreenText("SAPLBTCH", "2170", "BTCH2170-RUNNING"),
        "sm37.status[Finished]": ScreenText("SAPLBTCH", "2170", "BTCH2170-FINISHED"),
        "sm37.status[Canceled]": ScreenText("SAPLBTCH", "2170", "BTCH2170-ABORTED"),
        "sm37.col_status": Manual("list column title of the job overview, not looked up"),
        "sm37.job_name": ScreenText("SAPLBTCH", "2170", "JOBNAME"),
        "sm37.job_log_button": GuiFunction("SAPLBTCH", "JPRO"),
        "sm37.job_log_heading": Manual("title of the job log list, not in the GUI status"),
        "sm37.job_log_title_ecc": Manual("title of the job log screen on the ECC release, not looked up"),
        "sm37.no_jobs": Message("BT", "145", relation="fragment"),
        "sm37.select_hint": Manual("hint line of the classic list, not looked up"),
        "sm37.selected_hint": Manual("footer line of the classic list, not looked up"),
        "sm37.col_start_date": Manual("list column title of the job overview, not looked up"),
        "sm37.col_start_time": Manual("list column title of the job overview, not looked up"),
        "sm37.col_duration": Manual("list column title of the job overview, not looked up"),
        "sm37.col_created_by": Manual("list column title of the job overview, not looked up"),
        "sm37.col_client": Manual("list column title of the job overview, not looked up"),
        "spro.sap_reference_img": Manual(
            "IMG tree and toolbar texts of the customizing tool, not found in the supported text tables"
        ),
        "spro.search_dialog": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.search_field": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.column_hits": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.column_parent": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.column_area": Manual("IMG search dialog texts, not found in the supported text tables"),
        "st22.section[what_happened]": Manual("heading of the dump detail text (spec section 9)"),
        "st22.section[how_to_correct]": Manual("heading of the dump detail text (spec section 9)"),
        "st22.section[error_analysis]": Manual("heading of the dump detail text (spec section 9)"),
        "st22.today": Manual("pushbutton text of report RSSHOWRABAX (selection screen), not in D021T"),
        "st22.yesterday": Manual("pushbutton text of report RSSHOWRABAX (selection screen), not in D021T"),
        "st22.date_field": Manual("selection text of report RSSHOWRABAX (text pool), not in D021T"),
        "st22.no_dumps": Manual("union of the former tool and parser lists, status text of the ST22 list"),
        "st22.col_time": Manual("list column title of the dump list, not looked up"),
        "st22.col_program": Manual("list column title of the dump list, not looked up"),
        "st22.col_error_type": Manual("list column title of the dump list, not looked up"),
        "st22.col_short_text": Manual("list column title of the dump list, not looked up"),
        "st22.call_stack_heading": Manual("heading of the dump detail text (spec section 9)"),
        "st22.other_headings": Manual("headings of the dump detail text (spec section 9)"),
    }
)
"""Source of every pack field, keyed by its :func:`~sapguimcp.lang.schema.iter_leaves` path."""
