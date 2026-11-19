"""Which backend code reads each language-pack text (#1099).

Every field of a language pack section (every path of :func:`sapguimcp.lang.schema.iter_leaves`,
without the ``[key]`` of a canonical mapping) has exactly one entry in :data:`BACKEND_OF`:

- ``DESKTOP``: only the SAP GUI for Windows (COM) backend reads the text.
- ``BOTH``: shared code (outside ``backend/desktop/`` and the ``*_desktop`` functions) reads it.

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
    BOTH = "both"


_TAGS: dict[str, Backend] = {
    # common
    "common.display": Backend.BOTH,
    "common.not_found": Backend.BOTH,
    "common.does_not_exist": Backend.BOTH,
    "common.no_entries": Backend.DESKTOP,
    "common.user": Backend.BOTH,
    "common.program": Backend.BOTH,
    # popup
    "popup.type_error": Backend.DESKTOP,
    "popup.type_info": Backend.DESKTOP,
    "popup.type_confirm": Backend.DESKTOP,
    "popup.inactive_objects": Backend.DESKTOP,
    "popup.original_language_hint": Backend.DESKTOP,
    "popup.maintain_in_original": Backend.DESKTOP,
    "popup.abapgit_error_keywords": Backend.BOTH,
    "popup.abapgit_button_labels": Backend.BOTH,
    "popup.abapgit_inactive_objects": Backend.BOTH,
    "popup.abapgit_transport_required": Backend.BOTH,
    "popup.abapgit_no_task": Backend.BOTH,
    # status_type
    "status_type.activation_confirmed": Backend.DESKTOP,
    "status_type.activation_denied": Backend.DESKTOP,
    # session_pages
    "session_pages.debugger_window": Backend.DESKTOP,
    # keys
    "keys.names": Backend.BOTH,
    # abapgit
    "abapgit.status_error": Backend.BOTH,
    "abapgit.screen_errors": Backend.BOTH,
    # catalog
    "catalog.screen_header": Backend.BOTH,
    # se09
    "se09.status": Backend.BOTH,
    "se09.display_button": Backend.DESKTOP,
    "se09.workbench_requests": Backend.BOTH,
    "se09.customizing_requests": Backend.BOTH,
    "se09.expand": Backend.DESKTOP,
    "se09.compress": Backend.DESKTOP,
    # se11
    "se11.table_name": Backend.BOTH,
    # se16
    "se16.results_title": Backend.DESKTOP,
    # se24
    "se24.initial_screen": Backend.DESKTOP,
    "se24.object_type": Backend.DESKTOP,
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
    "se37.fm_field_label": Backend.DESKTOP,
    "se37.attributes_tab": Backend.DESKTOP,
    "se37.import_tab": Backend.DESKTOP,
    "se37.export_tab": Backend.DESKTOP,
    "se37.changing_tab": Backend.DESKTOP,
    "se37.tables_tab": Backend.DESKTOP,
    "se37.exceptions_tab": Backend.DESKTOP,
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
    "se93.transaction_code": Backend.BOTH,
    # slg1
    "slg1.no_logs_found": Backend.DESKTOP,
    "slg1.log_object": Backend.DESKTOP,
    "slg1.log_subobject": Backend.DESKTOP,
    "slg1.external_id": Backend.DESKTOP,
    "slg1.log_number": Backend.DESKTOP,
    "slg1.col_date": Backend.DESKTOP,
    "slg1.col_time": Backend.DESKTOP,
    "slg1.col_messages": Backend.DESKTOP,
    # sm30
    "sm30.maintain": Backend.BOTH,
    "sm30.table_view": Backend.BOTH,
    "sm30.display_view": Backend.BOTH,
    # sm37
    "sm37.status": Backend.BOTH,
    "sm37.col_status": Backend.DESKTOP,
    "sm37.job_name": Backend.BOTH,
    "sm37.job_log_button": Backend.BOTH,
    "sm37.job_log_heading": Backend.BOTH,
    "sm37.job_log_title_ecc": Backend.BOTH,
    "sm37.no_jobs": Backend.DESKTOP,
    "sm37.select_hint": Backend.DESKTOP,
    "sm37.selected_hint": Backend.DESKTOP,
    "sm37.col_start_date": Backend.DESKTOP,
    "sm37.col_start_time": Backend.DESKTOP,
    "sm37.col_duration": Backend.DESKTOP,
    "sm37.col_created_by": Backend.DESKTOP,
    "sm37.col_client": Backend.DESKTOP,
    # spro
    "spro.sap_reference_img": Backend.BOTH,
    "spro.search_dialog": Backend.BOTH,
    "spro.search_field": Backend.BOTH,
    "spro.column_hits": Backend.BOTH,
    "spro.column_parent": Backend.BOTH,
    "spro.column_area": Backend.BOTH,
    # st22
    "st22.section": Backend.BOTH,
    "st22.today": Backend.BOTH,
    "st22.yesterday": Backend.BOTH,
    "st22.date_field": Backend.BOTH,
    "st22.no_dumps": Backend.DESKTOP,
    "st22.col_time": Backend.DESKTOP,
    "st22.col_program": Backend.DESKTOP,
    "st22.col_error_type": Backend.DESKTOP,
    "st22.col_short_text": Backend.DESKTOP,
    "st22.call_stack_heading": Backend.BOTH,
    "st22.termination_heading": Backend.BOTH,
    "st22.other_headings": Backend.BOTH,
}

BACKEND_OF: Mapping[str, Backend] = MappingProxyType(_TAGS)
"""``"section.field"`` -> the backend that reads it."""


def backend_of(path: str) -> Backend:
    """The consumer of a leaf path as :func:`~sapguimcp.lang.schema.iter_leaves` yields it.

    ``sm37.status[Ready]`` resolves like ``sm37.status``; ``KeyError`` if the field has no tag.
    """
    return BACKEND_OF[path.partition("[")[0]]
