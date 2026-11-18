"""Which backend reads each language-pack text (#1099, desktop/WebGUI split preparation).

Every field of a language pack section (every path of :func:`sapguimcp.lang.schema.iter_leaves`,
without the ``[key]`` of a canonical mapping) has exactly one entry in :data:`BACKEND_OF`:

- ``DESKTOP``: only the SAP GUI for Windows (COM) backend reads the text.
- ``WEBGUI``: only the WebGUI backend reads it (including the JavaScript under
  ``backend/webgui/js`` through ``Text.for_js()``).
- ``BOTH``: shared code reads it, or both backends do. ``BOTH`` is also the safe choice when
  unsure: the text is kept on both sides after the split.

After the fork, each repository deletes the fields tagged for the other backend from
``schema.py``, from every pack (``de.py``, ``en.py``, ``it.py``), from ``sources.py`` and from
this table. Nothing else needs a decision.

The tags are derived from the source, not from intent: ``unittests/lang/test_backend_tags.py``
scans the code for every read of every field and fails when a field has no tag, when a tag does
not match where the field is read, and when a field is read nowhere. A new field must get its tag
here; a refactoring that moves a read between backend-specific and shared code must update it.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class Backend(StrEnum):
    """The consumer of a language-pack text."""

    DESKTOP = "desktop"
    WEBGUI = "webgui"
    BOTH = "both"


_TAGS: dict[str, Backend] = {
    # common
    "common.display": Backend.BOTH,
    "common.display_change_toggle": Backend.BOTH,
    "common.initial_screen": Backend.BOTH,
    "common.not_found": Backend.BOTH,
    "common.does_not_exist": Backend.BOTH,
    "common.no_entries": Backend.DESKTOP,
    "common.row_select_hint": Backend.WEBGUI,
    "common.user": Backend.BOTH,
    "common.program": Backend.BOTH,
    # popup
    "popup.type_error": Backend.DESKTOP,
    "popup.type_info": Backend.DESKTOP,
    "popup.type_confirm": Backend.DESKTOP,
    "popup.inactive_objects": Backend.DESKTOP,
    "popup.original_language_title": Backend.WEBGUI,
    "popup.original_language_hint": Backend.DESKTOP,
    "popup.maintain_in_original": Backend.DESKTOP,
    "popup.button_labels": Backend.WEBGUI,
    "popup.close": Backend.WEBGUI,
    "popup.abapgit_error_keywords": Backend.BOTH,
    "popup.abapgit_button_labels": Backend.BOTH,
    "popup.abapgit_inactive_objects": Backend.BOTH,
    "popup.abapgit_transport_required": Backend.BOTH,
    "popup.abapgit_no_task": Backend.BOTH,
    # status_type
    "status_type.error": Backend.WEBGUI,
    "status_type.warning": Backend.WEBGUI,
    "status_type.success": Backend.WEBGUI,
    "status_type.noise": Backend.WEBGUI,
    "status_type.success_prefix": Backend.WEBGUI,
    "status_type.error_prefix": Backend.WEBGUI,
    "status_type.message_bar": Backend.WEBGUI,
    "status_type.check_success": Backend.WEBGUI,
    "status_type.check_error": Backend.WEBGUI,
    "status_type.activation_confirmed": Backend.DESKTOP,
    "status_type.activation_denied": Backend.DESKTOP,
    # session_pages
    "session_pages.already_logged_on": Backend.WEBGUI,
    "session_pages.continue_button": Backend.WEBGUI,
    "session_pages.timed_out": Backend.WEBGUI,
    "session_pages.settings_menu": Backend.WEBGUI,
    "session_pages.settings_stem": Backend.BOTH,
    "session_pages.okcode_option": Backend.WEBGUI,
    "session_pages.debugger_window": Backend.DESKTOP,
    # keys
    "keys.names": Backend.BOTH,
    # abapgit
    "abapgit.status_error": Backend.BOTH,
    "abapgit.screen_errors": Backend.BOTH,
    "abapgit.se38_initial_title": Backend.WEBGUI,
    # catalog
    "catalog.screen_header": Backend.BOTH,
    # quick_report
    "quick_report.empty_patterns": Backend.WEBGUI,
    "quick_report.execute_button": Backend.WEBGUI,
    # se09
    "se09.status": Backend.BOTH,
    "se09.display_button": Backend.DESKTOP,
    "se09.workbench_requests": Backend.BOTH,
    "se09.customizing_requests": Backend.BOTH,
    "se09.expand": Backend.DESKTOP,
    "se09.compress": Backend.DESKTOP,
    "se09.list_region": Backend.WEBGUI,
    "se09.organizer_title": Backend.WEBGUI,
    "se09.request_word": Backend.WEBGUI,
    # se11
    "se11.database_table": Backend.WEBGUI,
    "se11.data_type": Backend.WEBGUI,
    "se11.table_name": Backend.BOTH,
    "se11.transparent_table": Backend.WEBGUI,
    "se11.structure": Backend.WEBGUI,
    "se11.short_description": Backend.WEBGUI,
    "se11.row_select_full": Backend.WEBGUI,
    "se11.data_type_name_label": Backend.WEBGUI,
    # se16
    "se16.hit_count_label": Backend.WEBGUI,
    "se16.column_selection": Backend.WEBGUI,
    "se16.no_values_found": Backend.WEBGUI,
    "se16.table_label": Backend.WEBGUI,
    "se16.max_hits_label": Backend.WEBGUI,
    "se16.empty_cell": Backend.WEBGUI,
    "se16.table_not_found": Backend.WEBGUI,
    "se16.selection_columns": Backend.WEBGUI,
    "se16.results_title": Backend.DESKTOP,
    # se24
    "se24.class_builder": Backend.WEBGUI,
    "se24.initial_screen": Backend.DESKTOP,
    "se24.display_title": Backend.WEBGUI,
    "se24.object_type": Backend.DESKTOP,
    "se24.class_label": Backend.WEBGUI,
    "se24.interface_label": Backend.DESKTOP,
    "se24.visibility": Backend.BOTH,
    "se24.static": Backend.BOTH,
    "se24.abstract": Backend.BOTH,
    "se24.constant": Backend.BOTH,
    "se24.class_field_label": Backend.DESKTOP,
    "se24.methods_tab": Backend.DESKTOP,
    "se24.attributes_tab": Backend.DESKTOP,
    "se24.interfaces_tab": Backend.DESKTOP,
    "se24.properties_tab": Backend.DESKTOP,
    "se24.source_button": Backend.DESKTOP,
    "se24.method_column": Backend.BOTH,
    "se24.attribute_column": Backend.BOTH,
    "se24.kind_column": Backend.BOTH,
    "se24.visibility_column": Backend.BOTH,
    "se24.description_column": Backend.BOTH,
    "se24.type_ref_column": Backend.BOTH,
    "se24.initial_value_column": Backend.BOTH,
    # se37
    "se37.initial_screen": Backend.WEBGUI,
    "se37.display_title": Backend.WEBGUI,
    "se37.function_builder": Backend.WEBGUI,
    "se37.fm_field_label": Backend.DESKTOP,
    "se37.not_found": Backend.WEBGUI,
    "se37.attributes_tab": Backend.DESKTOP,
    "se37.import_tab": Backend.DESKTOP,
    "se37.export_tab": Backend.DESKTOP,
    "se37.changing_tab": Backend.DESKTOP,
    "se37.tables_tab": Backend.DESKTOP,
    "se37.exceptions_tab": Backend.DESKTOP,
    "se37.source_tab": Backend.WEBGUI,
    "se37.parameter_name_column": Backend.BOTH,
    "se37.typing_column": Backend.BOTH,
    "se37.type_ref_column": Backend.BOTH,
    "se37.default_column": Backend.BOTH,
    "se37.optional_column": Backend.BOTH,
    "se37.pass_value_column": Backend.BOTH,
    "se37.short_text_column": Backend.BOTH,
    "se37.exception_column": Backend.DESKTOP,
    # se38
    "se38.initial_screen": Backend.DESKTOP,
    "se38.program_field_title": Backend.DESKTOP,
    # se93
    "se93.initial_screen": Backend.WEBGUI,
    "se93.dialog_transaction": Backend.WEBGUI,
    "se93.report_transaction": Backend.WEBGUI,
    "se93.gui_html": Backend.WEBGUI,
    "se93.gui_java": Backend.WEBGUI,
    "se93.gui_windows": Backend.WEBGUI,
    "se93.screen_number": Backend.WEBGUI,
    "se93.selection_screen": Backend.WEBGUI,
    "se93.start_with_variant": Backend.WEBGUI,
    "se93.transaction_code": Backend.BOTH,
    "se93.transaction_text": Backend.WEBGUI,
    "se93.package": Backend.WEBGUI,
    "se93.auth_object": Backend.WEBGUI,
    # slg1
    "slg1.initial_screen": Backend.WEBGUI,
    "slg1.log_list_screen": Backend.WEBGUI,
    "slg1.no_logs_found": Backend.DESKTOP,
    "slg1.log_object": Backend.DESKTOP,
    "slg1.log_subobject": Backend.DESKTOP,
    "slg1.external_id": Backend.DESKTOP,
    "slg1.from_datetime": Backend.WEBGUI,
    "slg1.to_datetime": Backend.WEBGUI,
    "slg1.log_number": Backend.DESKTOP,
    "slg1.col_date": Backend.DESKTOP,
    "slg1.col_time": Backend.DESKTOP,
    "slg1.col_messages": Backend.DESKTOP,
    "slg1.empty_cell": Backend.WEBGUI,
    # sm30
    "sm30.initial_screen": Backend.WEBGUI,
    "sm30.maintain": Backend.BOTH,
    "sm30.table_view": Backend.BOTH,
    "sm30.display_view": Backend.BOTH,
    "sm30.view_not_found": Backend.WEBGUI,
    "sm30.no_maintenance_dialog": Backend.WEBGUI,
    "sm30.view_title": Backend.WEBGUI,
    "sm30.row_count": Backend.WEBGUI,
    # sm37
    "sm37.status": Backend.BOTH,
    "sm37.col_status": Backend.DESKTOP,
    "sm37.job_name": Backend.BOTH,
    "sm37.user_name": Backend.WEBGUI,
    "sm37.from_date": Backend.WEBGUI,
    "sm37.to_date": Backend.WEBGUI,
    "sm37.job_log_button": Backend.BOTH,
    "sm37.job_log_heading": Backend.BOTH,
    "sm37.job_log_title_ecc": Backend.BOTH,
    "sm37.job_list_heading": Backend.WEBGUI,
    "sm37.no_jobs": Backend.DESKTOP,
    "sm37.select_hint": Backend.DESKTOP,
    "sm37.selected_hint": Backend.DESKTOP,
    "sm37.event_driven": Backend.WEBGUI,
    "sm37.abap_program": Backend.WEBGUI,
    "sm37.col_start_date": Backend.DESKTOP,
    "sm37.col_start_time": Backend.DESKTOP,
    "sm37.col_duration": Backend.DESKTOP,
    "sm37.col_created_by": Backend.DESKTOP,
    "sm37.col_client": Backend.DESKTOP,
    # spro
    "spro.initial_screen": Backend.WEBGUI,
    "spro.sap_reference_img": Backend.BOTH,
    "spro.search_button": Backend.WEBGUI,
    "spro.search_dialog": Backend.BOTH,
    "spro.search_field": Backend.BOTH,
    "spro.results_dialog": Backend.WEBGUI,
    "spro.column_hits": Backend.BOTH,
    "spro.column_parent": Backend.BOTH,
    "spro.column_area": Backend.BOTH,
    "spro.img_heading": Backend.WEBGUI,
    # st22
    "st22.section": Backend.BOTH,
    "st22.today": Backend.BOTH,
    "st22.yesterday": Backend.BOTH,
    "st22.date_field": Backend.BOTH,
    "st22.runtime_errors": Backend.WEBGUI,
    "st22.no_dumps": Backend.DESKTOP,
    "st22.col_time": Backend.DESKTOP,
    "st22.col_program": Backend.DESKTOP,
    "st22.col_error_type": Backend.DESKTOP,
    "st22.col_short_text": Backend.DESKTOP,
    "st22.call_stack_heading": Backend.BOTH,
    "st22.other_headings": Backend.BOTH,
    "st22.source_code_of": Backend.WEBGUI,
    "st22.source_code_start": Backend.WEBGUI,
    "st22.source_line": Backend.WEBGUI,
    "st22.line": Backend.WEBGUI,
}

BACKEND_OF: Mapping[str, Backend] = MappingProxyType(_TAGS)
"""``"section.field"`` -> the backend that reads it."""


def backend_of(path: str) -> Backend:
    """The consumer of a leaf path as :func:`~sapguimcp.lang.schema.iter_leaves` yields it.

    ``sm37.status[Ready]`` resolves like ``sm37.status``; ``KeyError`` if the field has no tag.
    """
    return BACKEND_OF[path.partition("[")[0]]
