"""IT language pack (#1041, #1044).

Texts come from SAP (``scripts/harvest_lang_texts.py IT --draft`` and ``--verify``) or from the screen read with an
Italian logon. Every ``TODO`` comment marks a field a person still has to settle; remove it afterwards.
"""

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
    QuickReportSection,
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

IT = LanguagePack(
    code="IT",
    html_lang="it",
    logon_dropdown="Italiano",  # TODO verify in the WebGUI logon dropdown (task 3)
    date_format="%d.%m.%Y",  # T005X-DATFM = 1 for country IT
    same_as_en=frozenset({"keys.names[Alt]", "keys.names[Ctrl]", "keys.names[Shift]", "se09.organizer_title", "se24.class_builder", "se24.interface_label", "se24.interfaces_tab", "se37.function_builder", "sm30.display_view", "st22.col_error_type", "st22.col_time", "st22.date_field", "st22.source_code_of", "st22.source_line"}),
    common=CommonSection(
        display=Text(("Visualizzare",)),
        display_change_toggle=Text(("Visualizzare <-> Modificare",)),
        initial_screen=Text(("videata iniziale",)),
        not_found=Text(("non è stato trovato", "non trovati")),
        does_not_exist=Text(("inesistente", "non esiste")),
        no_entries=Text(
            ("No entries found",)
        ),  # TODO translate (Manual: SAP text differs: ECC release has 'Es wurden keine Einträge gemäß Selektion gefunden' (SV 004), pack DE has 'Keine Einträge gefunden')
        row_select_hint=Text(
            ("To select a row", "To select")
        ),  # TODO translate (Manual: WebGUI framework text: ARIA hint of a selectable table row)
        user=Text(("Utente",)),
        program=Text(("Progr.",)),
    ),
    popup=PopupSection(
        type_error=Text(("Errore",)),
        type_info=Text(("Informazione",)),
        type_confirm=Text(("Confermare", "Sì", "No")),
        inactive_objects=Text(
            ("Inactive Objects",), fold=False
        ),  # TODO translate (Manual: popup title seen live; no matching text in D021T, T100 or RSMPTEXTS)
        original_language_title=Text(
            ("Different original and logon languages",), fold=False
        ),  # TODO translate (Manual: popup title seen live; the T100 messages about the original language have other wording)
        original_language_hint=RegexText(
            ("original[\\s\\S]*language", "language[\\s\\S]*original")
        ),  # TODO translate (Manual: regex over the desktop window title of the same popup)
        maintain_in_original=Text(
            ("Maint. in orig. lang.",)
        ),  # TODO translate (Manual: popup button text seen live; not found in D021T or RSMPTEXTS)
        button_labels=Text(("Sì", "No", "OK", "Interrompere")),
        close=Text(
            ("Close",), fold=False
        ),  # TODO translate (Manual: WebGUI framework tooltip of a popup's close control)
        abapgit_error_keywords=Text(("not found",)),  # TODO translate (Manual: abapGit UI text)
        abapgit_button_labels=Text(("Interrompere", "Sì", "No")),
        abapgit_inactive_objects=Text(("Inactive Objects",)),  # TODO translate (Manual: abapGit UI text)
        abapgit_transport_required=Text(("transport required",)),  # TODO translate (Manual: abapGit UI text)
        abapgit_no_task=Text(("no modifiable task", "has no task")),  # TODO translate (Manual: abapGit UI text)
    ),
    status_type=StatusTypeSection(
        error=Text(
            ("Error", "not found", "invalid")
        ),  # TODO translate (Manual: keyword list inferring the message type from its text)
        warning=Text(("Warning",)),  # TODO translate (Manual: keyword list inferring the message type from its text)
        success=Text(
            ("saved", "created", "successful")
        ),  # TODO translate (Manual: keyword list inferring the message type from its text)
        noise=Text(
            ("Message Bar", "View Details", "Execute", "Emphasized"), fold=False
        ),  # TODO translate (Manual: WebGUI framework texts of the message bar (label, buttons, emphasis))
        success_prefix=Text(
            ("Success",), fold=False
        ),  # TODO translate (Manual: WebGUI framework text: message type in the message-bar ARIA label)
        error_prefix=Text(
            ("Error",), fold=False
        ),  # TODO translate (Manual: WebGUI framework text: message type in the message-bar ARIA label)
        message_bar=Text(
            ("Message Bar",), fold=False
        ),  # TODO translate (Manual: WebGUI framework text: the message bar's ARIA label)
        check_success=Text(
            ("No syntax errors", "Object activated", "generated successfully")
        ),  # TODO translate (Manual: fragments of several syntax check and activation messages)
        check_error=Text(("syntax error",)),  # TODO translate (Manual: fragment of several syntax check messages)
        activation_confirmed=Text(("activated",)),  # TODO translate (Manual: fragment of several activation messages)
        activation_denied=Text(
            ("not activated", "not active", "could not", "cannot", "can't", "failed")
        ),  # TODO translate (Manual: negating fragments of activation messages)
    ),
    session_pages=SessionPagesSection(
        already_logged_on=Text(
            ("already logged",)
        ),  # TODO translate (Manual: WebGUI logon page (ICF), not in SAP's text tables)
        continue_button=Text(
            ("Continue",)
        ),  # TODO translate (Manual: WebGUI logon page (ICF), not in SAP's text tables)
        timed_out=Text(
            ("session timeout", "session expired", "logged off")
        ),  # TODO translate (Manual: WebGUI timeout and logoff pages (ICF), not in SAP's text tables)
        settings_menu=Text(
            ("Settings",), fold=False
        ),  # TODO translate (Manual: WebGUI framework tooltip of the settings menu)
        settings_stem=Text(("Setting",)),  # TODO translate (Manual: stem of the WebGUI settings menu tooltip)
        okcode_option=Text(
            ("OK-Code", "Transaction Field")
        ),  # TODO translate (Manual: WebGUI framework settings menu entry)
        debugger_window=Text(("ABAP debugger", "ABAP Debugger"), fold=False),
    ),
    keys=KeysSection(
        names=canonical(
            {
                Key.CTRL: Text(("Ctrl",), word=True),
                Key.SHIFT: Text(("Shift",), word=True),
                Key.ALT: Text(("Alt",), word=True),
                Key.ENTER: Text(("Invio",), word=True),
                Key.DELETE: Text(
                    ("Delete",), word=True
                ),  # TODO translate (Manual: keyboard key name of the SAP GUI client, not in SAP's text tables)
                Key.ESCAPE: Text(
                    ("Escape", "Esc"), word=True
                ),  # TODO translate (Manual: keyboard key name of the SAP GUI client, not in SAP's text tables)
            }
        ),
    ),
    abapgit=AbapgitSection(
        status_error=Text(("not found",)),  # TODO translate (Manual: abapGit UI text)
        screen_errors=Text(("transport required",)),  # TODO translate (Manual: abapGit UI text)
        se38_initial_title=Text(("videata iniziale",)),
    ),
    catalog=CatalogSection(
        screen_header=Text(
            ("Screen number",)
        ),  # TODO translate (Manual: SE16 column header of the TSTC screen number (DYPNO); EN seen in a WebGUI capture)
    ),
    quick_report=QuickReportSection(
        empty_patterns=Text(
            ("no data", "no entries", "no job", "no documents")
        ),  # TODO translate (Manual: keyword list recognising an empty result in a quick report, our own report text)
        execute_button=Text(
            ("Execute", "Execute Highlighted")
        ),  # TODO translate (Manual: button labels of the quick report selection screen, differ per report)
    ),
    se09=Se09Section(
        status=canonical(
            {
                TransportStatus.MODIFIABLE: Text(("Modificabile",)),
                TransportStatus.RELEASED: Text(("Rilasciato",)),
            }
        ),
        display_button=Text(("Visualizzare",), fold=False),
        workbench_requests=Text(("Richieste workbench",)),
        customizing_requests=Text(("Richieste customizing",)),
        expand=Text(("Esplodere",)),
        compress=Text(("Comprimere",)),
        list_region=Text(
            ("List",)
        ),  # TODO translate (Manual: WebGUI ARIA label of the ABAP list region; EN value not yet read live (#1044))
        organizer_title=Text(("Transport Organizer",)),
        request_word=Text(("Richiesta", "Rich.")),
    ),
    se11=Se11Section(
        database_table=Text(("Tabella database",)),
        data_type=Text(("Tipo dati",)),
        table_name=Text(("Nome tabella",)),
        transparent_table=Text(("Tabella trasp.",)),
        structure=Text(("Struttura",)),
        short_description=Text(("Descrizione breve",)),
        row_select_full=RegexText(
            ("To select a row, press the space bar\\.",)
        ),  # TODO translate (Manual: WebGUI framework text: ARIA hint of a selectable table row)
        data_type_name_label=Text(
            ("Name of Dictionary Type",)
        ),  # TODO translate (Manual: quick info of the DDIC type name field, WebGUI input title)
    ),
    se16=Se16Section(
        hit_count_label=Text(("N. risultati",)),
        column_selection=Text(
            ("Column for row selection",)
        ),  # TODO translate (Manual: ALV list framework text (row selection column), not in D021T)
        no_values_found=Text(("Valori non trovati",)),
        table_label=Text(("Tabella",)),
        max_hits_label=Text(("N. massimo risultati",)),
        empty_cell=Text(("Empty",)),  # TODO translate (Manual: WebGUI framework text of empty grid rows)
        table_not_found=Text(("inesistente", "non esiste", "non è attiva nel Dictionary")),
        selection_columns=Text(("Nm.campo", "Da val.", "A valore", "Nome tecnico")),
        results_title=Text(("hit", "inserimenti trovati")),
    ),
    se24=Se24Section(
        class_builder=Text(("Class Builder",)),
        initial_screen=Text(("Class Builder: videata iniziale",)),
        display_title=Template(("Class builder: visualizzare classe {name}",)),
        object_type=Text(("Tipo oggetto",)),
        class_label=Text(("Classe",)),
        interface_label=Text(("Interface",)),
        visibility=canonical(
            {
                Visibility.PUBLIC: Text(("Pubblico",)),
                Visibility.PROTECTED: Text(("Protetto",)),
                Visibility.PRIVATE: Text(("Privato",)),
            }
        ),
        static=Text(("Statico",)),
        abstract=Text(("Astratto",)),
        constant=Text(("Costante",)),
        class_field_label=Text(("Tipo oggetto", "Classe/interface")),
        methods_tab=Text(("Metodi",)),
        attributes_tab=Text(("Attributi",)),
        interfaces_tab=Text(("Interfaces",)),
        properties_tab=Text(("Proprietà",)),
        source_button=Text(("Testo sorgente",)),
        method_column=Text(("Metodo",)),
        attribute_column=Text(("Attributo",)),
        kind_column=Text(("Cat.", "Tipo")),
        visibility_column=Text(("Visibilità",)),
        description_column=Text(("Descrizione",)),
        type_ref_column=Text(("Tipo di rif.",)),
        initial_value_column=Text(("Valore iniziale",)),
    ),
    se37=Se37Section(
        initial_screen=Text(("Function Builder: videata iniziale",)),
        display_title=Template(("Function Builder: {name} Visualizzare",)),
        function_builder=Text(("Function Builder",)),
        fm_field_label=Text(("Function module",), fold=False),
        not_found=Text(("non esiste",)),
        attributes_tab=Text(("Proprietà",)),
        import_tab=Text(("Importazione",)),
        export_tab=Text(("Esportazione",)),
        changing_tab=Text(("Modifica",)),
        tables_tab=Text(("Tabelle",)),
        exceptions_tab=Text(("Eccezioni",)),
        source_tab=Text(("Testo sorgente",)),
        parameter_name_column=Text(("Nome parametro",)),
        typing_column=Text(("Tipizzaz.",)),
        type_ref_column=Text(("Tipo di rif.",)),
        default_column=Text(("Valore default",)),
        optional_column=Text(("Facolt.",)),
        pass_value_column=Text(("Trasm. val.",)),
        short_text_column=Text(("Testo breve",)),
        exception_column=Text(("Eccezione",)),
    ),
    se38=Se38Section(
        initial_screen=Text(("videata iniziale",)),
        program_field_title=Text(
            ("ABAP Program Name", "Program")
        ),  # TODO translate (Manual: title attribute of the program name input)
    ),
    se93=Se93Section(
        initial_screen=Text(("Agg. transazioni",)),
        dialog_transaction=Text(("Transazione interattiva", "transazione di dialogo")),
        report_transaction=Text(("Trans. report", "transazione report")),
        gui_html=Text(("SAP GUI per HTML",)),
        gui_java=Text(("SAP GUI per Java",)),
        gui_windows=Text(("SAP GUI per Windows",)),
        screen_number=Text(("Numero dynpro",)),
        selection_screen=Text(("Videata di selezione",)),
        start_with_variant=Text(("Avvio con variante", "Start con variante")),
        transaction_code=Text(("Codice transazione",)),
        transaction_text=Text(("Testo transazione",)),
        package=Text(("Pacchetto",)),
        auth_object=Text(("Ogg. di autorizz.",)),
    ),
    slg1=Slg1Section(
        initial_screen=Text(("Valutare reg. applicazione",)),
        log_list_screen=Text(("Visualizzare registri", "vis. registri")),
        no_logs_found=Text(("Il log non è stato trovato nel database", "log non è stato trovato")),
        log_object=Text(("Oggetto",)),
        log_subobject=Text(("Sottooggetto",)),
        external_id=Text(("Identif.esterno",)),
        from_datetime=Text(("Da (data/ora)",)),
        to_datetime=Text(("A (data/ora)",)),
        log_number=Text(("Log Number",)),  # TODO translate (Manual: list column title of the log grid, not looked up)
        col_date=Text(("Date",)),  # TODO translate (Manual: list column title of the log grid, not looked up)
        col_time=Text(("Time",)),  # TODO translate (Manual: list column title of the log grid, not looked up)
        col_messages=Text(
            ("No. Messages",)
        ),  # TODO translate (Manual: list column title of the log grid, not looked up)
        empty_cell=Text(("Empty",)),  # TODO translate (Manual: WebGUI framework text for an empty grid cell)
    ),
    sm30=Sm30Section(
        initial_screen=Text(("Aggiornamento view tabella",)),
        maintain=Text(("Agg.",)),
        table_view=Text(("Tabella/view",)),
        display_view=Text(("View",)),
        view_not_found=Text(("inesistente nel Dictionary", "inesistente")),
        no_maintenance_dialog=Text(("dialogo di agg.",)),
        view_title=Template(("Visualizza view {desc}", "Modifica view {desc}")),
        row_count=Template(("Inserimento {current} di {total}",)),
    ),
    sm37=Sm37Section(
        status=canonical(
            {
                JobStatus.SCHEDULED: Text(("Pian.", "Pianif.")),
                JobStatus.RELEASED: Text(("Rilasciato",)),
                JobStatus.READY: Text(("Pronto",)),
                JobStatus.ACTIVE: Text(("Attivo", "att.")),
                JobStatus.FINISHED: Text(("Term.", "Completo")),
                JobStatus.CANCELED: Text(("Interrotto",)),
            }
        ),
        col_status=Text(("Stato",)),
        job_name=Text(("Nome job",), fold=False),
        user_name=Text(("Nome utente",), fold=False),
        from_date=Text(
            ("From Date",)
        ),  # TODO translate (Manual: WebGUI label: 'von' / 'From' (SAPLBTCH 2170 FROM) plus the date field's own label)
        to_date=Text(
            ("To Date",)
        ),  # TODO translate (Manual: WebGUI label: 'bis' / 'To' (SAPLBTCH 2170 TO) plus the date field's own label)
        job_log_button=Text(("Registro job", "Visualizzare registro job")),
        job_log_heading=Text(("Riepilogo reg. job",), fold=False),
        job_log_title_ecc=Text(("Registro job per job",)),
        job_list_heading=Text(("Riepilogo job",), fold=False),
        no_jobs=Text(("Nessun job corrisponde",)),
        select_hint=Text(
            ("To select",), fold=False
        ),  # TODO translate (Manual: hint line of the classic list, not looked up)
        selected_hint=Text(("selezionati",), fold=False),
        event_driven=Text(("Contr.da evento",), fold=False),
        abap_program=Text(("Progr. ABAP",), fold=False),
        col_start_date=Text(("Data avvio",)),
        col_start_time=Text(("Ora avvio",)),
        col_duration=Text(("Durata", "Durata (sec.)")),
        col_created_by=Text(("Autore job",)),
        col_client=Text(("Man",)),
    ),
    spro=SproSection(
        initial_screen=Text(("Customizing: elaborazione progetto",)),
        sap_reference_img=Text(("IMG di riferim. SAP", "IMG di riferimento SAP")),
        search_button=Text(
            ("Find (Ctrl+F)",)
        ),  # TODO translate (Manual: IMG tree and toolbar texts of the customizing tool, not found in the supported text tables)
        search_dialog=Text(("Ricerca nella struttura",)),
        search_field=Text(("Chiave ric.",)),
        results_dialog=Text(("Lista ris.",)),
        column_hits=Text(("Hit trovati",)),
        column_parent=Text(("Nodo sovraordinato",)),
        column_area=Text(("Nell'area",)),
        img_heading=Text(("Visualizzare IMG",)),
    ),
    st22=St22Section(
        section=canonical(
            {
                DumpSection.WHAT_HAPPENED: Text(("Causa dell'errore",)),
                DumpSection.HOW_TO_CORRECT: Text(("Possibili soluzioni", "Indic. per la correzione")),
                DumpSection.ERROR_ANALYSIS: Text(("Analisi errori",)),
            }
        ),
        today=Text(("Oggi",)),
        yesterday=Text(("Ieri",)),
        date_field=Text(("Date",)),
        runtime_errors=Text(("Errore run-time", "Errore di run-time")),
        no_dumps=Text(("dumps brevi selezionati non esistono",)),
        col_time=Text(("Time",)),
        col_program=Text(("Canceled Program",)),
        col_error_type=Text(("Runtime Errors", "Runtime Error")),
        col_short_text=Text(("Short Text", "Testo breve")),
        call_stack_heading=Text(("Chiamate/eventi attivi",)),
        other_headings=Text(
            (
                "Ambiente sistema",
                "Utente e transazione",
                "Informazioni punto di interr.",
                "Dett. testo sorgente",
                "Contenuto campi sistema",
                "Variabili selezionate",
                "Chiam. attive in kernel SAP",
                "Testo breve",
                "Note interne",
            )
        ),
        source_code_of=RegexText(("Source Code of",)),
        source_code_start=RegexText(("Dett\\. testo sorgente",)),
        source_line=Text(("Source Code Line",)),
        line=Text(("Riga",)),
    ),
)
