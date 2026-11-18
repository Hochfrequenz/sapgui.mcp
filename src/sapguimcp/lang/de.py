"""German language pack (SAP logon language DE). Adding a language: see ``ADDING_A_LANGUAGE.md``."""

from sapguimcp.lang.schema import (
    AbapgitSection,
    CatalogSection,
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
from sapguimcp.lang.text import RegexText, Text

DE = LanguagePack(
    code="DE",
    date_format="%d.%m.%Y",
    same_as_en=frozenset(
        {
            "sm37.col_status",
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
        user=Text(("Benutzer",)),
        program=Text(("Programm",)),
    ),
    popup=PopupSection(
        type_error=Text(("Fehler",)),
        type_info=Text(("Information", "Hinweis")),
        type_confirm=Text(("Bestätigung", "Ja", "Nein")),
        inactive_objects=Text(("Inaktive Objekte",), fold=False),
        original_language_hint=RegexText(("originalsprache", r"original-\s*und\s+anmeldesprache")),
        maintain_in_original=Text(("In Orig.spr. pflegen", "Pflege in Originalsprache")),
        # The stem, as before: matches "Schließen" without depending on the encoding of ß.
        abapgit_error_keywords=Text(("nicht gefunden", "fehler", "fehlgeschlagen", "erforderlich")),
        abapgit_button_labels=Text(("Abbrechen", "Ja", "Nein")),
        abapgit_inactive_objects=Text(("Inaktive Objekte",)),
        abapgit_transport_required=Text(("transport erforderlich", "transportauftrag")),
        abapgit_no_task=Text(("keine modifizierbare aufgabe", "keine aufgabe")),
    ),
    status_type=StatusTypeSection(
        activation_confirmed=Text(("aktiviert",)),
        activation_denied=Text(("nicht aktiv", "konnte nicht", "kann nicht", "fehlgeschlagen", "deaktiv", "inaktiv")),
    ),
    session_pages=SessionPagesSection(
        # The DE window title reads "ABAP Debugger(1)  (exklusiv) ..."; other releases hyphenate it.
        debugger_window=Text(("ABAP Debugger", "ABAP-Debugger"), fold=False),
    ),
    keys=KeysSection(
        names=canonical(
            {
                Key.CTRL: Text(("Strg",), word=True),
                Key.SHIFT: Text(("Umschalt", "Umsch"), word=True),
                Key.ALT: Text(("Alt",), word=True),
                Key.ENTER: Text(("Eingabe",), word=True),
                Key.DELETE: Text(("Entf",), word=True),
                Key.ESCAPE: Text(("Escape", "Esc"), word=True),
            }
        ),
    ),
    abapgit=AbapgitSection(
        status_error=Text(("nicht gefunden", "fehler")),
        screen_errors=Text(("nicht gefunden", "transport erforderlich", "fehler bei")),
    ),
    catalog=CatalogSection(screen_header=Text(("Dynpro",))),
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
    ),
    se11=Se11Section(
        table_name=Text(("Tabellenname",)),
    ),
    se16=Se16Section(
        results_title=Text(("Treffer",)),
    ),
    se24=Se24Section(
        # The DE screens carry the English title "Class Builder" (snapshots of the DE system); "Klassenpflege" is
        # the transaction text and was the pack's only variant before.
        initial_screen=Text(("Class Builder: Einstieg", "Klassenpflege: Einstieg")),
        object_type=Text(("Objekttyp",)),
        interface_label=Text(("Interface",)),
        # The methods/attributes table controls show the DDIC domain texts in English on DE logons too (live check),
        # so the English words are variants of the DE pack.
        visibility=canonical(
            {
                Visibility.PUBLIC: Text(("Öffentlich", "Public")),
                Visibility.PROTECTED: Text(("Geschützt", "Protected")),
                Visibility.PRIVATE: Text(("Privat", "Private")),
            }
        ),
        static=Text(("Statisch", "Static")),
        abstract=Text(("Abstrakt", "Abstract")),
        constant=Text(("Konstante", "Constant")),
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
        fm_field_label=Text(("Funktionsbaustein",), fold=False),
        attributes_tab=Text(("Eigenschaften",)),
        import_tab=Text(("Import",)),
        export_tab=Text(("Export",)),
        changing_tab=Text(("Changing",)),
        tables_tab=Text(("Tabellen",)),
        exceptions_tab=Text(("Ausnahmen",)),
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
        transaction_code=Text(("Transaktionscode",)),
    ),
    slg1=Slg1Section(
        no_logs_found=Text(("Es konnte kein Protokoll auf der Datenbank gefunden werden", "Keine Protokolle")),
        log_object=Text(("Objekt",)),
        log_subobject=Text(("Unterobjekt",)),
        external_id=Text(("Ext. Identif.",)),
        log_number=Text(("Protokollnummer", "Protokollnr.")),
        col_date=Text(("Datum",)),
        col_time=Text(("Uhrzeit",)),
        col_messages=Text(("Anzahl Nachr.",)),
    ),
    sm30=Sm30Section(
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
        col_status=Text(("Status",)),
        job_name=Text(("Jobname",), fold=False),
        job_log_button=Text(("Job-Log",)),
        job_log_heading=Text(("Job Log Einträge",), fold=False),
        job_log_title_ecc=Text(("Job-Log zu Job",)),
        no_jobs=Text(("Kein Job entspricht", "Keine Jobs", "Keine Hintergrundjobs")),
        select_hint=Text(("Zum Auswählen",), fold=False),
        selected_hint=Text(("Selektierte",), fold=False),
        col_start_date=Text(("Startdatum",)),
        col_start_time=Text(("Startzeit",)),
        col_duration=Text(("Dauer", "Dauer(s)", "Dauer(sec.)")),
        col_created_by=Text(("Ersteller", "Job-Erstelle", "Job-Ersteller")),
        col_client=Text(("Mandant",)),
    ),
    spro=SproSection(
        sap_reference_img=Text(("SAP Referenz-IMG",)),
        search_dialog=Text(("Suche in der Struktur",)),
        search_field=Text(("Suchbegriff",)),
        column_hits=Text(("Gefundene Treffer",)),
        column_parent=Text(("Übergeordneter Knoten",)),
        column_area=Text(("Im Bereich",)),
    ),
    st22=St22Section(
        section=canonical(
            {
                DumpSection.WHAT_HAPPENED: Text(("Was ist geschehen?", "Was ist passiert")),
                DumpSection.HOW_TO_CORRECT: Text(("Was können Sie tun?", "Hinweise zur Fehlerbehebung")),
                DumpSection.ERROR_ANALYSIS: Text(("Fehleranalyse",)),
            }
        ),
        today=Text(("Heute",)),
        yesterday=Text(("Gestern",)),
        date_field=Text(("Datum",)),
        no_dumps=Text(("Keine Einträge gefunden", "Keine Kurzdumps", "Keine Dumps", "Keine Kurzabzüge")),
        col_time=Text(("Uhrzeit", "Zeit")),
        col_program=Text(("Programm", "Abgebrochenes Programm")),
        col_error_type=Text(("Laufzeitfehler", "Fehler")),
        col_short_text=Text(("Kurztext",)),
        call_stack_heading=Text(("Aktive Aufrufe/Ereignisse", "Aktive Aufrufe", "Aufrufhierarchie")),
        other_headings=Text(
            (
                "Systemumgebung",
                "Anwenderspezifische Systemumgebung",
                "Informationen zur Abbruchstelle",
                "Quelltextauszug",
                "Inhalte der Systemfelder",
                "Ausgewählte Variablen",
                "Aktive Aufrufe im SAP-Kernel",
                "Anwender und Transaktion",
                "Kurztext",
                "Interne Notizen",
            )
        ),
    ),
)
