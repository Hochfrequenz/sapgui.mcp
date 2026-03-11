"""
Explicit DE/EN language constants for SAP GUI text matching.

Every constant has _DE or _EN suffix - verbose but obvious.
This module centralizes all language-dependent strings used in parsers.
"""

import re

# =============================================================================
# SE16 - Data Browser
# =============================================================================
SE16_HIT_COUNT_LABEL_DE = "Anzahl Treffer"
SE16_HIT_COUNT_LABEL_EN = "Number of Hits"

SE16_ROW_SELECT_HINT_DE = "Zum Auswählen einer Zeile"
SE16_ROW_SELECT_HINT_EN = "To select a row"

SE16_COLUMN_SELECTION_DE = "Spalte für Zeilenauswahl"
SE16_COLUMN_SELECTION_EN = "Column for row selection"

SE16_NO_ENTRIES_DE = "keine werte gefunden"
SE16_NO_ENTRIES_EN = "no values found"

# =============================================================================
# SE11 - ABAP Dictionary
# =============================================================================
SE11_DATABASE_TABLE_DE = "Datenbanktabelle"
SE11_DATABASE_TABLE_EN = "Database table"

SE11_DATA_TYPE_DE = "Datentyp"
SE11_DATA_TYPE_EN = "Data type"

SE11_TABLE_NAME_DE = "Tabellenname"
SE11_TABLE_NAME_EN = "Table name"

SE11_DISPLAY_BUTTON_DE = "Anzeigen"
SE11_DISPLAY_BUTTON_EN = "Display"

SE11_TRANSPARENT_TABLE_DE = "Transp.Tabelle"
SE11_TRANSPARENT_TABLE_EN = "Transparent Table"

SE11_STRUCTURE_DE = "Struktur"
SE11_STRUCTURE_EN = "Structure"

SE11_SHORT_DESC_DE = "Kurzbeschreibung"
SE11_SHORT_DESC_EN = "Short Description"

SE11_ROW_SELECT_PREFIX_DE = "Zum Auswählen"
SE11_ROW_SELECT_PREFIX_EN = "To select a row"

SE11_ROW_SELECT_FULL_DE = r"Zum Auswählen[^\"]*Leertaste\."
SE11_ROW_SELECT_FULL_EN = r"To select a row, press the space bar\."

SE11_DICTIONARY_TYPE_DE = "Dictionary.*Typ"
SE11_DICTIONARY_TYPE_EN = "Dictionary.*type"

# Error messages
SE11_NOT_EXIST_DE = "existiert nicht"
SE11_NOT_EXIST_EN = "does not exist"

SE11_NOT_FOUND_DE = "nicht gefunden"
SE11_NOT_FOUND_EN = "not found"

# =============================================================================
# SE37 - Function Builder
# =============================================================================
SE37_DISPLAY_SUFFIX_DE = "anzeigen"
SE37_DISPLAY_PREFIX_EN = "Display"

SE37_INITIAL_SCREEN_DE = "Function Builder: Einstieg"
SE37_INITIAL_SCREEN_EN = "Function Builder: Initial Screen"

SE37_NOT_EXIST_DE = "ist noch nicht vorhanden"
SE37_NOT_EXIST_EN = "does not exist"

SE37_NOT_FOUND_DE = "nicht vorhanden"
SE37_NOT_FOUND_EN = "does not exist"

# =============================================================================
# SE24 - Class Builder
# =============================================================================
SE24_CLASS_BUILDER_DE = "Klassenpflege"
SE24_CLASS_BUILDER_EN = "Class Builder"

SE24_DISPLAY_SUFFIX_DE = "anzeigen"
SE24_DISPLAY_PREFIX_EN = "Display"

SE24_OBJECT_TYPE_DE = "Objekttyp"
SE24_OBJECT_TYPE_EN = "Object Type"

SE24_CLASS_DE = "Klasse"
SE24_CLASS_EN = "Class"

SE24_INTERFACE_DE = "Interface"
SE24_INTERFACE_EN = "Interface"

# Visibility keywords
SE24_PUBLIC_DE = "Öffentlich"
SE24_PUBLIC_EN = "Public"

SE24_PRIVATE_DE = "Privat"
SE24_PRIVATE_EN = "Private"

SE24_PROTECTED_DE = "Geschützt"
SE24_PROTECTED_EN = "Protected"

# Modifier keywords
SE24_STATIC_DE = "Statisch"
SE24_STATIC_EN = "Static"

