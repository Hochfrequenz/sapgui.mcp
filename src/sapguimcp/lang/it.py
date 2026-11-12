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
    same_as_en=frozenset(),  # TODO field paths that deliberately equal EN
    common=CommonSection(
        display=Text(("Display",)),  # TODO fragment of: @10@ Visualizzare
        display_change_toggle=Text(
            ("Display <-> Change",)
        ),  # TODO translate (Manual: WebGUI toolbar tooltip of the display/change toggle)
        initial_screen=Text(
            ("Initial",)
        ),  # TODO translate (Manual: title fragment shared by the initial screens of several transactions)
        not_found=Text(("not found",)),  # TODO fragment of: L'oggetto richiesto non è stato trovato
        does_not_exist=Text(("does not exist",)),  # TODO fragment of: Richiesta/task &1 inesistente
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
        type_error=Text(("Error",)),  # TODO translate (Manual: keyword list classifying popups by title or text)
        type_info=Text(("Information",)),  # TODO translate (Manual: keyword list classifying popups by title or text)
        type_confirm=Text(
            ("Confirm", "Yes", "No")
        ),  # TODO translate (Manual: keyword list classifying popups by title or text)
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
        button_labels=Text(
            ("Yes", "No", "OK", "Cancel")
        ),  # TODO translate (Manual: standard popup button labels, several GUI statuses)
        close=Text(
            ("Close",), fold=False
        ),  # TODO translate (Manual: WebGUI framework tooltip of a popup's close control)
        abapgit_error_keywords=Text(("not found",)),  # TODO translate (Manual: abapGit UI text)
        abapgit_button_labels=Text(("OK", "Cancel", "Yes", "No")),  # TODO translate (Manual: abapGit UI text)
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
        debugger_window=Text(
            ("ABAP Debugger",), fold=False
        ),  # TODO translate (Manual: SAP GUI window title of the ABAP debugger)
    ),
    keys=KeysSection(
        names=canonical(
            {
                Key.CTRL: Text(
                    ("Ctrl",), word=True
                ),  # TODO translate (Manual: keyboard key name of the SAP GUI client, not in SAP's text tables)
                Key.SHIFT: Text(
                    ("Shift",), word=True
                ),  # TODO translate (Manual: keyboard key name of the SAP GUI client, not in SAP's text tables)
                Key.ALT: Text(
                    ("Alt",), word=True
                ),  # TODO translate (Manual: keyboard key name of the SAP GUI client, not in SAP's text tables)
                Key.ENTER: Text(
                    ("Enter",), word=True
                ),  # TODO translate (Manual: keyboard key name of the SAP GUI client, not in SAP's text tables)
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
        se38_initial_title=Text(
            ("Initial Screen",)
        ),  # TODO translate (Manual: abapGit UI text; title of the SE38 initial screen, read live in DE and EN)
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
        display_button=Text(("Display",), fold=False),  # TODO fragment of: @10@ Visualizzare
        workbench_requests=Text(
            ("Workbench Requests",)
        ),  # TODO translate (Manual: SAP text differs: TRFUNCTION K is the singular 'Workbench-Auftrag' / 'Workbench Request'; the SE09 tree node holds the plural)
        customizing_requests=Text(
            ("Customizing Requests",)
        ),  # TODO translate (Manual: SAP text differs: TRFUNCTION W is the singular 'Customizing-Auftrag' / 'Customizing Request'; the SE09 tree node holds the plural)
        expand=Text(("Expand",)),  # TODO translate (Manual: tree toolbar tooltip, generic text of many GUI statuses)
        compress=Text(
            ("Compress",)
        ),  # TODO translate (Manual: tree toolbar tooltip, generic text of many GUI statuses)
        list_region=Text(
            ("List",)
        ),  # TODO translate (Manual: WebGUI ARIA label of the ABAP list region; EN value not yet read live (#1044))
        organizer_title=Text(("Transport Organizer",)),
        request_word=Text(
            ("Request",)
        ),  # TODO translate (Manual: word inside SE09 list texts and messages, no single source)
    ),
    se11=Se11Section(
        database_table=Text(("Tabella database",)),
        data_type=Text(("Tipo dati",)),
        table_name=Text(("Nome tabella",)),
        transparent_table=Text(
            ("Transparent Table",)
        ),  # TODO translate (Manual: SAP text differs: DE domain value TABCLASS TRANSP is 'Transparente Tabelle', pack has 'Transp.Tabelle' (EN 'Transparent table' matches))
        structure=Text(("Struttura",)),
        short_description=Text(
            ("Short Description",)
        ),  # TODO translate (Manual: SAP text differs: EN data element DDTEXT is 'Short text', pack has 'Short Description')
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
        no_values_found=Text(("no values found",)),  # TODO fragment of: Valori non trovati
        table_label=Text(("Tabella",)),
        max_hits_label=Text(("N. massimo risultati",)),
        empty_cell=Text(("Empty",)),  # TODO translate (Manual: WebGUI framework text of empty grid rows)
        table_not_found=Text(("does not exist",)),  # TODO fragment of: Richiesta/task &1 inesistente
        selection_columns=Text(
            ("Field Name", "From-Value", "To-Value", "Technical Name")
        ),  # TODO translate (Manual: column headers of the selection grid, composed from several data elements)
        results_title=Text(("hits", "entries")),  # TODO translate (Manual: composed title fragment of the result list)
    ),
    se24=Se24Section(
        class_builder=Text(
            ("Class Builder",)
        ),  # TODO translate (Manual: SAP text differs: transaction SE24 is 'ABAP Class Builder' in both languages; pack DE has 'Klassenpflege')
        initial_screen=Text(
            ("Class Builder: Initial Screen", "Class Builder: Initial")
        ),  # TODO translate (Manual: window title of the class builder initial screen (titlebar, not in the supported text tables))
        display_title=Template(
            ("Class Builder: Display {name}",)
        ),  # TODO translate (Manual: composed window title of the class builder)
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
        abstract=Text(
            ("Abstract",)
        ),  # TODO translate (Manual: screen text SAPLSEOD 0351 VSEOMETHOD-MTDABSTRCT exists on the S/4HANA release only)
        constant=Text(("Costante",)),
        class_field_label=Text(
            ("Object Type", "Class/Interface")
        ),  # TODO translate (Manual: input field label/title of the class builder initial screen)
        methods_tab=Text(("Methods",)),  # TODO translate (Manual: tab title of the class builder tab strip)
        attributes_tab=Text(("Attributes",)),  # TODO translate (Manual: tab title of the class builder tab strip)
        interfaces_tab=Text(("Interfaces",)),  # TODO translate (Manual: tab title of the class builder tab strip)
        properties_tab=Text(("Properties",)),  # TODO translate (Manual: tab title of the class builder tab strip)
        source_button=Text(
            ("Source Code", "Sourcecode")
        ),  # TODO translate (Manual: button text of the class builder method list)
        method_column=Text(("Method",)),  # TODO translate (Manual: table control column title of the methods tab)
        attribute_column=Text(
            ("Attribute",)
        ),  # TODO translate (Manual: table control column title of the attributes tab)
        kind_column=Text(
            ("Level",)
        ),  # TODO translate (Manual: table control column title of the methods and attributes tabs)
        visibility_column=Text(
            ("Visibility",)
        ),  # TODO translate (Manual: table control column title of the methods and attributes tabs)
        description_column=Text(
            ("Description",)
        ),  # TODO translate (Manual: table control column title of the class builder tabs)
        type_ref_column=Text(
            ("Assoc.Type",)
        ),  # TODO translate (Manual: table control column title of the attributes tab)
        initial_value_column=Text(
            ("Initial Value",)
        ),  # TODO translate (Manual: table control column title of the attributes tab)
    ),
    se37=Se37Section(
        initial_screen=Text(
            ("Function Builder: Initial Screen",)
        ),  # TODO translate (Manual: window title of the function builder initial screen (titlebar, not in the supported text tables))
        display_title=Template(
            ("Function Builder: Display {name}",)
        ),  # TODO translate (Manual: composed window title of the function builder)
        function_builder=Text(("Function Builder",)),  # TODO translate (Manual: title fragment of the function builder)
        fm_field_label=Text(("Function module",), fold=False),
        not_found=Text(("does not exist",)),  # TODO fragment of: Il function module & non esiste ancora
        attributes_tab=Text(("Attributes",)),  # TODO translate (Manual: tab title of the function builder tab strip)
        import_tab=Text(("Import",)),  # TODO translate (Manual: tab title of the function builder tab strip)
        export_tab=Text(("Export",)),  # TODO translate (Manual: tab title of the function builder tab strip)
        changing_tab=Text(("Changing",)),  # TODO translate (Manual: tab title of the function builder tab strip)
        tables_tab=Text(("Tables",)),  # TODO translate (Manual: tab title of the function builder tab strip)
        exceptions_tab=Text(("Exceptions",)),  # TODO translate (Manual: tab title of the function builder tab strip)
        source_tab=Text(
            ("Source Code", "Source text")
        ),  # TODO translate (Manual: tab title of the function builder tab strip)
        parameter_name_column=Text(
            ("Parameter Name",)
        ),  # TODO translate (Manual: table control column title of the signature tabs)
        typing_column=Text(("Typing",)),  # TODO translate (Manual: table control column title of the signature tabs)
        type_ref_column=Text(
            ("Associated Type",)
        ),  # TODO translate (Manual: table control column title of the signature tabs)
        default_column=Text(
            ("Default Value",)
        ),  # TODO translate (Manual: table control column title of the signature tabs)
        optional_column=Text(
            ("Optional",)
        ),  # TODO translate (Manual: table control column title of the signature tabs)
        pass_value_column=Text(
            ("Pass Value",)
        ),  # TODO translate (Manual: table control column title of the signature tabs)
        short_text_column=Text(
            ("Short Text",)
        ),  # TODO translate (Manual: table control column title of the signature and exception tabs)
        exception_column=Text(
            ("Exception",)
        ),  # TODO translate (Manual: table control column title of the exceptions tab)
    ),
    se38=Se38Section(
        initial_screen=Text(
            ("Initial Screen",)
        ),  # TODO translate (Manual: title fragment of the ABAP editor initial screen)
        program_field_title=Text(
            ("ABAP Program Name", "Program")
        ),  # TODO translate (Manual: title attribute of the program name input)
    ),
    se93=Se93Section(
        initial_screen=Text(
            ("Transaction Maintenance", "Maintain Transaction")
        ),  # TODO translate (Manual: SAP text differs: transaction SE93 is 'Maintain Transaction Codes' / 'Pflege Transaktionscodes'; pack DE has 'Transaktionspflege')
        dialog_transaction=Text(
            ("Dialog Transaction",)
        ),  # TODO translate (Manual: EN screen text SAPLSEUK 0300 RSSTCD-S_TRANS; no DE text in D021T)
        report_transaction=Text(
            ("Report Transaction",)
        ),  # TODO translate (Manual: EN screen text SAPLSEUK 0300 RSSTCD-S_REPORT; no DE text in D021T)
        gui_html=Text(("SAP GUI per HTML",)),
        gui_java=Text(("SAP GUI per Java",)),
        gui_windows=Text(("SAP GUI per Windows",)),
        screen_number=Text(
            ("Screen number",)
        ),  # TODO translate (Manual: SAP text differs: EN screen text is 'Dynpro Number' on the S/4HANA release ('Screen number' on the ECC release); pack has 'Screen number')
        selection_screen=Text(("Videata di selezione",)),
        start_with_variant=Text(("Avvio con variante", "Start con variante")),
        transaction_code=Text(("Codice transazione",)),
        transaction_text=Text(("Testo transazione",)),
        package=Text(("Pacchetto",)),
        auth_object=Text(("Ogg. di autorizz.",)),
    ),
    slg1=Slg1Section(
        initial_screen=Text(
            ("Analyze Application Log",)
        ),  # TODO translate (Manual: window title of the log selection screen (titlebar, not in the supported text tables))
        log_list_screen=Text(("Display Logs",)),  # TODO fragment of: Reg. applicazione: vis. registri
        no_logs_found=Text(
            ("No log found in the database", "No logs", "No application log")
        ),  # TODO fragment of: Il log non è stato trovato nel database
        log_object=Text(
            ("Object",)
        ),  # TODO translate (Manual: selection text of report SBAL_DISPLAY (text pool), not in D021T)
        log_subobject=Text(
            ("Subobject",)
        ),  # TODO translate (Manual: selection text of report SBAL_DISPLAY (text pool), not in D021T)
        external_id=Text(
            ("External ID",)
        ),  # TODO translate (Manual: selection text of report SBAL_DISPLAY (text pool), not in D021T)
        from_datetime=Text(
            ("From (Date/Time)",)
        ),  # TODO translate (Manual: selection text of report SBAL_DISPLAY (text pool), not in D021T)
        to_datetime=Text(
            ("To (Date/Time)",)
        ),  # TODO translate (Manual: selection text of report SBAL_DISPLAY (text pool), not in D021T)
        log_number=Text(("Log Number",)),  # TODO translate (Manual: list column title of the log grid, not looked up)
        col_date=Text(("Date",)),  # TODO translate (Manual: list column title of the log grid, not looked up)
        col_time=Text(("Time",)),  # TODO translate (Manual: list column title of the log grid, not looked up)
        col_messages=Text(
            ("No. Messages",)
        ),  # TODO translate (Manual: list column title of the log grid, not looked up)
        empty_cell=Text(("Empty",)),  # TODO translate (Manual: WebGUI framework text for an empty grid cell)
    ),
    sm30=Sm30Section(
        initial_screen=Text(
            ("Table View Maintenance",)
        ),  # TODO translate (Manual: SAP text differs: transaction SM30 is 'Call View Maintenance' / 'Aufruf View-Pflege'; pack has 'Table View Maintenance' / 'Tabellensicht-Pflege')
        maintain=Text(
            ("Maintain", "Edit")
        ),  # TODO translate (Manual: SAP text differs: EN screen text SAPMSVMA 0100 UPDATE_PUSH is 'Edit' on the S/4HANA release ('Maintain' on the ECC release); pack has 'Maintain')
        table_view=Text(("Tabella/view",)),
        display_view=Text(("View",)),  # TODO translate (Manual: view-type word inside the composed SM30 titles)
        view_not_found=Text(
            ("is not in the Dictionary", "does not exist", "not found")
        ),  # TODO fragment of: Tabella/view &1 inesistente nel Dictionary
        no_maintenance_dialog=Text(
            ("no maintenance dialog",)
        ),  # TODO translate (Manual: no single T100 message has the fragment in both languages (SV 432 EN only, SV 790 DE only))
        view_title=Template(
            ("Display View {desc}", "Change View {desc}")
        ),  # TODO translate (Manual: composed window title of the view maintenance)
        row_count=Template(
            ("Entry {current} of {total}",)
        ),  # TODO translate (Manual: WebGUI composed status text of the entry counter)
    ),
    sm37=Sm37Section(
        status=canonical(
            {
                JobStatus.SCHEDULED: Text(("Pian.",)),
                JobStatus.RELEASED: Text(("Rilasciato",)),
                JobStatus.READY: Text(("Pronto",)),
                JobStatus.ACTIVE: Text(("Attivo",)),
                JobStatus.FINISHED: Text(("Term.",)),
                JobStatus.CANCELED: Text(("Interrotto",)),
            }
        ),
        col_status=Text(("Status",)),  # TODO translate (Manual: list column title of the job overview, not looked up)
        job_name=Text(("Nome job",), fold=False),
        user_name=Text(("Nome utente",), fold=False),
        from_date=Text(
            ("From Date",)
        ),  # TODO translate (Manual: WebGUI label: 'von' / 'From' (SAPLBTCH 2170 FROM) plus the date field's own label)
        to_date=Text(
            ("To Date",)
        ),  # TODO translate (Manual: WebGUI label: 'bis' / 'To' (SAPLBTCH 2170 TO) plus the date field's own label)
        job_log_button=Text(("Registro job", "Visualizzare registro job")),
        job_log_heading=Text(
            ("Job Log Entries",), fold=False
        ),  # TODO translate (Manual: title of the job log list, not in the GUI status)
        job_log_title_ecc=Text(
            ("Job Log for Job",)
        ),  # TODO translate (Manual: title of the job log screen on the ECC release, not looked up)
        job_list_heading=Text(
            ("Job Overview",), fold=False
        ),  # TODO translate (Manual: title of the job overview list, not looked up)
        no_jobs=Text(
            ("No job match", "No jobs found")
        ),  # TODO fragment of: Nessun job corrisponde alle condizioni di selezione indicate
        select_hint=Text(
            ("To select",), fold=False
        ),  # TODO translate (Manual: hint line of the classic list, not looked up)
        selected_hint=Text(
            ("Selected",), fold=False
        ),  # TODO translate (Manual: footer line of the classic list, not looked up)
        event_driven=Text(
            ("event-driven",), fold=False
        ),  # TODO translate (Manual: start condition line of the classic list, not looked up)
        abap_program=Text(
            ("ABAP Program",), fold=False
        ),  # TODO translate (Manual: step line of the classic list, not looked up)
        col_start_date=Text(
            ("Start Date",)
        ),  # TODO translate (Manual: list column title of the job overview, not looked up)
        col_start_time=Text(
            ("Start Time",)
        ),  # TODO translate (Manual: list column title of the job overview, not looked up)
        col_duration=Text(
            ("Duration", "Duration(sec.)")
        ),  # TODO translate (Manual: list column title of the job overview, not looked up)
        col_created_by=Text(
            ("Created By", "Job Created By", "Job CreatedB")
        ),  # TODO translate (Manual: list column title of the job overview, not looked up)
        col_client=Text(
            ("Client", "Cli")
        ),  # TODO translate (Manual: list column title of the job overview, not looked up)
    ),
    spro=SproSection(
        initial_screen=Text(
            ("Customizing: Execute Project",)
        ),  # TODO translate (Manual: SAP text differs: transaction SPRO is 'Customizing - Edit Project' in both languages; pack has the screen titles 'Customizing: Projektbearbeitung' / 'Customizing: Execute Project')
        sap_reference_img=Text(
            ("SAP Reference IMG",)
        ),  # TODO translate (Manual: IMG tree and toolbar texts of the customizing tool, not found in the supported text tables)
        search_button=Text(
            ("Find (Ctrl+F)",)
        ),  # TODO translate (Manual: IMG tree and toolbar texts of the customizing tool, not found in the supported text tables)
        search_dialog=Text(
            ("Search in the structure",)
        ),  # TODO translate (Manual: IMG search dialog texts, not found in the supported text tables)
        search_field=Text(
            ("Search Term",)
        ),  # TODO translate (Manual: IMG search dialog texts, not found in the supported text tables)
        results_dialog=Text(
            ("Hit List",)
        ),  # TODO translate (Manual: IMG search dialog texts, not found in the supported text tables)
        column_hits=Text(
            ("Hits",)
        ),  # TODO translate (Manual: IMG search dialog texts, not found in the supported text tables)
        column_parent=Text(
            ("Parent Node",)
        ),  # TODO translate (Manual: IMG search dialog texts, not found in the supported text tables)
        column_area=Text(
            ("In area",)
        ),  # TODO translate (Manual: IMG search dialog texts, not found in the supported text tables)
        img_heading=Text(
            ("Display IMG",)
        ),  # TODO translate (Manual: window title of the IMG display (titlebar, not in the supported text tables))
    ),
    st22=St22Section(
        section=canonical(
            {
                DumpSection.WHAT_HAPPENED: Text(
                    ("What happened?",)
                ),  # TODO translate (Manual: heading of the dump detail text (spec section 9))
                DumpSection.HOW_TO_CORRECT: Text(
                    ("How to Correct the Error", "What can you do?")
                ),  # TODO translate (Manual: heading of the dump detail text (spec section 9))
                DumpSection.ERROR_ANALYSIS: Text(
                    ("Error Analysis",)
                ),  # TODO translate (Manual: heading of the dump detail text (spec section 9))
            }
        ),
        today=Text(
            ("Today",)
        ),  # TODO translate (Manual: pushbutton text of report RSSHOWRABAX (selection screen), not in D021T)
        yesterday=Text(
            ("Yesterday",)
        ),  # TODO translate (Manual: pushbutton text of report RSSHOWRABAX (selection screen), not in D021T)
        date_field=Text(
            ("Date",)
        ),  # TODO translate (Manual: selection text of report RSSHOWRABAX (text pool), not in D021T)
        runtime_errors=Text(
            ("Runtime Errors", "Runtime Error")
        ),  # TODO translate (Manual: button and heading text of report RSSHOWRABAX, not in D021T)
        no_dumps=Text(
            ("No entries found", "No short dumps", "No dumps")
        ),  # TODO translate (Manual: union of the former tool and parser lists, status text of the ST22 list)
        col_time=Text(("Time",)),  # TODO translate (Manual: list column title of the dump list, not looked up)
        col_program=Text(
            ("Program", "Terminated Program")
        ),  # TODO translate (Manual: list column title of the dump list, not looked up)
        col_error_type=Text(
            ("Runtime Errors", "Runtime Error")
        ),  # TODO translate (Manual: list column title of the dump list, not looked up)
        col_short_text=Text(
            ("Short Text",)
        ),  # TODO translate (Manual: list column title of the dump list, not looked up)
        call_stack_heading=Text(
            ("Active Calls/Events", "Active Calls", "Call Stack")
        ),  # TODO translate (Manual: heading of the dump detail text (spec section 9))
        other_headings=Text(
            (
                "System Environment",
                "User-Specific System Environment",
                "Information on Where Terminated",
                "Source Code Extract",
                "Contents of System Fields",
                "Chosen Variables",
                "Active Calls in SAP Kernel",
                "User and Transaction",
                "Short Text",
                "Internal Notes",
            )
        ),  # TODO translate (Manual: headings of the dump detail text (spec section 9))
        source_code_of=RegexText(("Source Code of",)),  # TODO translate (Manual: text of the dump detail)
        source_code_start=RegexText(
            ("Source Code",)
        ),  # TODO translate (Manual: heading of the dump detail text (spec section 9))
        source_line=Text(("Source Code Line",)),  # TODO translate (Manual: text of the dump detail)
        line=Text(("Line",)),  # TODO translate (Manual: text of the dump detail)
    ),
)
