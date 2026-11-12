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
        "abapgit.se38_initial_title": Manual(
            "abapGit UI text; title of the SE38 initial screen, read live in DE and EN"
        ),
        "catalog.screen_header": Manual(
            "SE16 column header of the TSTC screen number (DYPNO); EN seen in a WebGUI capture"
        ),
        "quick_report.empty_patterns": Manual(
            "keyword list recognising an empty result in a quick report, our own report text"
        ),
        "quick_report.execute_button": Manual("button labels of the quick report selection screen, differ per report"),
        "common.display": ScreenText("SAPLSEOD", "1000", "PUSH_DISPLAY", relation="fragment"),
        "common.display_change_toggle": Manual("WebGUI toolbar tooltip of the display/change toggle"),
        "common.initial_screen": Manual("title fragment shared by the initial screens of several transactions"),
        "common.not_found": Message("EU", "046", relation="fragment"),
        "common.does_not_exist": Message("TK", "054", relation="fragment"),
        "common.no_entries": Manual(
            "SAP text differs: ECC release has 'Es wurden keine Einträge gemäß Selektion gefunden' (SV 004),"
            " pack DE has 'Keine Einträge gefunden'"
        ),
        "common.row_select_hint": Manual("WebGUI framework text: ARIA hint of a selectable table row"),
        "common.user": DataElement("XUBNAME", "medium"),
        "common.program": DataElement("PROGNAME", "short"),
        "popup.type_error": Manual("keyword list classifying popups by title or text"),
        "popup.type_info": Manual("keyword list classifying popups by title or text"),
        "popup.type_confirm": Manual("keyword list classifying popups by title or text"),
        "popup.inactive_objects": Manual("popup title seen live; no matching text in D021T, T100 or RSMPTEXTS"),
        "popup.original_language_title": Manual(
            "GUI title of screen SAPLSETX 0100 (title bar, not a D021T text); the T100 messages about the"
            " original language have other wording"
        ),
        "popup.original_language_hint": Manual("regex over the desktop window title of the same popup"),
        "popup.maintain_in_original": ScreenText("SAPLSETX", "0100", "PUSH1"),
        "popup.button_labels": Manual("standard popup button labels, several GUI statuses"),
        "popup.close": Manual("WebGUI framework tooltip of a popup's close control"),
        "status_type.error": Manual("keyword list inferring the message type from its text"),
        "status_type.warning": Manual("keyword list inferring the message type from its text"),
        "status_type.success": Manual("keyword list inferring the message type from its text"),
        "status_type.noise": Manual("WebGUI framework texts of the message bar (label, buttons, emphasis)"),
        "status_type.success_prefix": Manual("WebGUI framework text: message type in the message-bar ARIA label"),
        "status_type.error_prefix": Manual("WebGUI framework text: message type in the message-bar ARIA label"),
        "status_type.message_bar": Manual("WebGUI framework text: the message bar's ARIA label"),
        "status_type.check_success": Manual("fragments of several syntax check and activation messages"),
        "status_type.check_error": Manual("fragment of several syntax check messages"),
        "status_type.activation_confirmed": Manual("fragment of several activation messages"),
        "status_type.activation_denied": Manual("negating fragments of activation messages"),
        "session_pages.already_logged_on": Manual("WebGUI logon page (ICF), not in SAP's text tables"),
        "session_pages.continue_button": Manual("WebGUI logon page (ICF), not in SAP's text tables"),
        "session_pages.timed_out": Manual("WebGUI timeout and logoff pages (ICF), not in SAP's text tables"),
        "session_pages.settings_menu": Manual("WebGUI framework tooltip of the settings menu"),
        "session_pages.settings_stem": Manual("stem of the WebGUI settings menu tooltip"),
        "session_pages.okcode_option": Manual("WebGUI framework settings menu entry"),
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
        "se09.list_region": Manual("WebGUI ARIA label of the ABAP list region; EN value not yet read live (#1044)"),
        "se09.organizer_title": Transaction("SE09"),
        "se09.request_word": Manual("word inside SE09 list texts and messages, no single source"),
        "se11.database_table": ScreenText("SAPLSD_ENTRY", "1000", "RSRD1-TBMA"),
        "se11.data_type": DataElement("DATATYPE_D", "medium"),
        "se11.table_name": DataElement("TABNAME", "medium"),
        "se11.transparent_table": Manual(
            "SAP text differs: DE domain value TABCLASS TRANSP is 'Transparente Tabelle', pack has"
            " 'Transp.Tabelle' (EN 'Transparent table' matches)"
        ),
        "se11.structure": DomainValue("TABCLASS", "INTTAB"),
        "se11.short_description": Manual(
            "SAP text differs: EN data element DDTEXT is 'Short text', pack has 'Short Description'"
        ),
        "se11.row_select_full": Manual("WebGUI framework text: ARIA hint of a selectable table row"),
        "se11.data_type_name_label": Manual("quick info of the DDIC type name field, WebGUI input title"),
        "se16.hit_count_label": ScreenText("SAPLSE16N", "0200", "TEXT2"),
        "se16.column_selection": Manual("ALV list framework text (row selection column), not in D021T"),
        "se16.no_values_found": Message("WUSL", "002", relation="fragment"),
        "se16.table_label": ScreenText("SAPLSE16N", "0100", "SEARCHTAB"),
        "se16.max_hits_label": ScreenText("SAPLSE16N", "0100", "TEXTMAX"),
        "se16.empty_cell": Manual("WebGUI framework text of empty grid rows"),
        "se16.table_not_found": Message("TK", "054", relation="fragment"),
        "se16.selection_columns": Manual("column headers of the selection grid, composed from several data elements"),
        "se16.results_title": Manual("composed title fragment of the result list"),
        "se24.class_builder": Manual(
            "SAP text differs: transaction SE24 is 'ABAP Class Builder' in both languages; pack DE has 'Klassenpflege'"
        ),
        "se24.initial_screen": Manual(
            "window title of the class builder initial screen (titlebar, not in the supported text tables)"
        ),
        "se24.display_title": Manual("composed window title of the class builder"),
        "se24.object_type": ScreenText("SAPLSEOD", "1000", "*DY_1000-CLIF"),
        "se24.class_label": ScreenText("SAPLSEOD", "1000", "DY_1000-CHECK_CLASS"),
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
        "se37.initial_screen": Manual(
            "window title of the function builder initial screen (titlebar, not in the supported text tables)"
        ),
        "se37.display_title": Manual("composed window title of the function builder"),
        "se37.function_builder": Manual("title fragment of the function builder"),
        "se37.fm_field_label": ScreenText("SAPLSEUF", "0100", "NAME1"),
        "se37.not_found": Message("FL", "110", relation="fragment"),
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
        "se93.initial_screen": Manual(
            "SAP text differs: transaction SE93 is 'Maintain Transaction Codes' / 'Pflege Transaktionscodes';"
            " pack DE has 'Transaktionspflege'"
        ),
        "se93.dialog_transaction": Manual("EN screen text SAPLSEUK 0300 RSSTCD-S_TRANS; no DE text in D021T"),
        "se93.report_transaction": Manual("EN screen text SAPLSEUK 0300 RSSTCD-S_REPORT; no DE text in D021T"),
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
        "slg1.initial_screen": Manual(
            "window title of the log selection screen (titlebar, not in the supported text tables)"
        ),
        "slg1.log_list_screen": Transaction("SLG1", relation="fragment"),
        # The variants besides BL 208 are shorter fragments the desktop tool always accepted (no T100 source).
        "slg1.no_logs_found": Message("BL", "208", relation="fragment"),
        "slg1.log_object": Manual("selection text of report SBAL_DISPLAY (text pool), not in D021T"),
        "slg1.log_subobject": Manual("selection text of report SBAL_DISPLAY (text pool), not in D021T"),
        "slg1.external_id": Manual("selection text of report SBAL_DISPLAY (text pool), not in D021T"),
        "slg1.from_datetime": Manual("selection text of report SBAL_DISPLAY (text pool), not in D021T"),
        "slg1.to_datetime": Manual("selection text of report SBAL_DISPLAY (text pool), not in D021T"),
        "slg1.log_number": Manual("list column title of the log grid, not looked up"),
        "slg1.col_date": Manual("list column title of the log grid, not looked up"),
        "slg1.col_time": Manual("list column title of the log grid, not looked up"),
        "slg1.col_messages": Manual("list column title of the log grid, not looked up"),
        "slg1.empty_cell": Manual("WebGUI framework text for an empty grid cell"),
        "sm30.initial_screen": Manual(
            "SAP text differs: transaction SM30 is 'Call View Maintenance' / 'Aufruf View-Pflege'; pack has"
            " 'Table View Maintenance' / 'Tabellensicht-Pflege'"
        ),
        "sm30.maintain": Manual(
            "SAP text differs: EN screen text SAPMSVMA 0100 UPDATE_PUSH is 'Edit' on the S/4HANA release "
            "('Maintain' on the ECC release); pack has 'Maintain'"
        ),
        "sm30.table_view": ScreenText("SAPMSVMA", "0100", "VIEWNAME"),
        "sm30.display_view": Manual("view-type word inside the composed SM30 titles"),
        "sm30.view_not_found": Message("SV", "164", relation="fragment"),
        "sm30.no_maintenance_dialog": Manual(
            "no single T100 message has the fragment in both languages (SV 432 EN only, SV 790 DE only)"
        ),
        "sm30.view_title": Manual("composed window title of the view maintenance"),
        "sm30.row_count": Manual("WebGUI composed status text of the entry counter"),
        "sm37.status[Scheduled]": ScreenText("SAPLBTCH", "2170", "BTCH2170-PRELIM"),
        "sm37.status[Released]": ScreenText("SAPLBTCH", "2170", "BTCH2170-SCHEDUL"),
        "sm37.status[Ready]": ScreenText("SAPLBTCH", "2170", "BTCH2170-READY"),
        "sm37.status[Active]": ScreenText("SAPLBTCH", "2170", "BTCH2170-RUNNING"),
        "sm37.status[Finished]": ScreenText("SAPLBTCH", "2170", "BTCH2170-FINISHED"),
        "sm37.status[Canceled]": ScreenText("SAPLBTCH", "2170", "BTCH2170-ABORTED"),
        "sm37.col_status": Manual("list column title of the job overview, not looked up"),
        "sm37.job_name": ScreenText("SAPLBTCH", "2170", "JOBNAME"),
        "sm37.user_name": ScreenText("SAPLBTCH", "2170", "USERNAME"),
        "sm37.from_date": Manual("WebGUI label: 'von' / 'From' (SAPLBTCH 2170 FROM) plus the date field's own label"),
        "sm37.to_date": Manual("WebGUI label: 'bis' / 'To' (SAPLBTCH 2170 TO) plus the date field's own label"),
        "sm37.job_log_button": GuiFunction("SAPLBTCH", "JPRO"),
        "sm37.job_log_heading": Manual("title of the job log list, not in the GUI status"),
        "sm37.job_log_title_ecc": Manual("title of the job log screen on the ECC release, not looked up"),
        "sm37.job_list_heading": Manual("title of the job overview list, not looked up"),
        "sm37.no_jobs": Message("BT", "145", relation="fragment"),
        "sm37.select_hint": Manual("hint line of the classic list, not looked up"),
        "sm37.selected_hint": Manual("footer line of the classic list, not looked up"),
        "sm37.event_driven": Manual("start condition line of the classic list, not looked up"),
        "sm37.abap_program": Manual("step line of the classic list, not looked up"),
        "sm37.col_start_date": Manual("list column title of the job overview, not looked up"),
        "sm37.col_start_time": Manual("list column title of the job overview, not looked up"),
        "sm37.col_duration": Manual("list column title of the job overview, not looked up"),
        "sm37.col_created_by": Manual("list column title of the job overview, not looked up"),
        "sm37.col_client": Manual("list column title of the job overview, not looked up"),
        "spro.initial_screen": Manual(
            "SAP text differs: transaction SPRO is 'Customizing - Edit Project' in both languages; pack has the"
            " screen titles 'Customizing: Projektbearbeitung' / 'Customizing: Execute Project'"
        ),
        "spro.sap_reference_img": Manual(
            "IMG tree and toolbar texts of the customizing tool, not found in the supported text tables"
        ),
        "spro.search_button": Manual(
            "IMG tree and toolbar texts of the customizing tool, not found in the supported text tables"
        ),
        "spro.search_dialog": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.search_field": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.results_dialog": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.column_hits": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.column_parent": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.column_area": Manual("IMG search dialog texts, not found in the supported text tables"),
        "spro.img_heading": Manual("window title of the IMG display (titlebar, not in the supported text tables)"),
        "st22.section[what_happened]": Manual("heading of the dump detail text (spec section 9)"),
        "st22.section[how_to_correct]": Manual("heading of the dump detail text (spec section 9)"),
        "st22.section[error_analysis]": Manual("heading of the dump detail text (spec section 9)"),
        "st22.today": Manual("pushbutton text of report RSSHOWRABAX (selection screen), not in D021T"),
        "st22.yesterday": Manual("pushbutton text of report RSSHOWRABAX (selection screen), not in D021T"),
        "st22.date_field": Manual("selection text of report RSSHOWRABAX (text pool), not in D021T"),
        "st22.runtime_errors": Manual("button and heading text of report RSSHOWRABAX, not in D021T"),
        "st22.no_dumps": Manual("union of the former tool and parser lists, status text of the ST22 list"),
        "st22.col_time": Manual("list column title of the dump list, not looked up"),
        "st22.col_program": Manual("list column title of the dump list, not looked up"),
        "st22.col_error_type": Manual("list column title of the dump list, not looked up"),
        "st22.col_short_text": Manual("list column title of the dump list, not looked up"),
        "st22.call_stack_heading": Manual("heading of the dump detail text (spec section 9)"),
        "st22.other_headings": Manual("headings of the dump detail text (spec section 9)"),
        "st22.source_code_start": Manual("heading of the dump detail text (spec section 9)"),
        "st22.source_code_of": Manual("text of the dump detail"),
        "st22.source_line": Manual("text of the dump detail"),
        "st22.line": Manual("text of the dump detail"),
    }
)
"""Source of every pack field, keyed by its :func:`~sapguimcp.lang.schema.iter_leaves` path."""
