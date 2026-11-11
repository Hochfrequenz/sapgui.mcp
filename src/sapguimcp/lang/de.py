"""German language pack (SAP logon language DE)."""

from sapguimcp.lang.schema import (
    CommonSection,
    DumpSection,
    JobStatus,
    Key,
    KeysSection,
    LanguagePack,
    PopupSection,
    Se09Section,
    Se11Section,
    Se16Section,
    Se24Section,
    Se37Section,
    Se38Section,
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
    same_as_en=frozenset(
        {
            "se24.interface_label",
            "se37.import_tab",
            "se37.export_tab",
            "se37.changing_tab",
            "se37.optional_column",
            "keys.names[Alt]",
            "keys.names[Escape]",
        }
    ),
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
    se09=Se09Section(
        status=canonical(
            {
                TransportStatus.MODIFIABLE: Text(("Änderbar",)),
                TransportStatus.RELEASED: Text(("Freigegeben",)),
            }
        ),
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
        # The DE screens carry the English title "Class Builder" (snapshots of the DE system); "Klassenpflege" is
        # the transaction text and was the pack's only variant before.
        initial_screen=Text(("Class Builder: Einstieg", "Klassenpflege: Einstieg")),
        display_title=Template(("Class Builder: {name} anzeigen", "Klassenpflege: {name} anzeigen")),
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
        constant=Text(("Konstante",)),
        class_field_label=Text(("Objekttyp", "Klasse/Interface")),
        methods_tab=Text(("Methoden",)),
        attributes_tab=Text(("Attribute",)),
        interfaces_tab=Text(("Schnittstellen",)),
        properties_tab=Text(("Eigenschaften",)),
        source_button=Text(("Quelltext", "Sourcecode", "Weiter zu Quelltext")),
        method_column=Text(("Methode",)),
        attribute_column=Text(("Attribut",)),
        kind_column=Text(("Art",)),
        visibility_column=Text(("Sichtbarkeit",)),
        description_column=Text(("Beschreibung",)),
        type_ref_column=Text(("Bezugstyp",)),
        initial_value_column=Text(("Initialer Wert",)),
    ),
    se37=Se37Section(
        initial_screen=Text(("Function Builder: Einstieg",)),
        display_title=Template(("Function Builder: {name} anzeigen",)),
        function_builder=Text(("Function Builder", "Funktionsbaustein")),
        fm_field_label=Text(("Funktionsbaustein",)),
        not_found=Text(("ist noch nicht vorhanden", "nicht vorhanden")),
        attributes_tab=Text(("Eigenschaften",)),
        import_tab=Text(("Import",)),
        export_tab=Text(("Export",)),
        changing_tab=Text(("Changing",)),
        tables_tab=Text(("Tabellen",)),
        exceptions_tab=Text(("Ausnahmen",)),
        source_tab=Text(("Quelltext",)),
        parameter_name_column=Text(("Parametername",)),
        typing_column=Text(("Typisierung",)),
        type_ref_column=Text(("Bezugstyp",)),
        default_column=Text(("Standardwert",)),
        optional_column=Text(("Optional",)),
        pass_value_column=Text(("Wertübergabe",)),
        short_text_column=Text(("Kurztext",)),
        exception_column=Text(("Ausnahme",)),
    ),
    se38=Se38Section(
        initial_screen=Text(("Einstieg",)),
        program_field_title=Text(("ABAP-Programmname", "Programm")),
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