SE24_ABSTRACT_DE = "Abstrakt"
SE24_ABSTRACT_EN = "Abstract"

# Initial screen
SE24_INITIAL_SCREEN_DE = "Klassenpflege: Einstieg"
SE24_INITIAL_SCREEN_EN = "Class Builder: Initial"

# Error messages
SE24_NOT_FOUND_DE = "nicht vorhanden"
SE24_NOT_FOUND_EN = "does not exist"

SE24_NOT_EXIST_DE = "existiert nicht"
SE24_NOT_EXIST_EN = "does not exist"

# =============================================================================
# SE93 - Transaction Maintenance
# =============================================================================
SE93_DIALOG_TRANSACTION_DE = "Dialogtransaktion"
SE93_DIALOG_TRANSACTION_EN = "Dialog Transaction"

SE93_REPORT_TRANSACTION_DE = "Reporttransaktion"
SE93_REPORT_TRANSACTION_EN = "Report Transaction"

SE93_INITIAL_SCREEN_DE = "Transaktionspflege"
SE93_INITIAL_SCREEN_EN = "Transaction Maintenance"

# GUI capability labels
SE93_GUI_HTML_DE = "SAP GUI für HTML"
SE93_GUI_HTML_EN = "SAP GUI for HTML"

SE93_GUI_JAVA_DE = "SAP GUI für Java"
SE93_GUI_JAVA_EN = "SAP GUI for Java"

SE93_GUI_WINDOWS_DE = "SAP GUI für Windows"
SE93_GUI_WINDOWS_EN = "SAP GUI for Windows"

# Field labels
SE93_SCREEN_NUMBER_DE = "Dynpronummer"
SE93_SCREEN_NUMBER_EN = "Screen number"

SE93_SELECTION_SCREEN_DE = "Selektionsbild"
SE93_SELECTION_SCREEN_EN = "Selection screen"

SE93_START_WITH_VARIANT_DE = "Start mit Variante"
SE93_START_WITH_VARIANT_EN = "Start with variant"

SE93_TRANSACTION_CODE_DE = "Transaktionscode"
SE93_TRANSACTION_CODE_EN = "Transaction code"

SE93_TRANSACTION_TEXT_DE = "Transaktionstext"
SE93_TRANSACTION_TEXT_EN = "Transaction text"

SE93_PACKAGE_DE = "Paket"
SE93_PACKAGE_EN = "Package"

SE93_PROGRAM_DE = "Programm"
SE93_PROGRAM_EN = "Program"

SE93_AUTH_OBJECT_DE = "Berechtigungsobjekt"
SE93_AUTH_OBJECT_EN = "Authorization object"

# =============================================================================
# SLG1 - Application Log
# =============================================================================
SLG1_INITIAL_SCREEN_DE = "Anwendungslog auswerten"
SLG1_INITIAL_SCREEN_EN = "Analyze Application Log"

SLG1_LOG_LIST_SCREEN_DE = "Protokolle anzeigen"
SLG1_LOG_LIST_SCREEN_EN = "Display Logs"

# Status bar message when no logs found
SLG1_NO_LOGS_FOUND_DE = "Es konnte kein Protokoll auf der Datenbank gefunden werden"
SLG1_NO_LOGS_FOUND_EN = "No log could be found in the database"


# =============================================================================
# SM37 - Job Overview
# =============================================================================

# Status text mapping (as shown in job list result rows, lowercase in ARIA)
# Exported because parsers and tools both reference these.
SM37_STATUS_MAP_DE = {
    "geplant": "Scheduled",
    "freigegeben": "Released",
    "bereit": "Ready",
    "aktiv": "Active",
    "fertig": "Finished",
    "abgebrochen": "Canceled",
}

SM37_STATUS_MAP_EN = {
    "scheduled": "Scheduled",
    "released": "Released",
    "ready": "Ready",
    "active": "Active",
    "finished": "Finished",
    "canceled": "Canceled",
}


# =============================================================================
# SE09 - Transport Organizer
# =============================================================================

# User filter field label
SE09_USER_FIELD_DE = "Benutzer"
SE09_USER_FIELD_EN = "User"

# Status filter labels
SE09_MODIFIABLE_DE = "Änderbar"
SE09_MODIFIABLE_EN = "Modifiable"
SE09_RELEASED_DE = "Freigegeben"
SE09_RELEASED_EN = "Released"

# Button labels
SE09_DISPLAY_BUTTON_DE = "Anzeigen"
SE09_DISPLAY_BUTTON_EN = "Display"


