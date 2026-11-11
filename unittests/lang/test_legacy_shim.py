"""The former ``lang.py`` constants stay importable and agree with the packs (#1044, phase 2a).

Every constant maps to the pack field that now holds its text. The test fails when a constant is
added without a mapping, or when a pack text and its constant drift apart.
"""

import pytest

from sapguimcp import lang
from sapguimcp.lang import _legacy
from sapguimcp.lang.schema import iter_leaves
from sapguimcp.lang.text import RegexText, Text

# Constant name without _DE/_EN -> pack field path ("invariant." paths point into lang.INVARIANT).
LEGACY_PATHS: dict[str, str] = {
    "SE16_HIT_COUNT_LABEL": "se16.hit_count_label",
    "SE16_ROW_SELECT_HINT": "common.row_select_hint",
    "SE16_COLUMN_SELECTION": "se16.column_selection",
    "SE16_NO_ENTRIES": "se16.no_values_found",
    "SE11_DATABASE_TABLE": "se11.database_table",
    "SE11_DATA_TYPE": "se11.data_type",
    "SE11_TABLE_NAME": "se11.table_name",
    "SE11_DISPLAY_BUTTON": "common.display",
    "SE11_TRANSPARENT_TABLE": "se11.transparent_table",
    "SE11_STRUCTURE": "se11.structure",
    "SE11_SHORT_DESC": "se11.short_description",
    "SE11_ROW_SELECT_PREFIX": "common.row_select_hint",
    "SE11_ROW_SELECT_FULL": "se11.row_select_full",
    "SE11_NOT_EXIST": "common.does_not_exist",
    "SE11_NOT_FOUND": "common.not_found",
    "SE37_INITIAL_SCREEN": "se37.initial_screen",
    "SE37_NOT_EXIST": "common.does_not_exist",
    "SE37_NOT_FOUND": "common.does_not_exist",
    "SE24_CLASS_BUILDER": "se24.class_builder",
    "SE24_OBJECT_TYPE": "se24.object_type",
    "SE24_CLASS": "se24.class_label",
    "SE24_INTERFACE": "se24.interface_label",
    "SE24_PUBLIC": "se24.visibility[Public]",
    "SE24_PRIVATE": "se24.visibility[Private]",
    "SE24_PROTECTED": "se24.visibility[Protected]",
    "SE24_STATIC": "se24.static",
    "SE24_ABSTRACT": "se24.abstract",
    "SE24_INITIAL_SCREEN": "se24.initial_screen",
    "SE24_NOT_FOUND": "common.does_not_exist",
    "SE24_NOT_EXIST": "common.does_not_exist",
    "SE93_DIALOG_TRANSACTION": "se93.dialog_transaction",
    "SE93_REPORT_TRANSACTION": "se93.report_transaction",
    "SE93_INITIAL_SCREEN": "se93.initial_screen",
    "SE93_GUI_HTML": "se93.gui_html",
    "SE93_GUI_JAVA": "se93.gui_java",
    "SE93_GUI_WINDOWS": "se93.gui_windows",
    "SE93_SCREEN_NUMBER": "se93.screen_number",
    "SE93_SELECTION_SCREEN": "se93.selection_screen",
    "SE93_START_WITH_VARIANT": "se93.start_with_variant",
    "SE93_TRANSACTION_CODE": "se93.transaction_code",
    "SE93_TRANSACTION_TEXT": "se93.transaction_text",
    "SE93_PACKAGE": "se93.package",
    "SE93_PROGRAM": "common.program",
    "SE93_AUTH_OBJECT": "se93.auth_object",
    "SLG1_INITIAL_SCREEN": "slg1.initial_screen",
    "SLG1_LOG_LIST_SCREEN": "slg1.log_list_screen",
    "SLG1_NO_LOGS_FOUND": "slg1.no_logs_found",
    "SE09_USER_FIELD": "common.user",
    "SE09_MODIFIABLE": "se09.status[Modifiable]",
    "SE09_RELEASED": "se09.status[Released]",
    "SE09_DISPLAY_BUTTON": "common.display",
    "SM30_DISPLAY_BUTTON": "common.display",
    "SM30_MAINTAIN_BUTTON": "sm30.maintain",
    "SM30_TABLE_VIEW": "sm30.table_view",
    "SM30_INITIAL_SCREEN": "sm30.initial_screen",
    "SM30_NOT_FOUND": "common.does_not_exist",
    "SM30_DISPLAY_VIEW": "sm30.display_view",
    "SM30_USE_SM34": "invariant.sm34_hint",
    "SM30_ROW_SELECT_HINT": "common.row_select_hint",
    "SPRO_INITIAL_SCREEN": "spro.initial_screen",
    "SPRO_SAP_REF_IMG": "spro.sap_reference_img",
    "SPRO_SEARCH_BUTTON": "spro.search_button",
    "SPRO_SEARCH_DIALOG": "spro.search_dialog",
    "SPRO_SEARCH_FIELD": "spro.search_field",
    "SPRO_RESULTS_DIALOG": "spro.results_dialog",
    "SPRO_COL_HITS": "spro.column_hits",
    "SPRO_COL_PARENT": "spro.column_parent",
    "SPRO_COL_AREA": "spro.column_area",
    "SPRO_IMG_HEADING": "spro.img_heading",
    "ST22_WHAT_HAPPENED": "st22.section[what_happened]",
    "ST22_HOW_TO_CORRECT": "st22.section[how_to_correct]",
    "ST22_ERROR_ANALYSIS": "st22.section[error_analysis]",
    "ST22_NO_DUMPS": "common.no_entries",
}

