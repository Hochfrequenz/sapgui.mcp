"""German language pack (SAP logon language DE)."""

from sapguimcp.lang.schema import (
    AbapgitSection,
    CommonSection,
    DumpSection,
    JobStatus,
    Key,
    KeysSection,
    LanguagePack,
    PopupSection,
    QuickReportSection,
    Se09Section,
    Se11Section,
    Se16Section,
    Se24Section,
    Se37Section,
    Se93Section,
    SessionPagesSection,
    Slg1Section,
    Sm30Section,
    Sm37Section,
    SproSection,
    St22Section,
    StatusTypeSection,
    TransportStatus,
    Visibility,
    canonical,
)
from sapguimcp.lang.text import RegexText, Template, Text

DE = LanguagePack(
    code="DE",
    html_lang="de",
    logon_dropdown="Deutsch",
    date_format="%d.%m.%Y",
    same_as_en=frozenset({"se24.interface_label", "keys.names[Alt]", "keys.names[Escape]", "se09.organizer_title"}),
    common=CommonSection(
        display=Text(("Anzeigen",)),
        not_found=Text(("nicht gefunden",)),
        does_not_exist=Text(("existiert nicht", "ist noch nicht vorhanden", "nicht vorhanden")),
        no_entries=Text(("Keine Einträge gefunden",)),
        row_select_hint=Text(("Zum Auswählen einer Zeile", "Zum Auswählen")),
        user=Text(("Benutzer",)),
        program=Text(("Programm",)),
    ),
    popup=PopupSection(),
    status_type=StatusTypeSection(),
    session_pages=SessionPagesSection(),
    keys=KeysSection(
        names=canonical(
            {
                Key.CTRL: Text(("Strg",), word=True),
                Key.SHIFT: Text(("Umschalt",), word=True),
                Key.ALT: Text(("Alt",), word=True),
                Key.ENTER: Text(("Eingabe",), word=True),
                Key.DELETE: Text(("Entf",), word=True),
                Key.ESCAPE: Text(("Escape", "Esc"), word=True),
            }
        ),
    ),
    abapgit=AbapgitSection(
        error_keywords=Text(("nicht gefunden", "fehler", "fehlgeschlagen", "erforderlich")),
        status_error=Text(("nicht gefunden", "fehler")),
        screen_errors=Text(("nicht gefunden", "transport erforderlich", "fehler bei")),
        transport_required=Text(("transport erforderlich", "transportauftrag")),
        no_task=Text(("keine modifizierbare aufgabe", "keine aufgabe")),
        button_labels=Text(("Abbrechen", "Ja", "Nein")),
        inactive_objects=Text(("Inaktive Objekte",)),
        se38_initial_title=Text(("Einstieg",)),
    ),
    quick_report=QuickReportSection(
        empty_patterns=Text(("keine Daten", "keine Werte", "kein Job", "keine Belege")),
        execute_button=Text(("Ausführen", "Ausführen Hervorgehoben")),
    ),
    se09=Se09Section(
        status=canonical(
            {
                TransportStatus.MODIFIABLE: Text(("Änderbar",)),
                TransportStatus.RELEASED: Text(("Freigegeben",)),
            }
        ),
        display_button=Text(("Anzeigen",), fold=False),
        workbench_requests=Text(("Workbench-Aufträge",)),
        customizing_requests=Text(("Customizing-Aufträge",)),
        expand=Text(("Expandieren",)),
        compress=Text(("Komprimieren",)),
        list_region=Text(("Liste",)),
        organizer_title=Text(("Transport Organizer",)),
        request_word=Text(("Auftrag", "Aufträge")),
    ),
    se11=Se11Section(
        database_table=Text(("Datenbanktabelle",)),
        data_type=Text(("Datentyp",)),
        table_name=Text(("Tabellenname",)),
        transparent_table=Text(("Transp.Tabelle",)),
        structure=Text(("Struktur",)),
        short_description=Text(("Kurzbeschreibung",)),
        row_select_full=RegexText((r'Zum Auswählen[^"]*Leertaste\.',)),
        dictionary_type=RegexText(("Dictionary.*Typ",)),
    ),
    se16=Se16Section(
        hit_count_label=Text(("Anzahl Treffer",)),
        column_selection=Text(("Spalte für Zeilenauswahl",)),
        no_values_found=Text(("keine werte gefunden",)),
    ),
    se24=Se24Section(
        class_builder=Text(("Klassenpflege",)),
        initial_screen=Text(("Klassenpflege: Einstieg",)),
        display_title=Template(("Klassenpflege: {name} anzeigen",)),
        object_type=Text(("Objekttyp",)),
        class_label=Text(("Klasse",)),
        interface_label=Text(("Interface",)),
        visibility=canonical(
            {
                Visibility.PUBLIC: Text(("Öffentlich",)),
                Visibility.PROTECTED: Text(("Geschützt",)),
                Visibility.PRIVATE: Text(("Privat",)),
            }
        ),
        static=Text(("Statisch",)),
        abstract=Text(("Abstrakt",)),
    ),
    se37=Se37Section(
        initial_screen=Text(("Function Builder: Einstieg",)),
        display_title=Template(("Function Builder: {name} anzeigen",)),
    ),
    se93=Se93Section(
        initial_screen=Text(("Transaktionspflege",)),
        dialog_transaction=Text(("Dialogtransaktion",)),
        report_transaction=Text(("Reporttransaktion",)),
        gui_html=Text(("SAP GUI für HTML",)),
        gui_java=Text(("SAP GUI für Java",)),
        gui_windows=Text(("SAP GUI für Windows",)),
        screen_number=Text(("Dynpronummer",)),
        selection_screen=Text(("Selektionsbild",)),
        start_with_variant=Text(("Start mit Variante",)),
        transaction_code=Text(("Transaktionscode",)),
        transaction_text=Text(("Transaktionstext",)),
        package=Text(("Paket",)),
        auth_object=Text(("Berechtigungsobjekt",)),
    ),
    slg1=Slg1Section(
        initial_screen=Text(("Anwendungslog auswerten",)),
        log_list_screen=Text(("Protokolle anzeigen",)),
        no_logs_found=Text(("Es konnte kein Protokoll auf der Datenbank gefunden werden",)),
    ),
    sm30=Sm30Section(
        initial_screen=Text(("Tabellensicht-Pflege",)),
        maintain=Text(("Pflegen",)),
        table_view=Text(("Tabelle/Sicht",)),
        display_view=Text(("Sicht",)),
        view_not_found=Text(("ist nicht im Dictionary vorhanden", "existiert nicht", "nicht vorhanden")),
        no_maintenance_dialog=Text(("kein Pflegedialog",)),
        view_title=Template(("Sicht {desc} anzeigen", "Sicht {desc} ändern")),
        row_count=Template(("Eintrag {current} von {total}",)),
    ),
    sm37=Sm37Section(
        status=canonical(
            {
                JobStatus.SCHEDULED: Text(("Geplant",)),
                JobStatus.RELEASED: Text(("Freigegeben",)),
                JobStatus.READY: Text(("Bereit",)),
                JobStatus.ACTIVE: Text(("Aktiv",)),
                JobStatus.FINISHED: Text(("Fertig",)),
                JobStatus.CANCELED: Text(("Abgebrochen",)),
            }
        ),
    ),
    spro=SproSection(
        initial_screen=Text(("Customizing: Projektbearbeitung",)),
        sap_reference_img=Text(("SAP Referenz-IMG",)),
        search_button=Text(("Suchen (Strg+F)",)),
        search_dialog=Text(("Suche in der Struktur",)),
        search_field=Text(("Suchbegriff",)),
        results_dialog=Text(("Trefferliste zum Suchbegriff",)),
        column_hits=Text(("Gefundene Treffer",)),
        column_parent=Text(("Übergeordneter Knoten",)),
        column_area=Text(("Im Bereich",)),
        img_heading=Text(("IMG anzeigen",)),
    ),
    st22=St22Section(
        section=canonical(
            {
                DumpSection.WHAT_HAPPENED: Text(("Was ist geschehen?",)),
                DumpSection.HOW_TO_CORRECT: Text(("Was können Sie tun?",)),
                DumpSection.ERROR_ANALYSIS: Text(("Fehleranalyse",)),
            }
        ),
    ),
)