# =============================================================================
# SM30 - Table Maintenance
# =============================================================================
SM30_DISPLAY_BUTTON_DE = "Anzeigen"
SM30_DISPLAY_BUTTON_EN = "Display"

SM30_MAINTAIN_BUTTON_DE = "Pflegen"
SM30_MAINTAIN_BUTTON_EN = "Maintain"

SM30_TABLE_VIEW_DE = "Tabelle/Sicht"
SM30_TABLE_VIEW_EN = "Table/View"

SM30_INITIAL_SCREEN_DE = "Tabellensicht-Pflege"
SM30_INITIAL_SCREEN_EN = "Table View Maintenance"

# SM30 status bar messages for view not found
SM30_NOT_FOUND_DE = "existiert nicht"
SM30_NOT_FOUND_EN = "does not exist"

# SM30 screen titles when displaying a view
SM30_DISPLAY_VIEW_DE = "Sicht"
SM30_DISPLAY_VIEW_EN = "View"

# SM30 hint for SM34 redirect
SM30_USE_SM34_DE = "SM34"
SM30_USE_SM34_EN = "SM34"

# SM30 column header for row selection (display mode)
SM30_ROW_SELECT_HINT_DE = "Zum Auswählen"
SM30_ROW_SELECT_HINT_EN = "To select"


# =============================================================================
# SPRO - Customizing (Implementation Guide)
# =============================================================================

# Initial screen title
SPRO_INITIAL_SCREEN_DE = "Customizing: Projektbearbeitung"
SPRO_INITIAL_SCREEN_EN = "Customizing: Execute Project"

# Button to enter IMG tree
SPRO_SAP_REF_IMG_DE = "SAP Referenz-IMG"
SPRO_SAP_REF_IMG_EN = "SAP Reference IMG"

# Search button in IMG toolbar (title attribute)
SPRO_SEARCH_BUTTON_DE = "Suchen (Strg+F)"
SPRO_SEARCH_BUTTON_EN = "Find (Ctrl+F)"

# Search dialog
SPRO_SEARCH_DIALOG_DE = "Suche in der Struktur"
SPRO_SEARCH_DIALOG_EN = "Search in the structure"

SPRO_SEARCH_FIELD_DE = "Suchbegriff"
SPRO_SEARCH_FIELD_EN = "Search Term"

# Results dialog title pattern (contains search term)
# DE: "Trefferliste zum Suchbegriff \"LAND\""
# EN: "Search Term \"COUNTRY\" Hit List"
SPRO_RESULTS_DIALOG_DE = "Trefferliste zum Suchbegriff"
SPRO_RESULTS_DIALOG_EN = "Hit List"

# Results grid column headers
SPRO_COL_HITS_DE = "Gefundene Treffer"
SPRO_COL_HITS_EN = "Hits"

SPRO_COL_PARENT_DE = "Übergeordneter Knoten"
SPRO_COL_PARENT_EN = "Parent Node"

SPRO_COL_AREA_DE = "Im Bereich"
SPRO_COL_AREA_EN = "In area"

# IMG tree heading (unique to IMG view, not present on initial screen)
SPRO_IMG_HEADING_DE = "IMG anzeigen"
SPRO_IMG_HEADING_EN = "Display IMG"


# =============================================================================
# Helper Functions
# =============================================================================


def bilingual_pattern(de: str, en: str, *, escape: bool = True) -> str:
    """
    Build regex alternation from DE/EN pair: (?:DE|EN)

    Args:
        de: German string
        en: English string
        escape: Whether to escape regex special characters (default True)

    Returns:
        Regex pattern string like (?:Anzahl Treffer|Number of Hits)
    """
    if escape:
        return f"(?:{re.escape(de)}|{re.escape(en)})"
    return f"(?:{de}|{en})"


# =============================================================================
# ST22 - Short Dump Analysis (ABAP Runtime Errors)
# =============================================================================

# Detail page section headers
ST22_WHAT_HAPPENED_DE = "Was ist geschehen?"
ST22_WHAT_HAPPENED_EN = "What happened?"

ST22_HOW_TO_CORRECT_DE = "Was können Sie tun?"
ST22_HOW_TO_CORRECT_EN = "How to Correct the Error"

ST22_ERROR_ANALYSIS_DE = "Fehleranalyse"
ST22_ERROR_ANALYSIS_EN = "Error Analysis"

# "No dumps found" status message
ST22_NO_DUMPS_DE = "Keine Einträge gefunden"
ST22_NO_DUMPS_EN = "No entries found"