# Constants whose name does not follow BASE_DE / BASE_EN.
IRREGULAR: dict[str, tuple[str, str]] = {
    "SE37_DISPLAY_SUFFIX_DE": ("DE", "common.display"),
    "SE37_DISPLAY_PREFIX_EN": ("EN", "common.display"),
    "SE24_DISPLAY_SUFFIX_DE": ("DE", "common.display"),
    "SE24_DISPLAY_PREFIX_EN": ("EN", "common.display"),
    "SLG1_NO_LOGS_FOUND_EN_LEGACY": ("EN", "slg1.no_logs_found"),
}

NOT_TEXTS = {"bilingual_pattern", "SM37_STATUS_MAP_DE", "SM37_STATUS_MAP_EN"}


def _target(name: str) -> tuple[str, str]:
    if name in IRREGULAR:
        return IRREGULAR[name]
    base, _, code = name.rpartition("_")
    return code, LEGACY_PATHS[base]


def _values(code: str, path: str) -> set[str]:
    if path.startswith("invariant."):
        leaf = getattr(lang.INVARIANT, path.removeprefix("invariant."))
    else:
        leaf = dict(iter_leaves(lang.pack_for(code)))[path]
    assert isinstance(leaf, Text | RegexText), path
    values = leaf.patterns if isinstance(leaf, RegexText) else leaf.variants
    return {value.lower() for value in values}


TEXT_CONSTANTS = sorted(set(_legacy.__all__) - NOT_TEXTS)


def test_every_constant_is_exported_by_the_package() -> None:
    for name in _legacy.__all__:
        assert getattr(lang, name) is getattr(_legacy, name)


@pytest.mark.parametrize("name", TEXT_CONSTANTS)
def test_constant_is_a_variant_of_its_pack_field(name: str) -> None:
    code, path = _target(name)
    assert getattr(_legacy, name).lower() in _values(code, path)


def test_sm37_status_maps_are_unchanged() -> None:
    assert lang.SM37_STATUS_MAP_DE == {
        "geplant": "Scheduled",
        "freigegeben": "Released",
        "bereit": "Ready",
        "aktiv": "Active",
        "fertig": "Finished",
        "abgebrochen": "Canceled",
    }
    assert lang.SM37_STATUS_MAP_EN == {
        "scheduled": "Scheduled",
        "released": "Released",
        "ready": "Ready",
        "active": "Active",
        "finished": "Finished",
        "canceled": "Canceled",
    }


def test_bilingual_pattern_is_unchanged() -> None:
    assert lang.bilingual_pattern("a.b", "c") == r"(?:a\.b|c)"
    assert lang.bilingual_pattern("a.b", "c", escape=False) == "(?:a.b|c)"


def test_slg1_no_logs_found_en_is_sap_message_bl_208() -> None:
    assert lang.SLG1_NO_LOGS_FOUND_EN == "No log found in the database"
    assert lang.SLG1_NO_LOGS_FOUND_EN_LEGACY == "No log could be found in the database"
