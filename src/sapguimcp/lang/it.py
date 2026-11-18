"""IT language pack (#1041, #1044).

Texts come from SAP (``scripts/harvest_lang_texts.py IT --draft`` and ``--verify``) or from the screen read with an
Italian logon. Adding a language: see ``ADDING_A_LANGUAGE.md``.
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

IT = LanguagePack(
    code="IT",
    html_lang="it",
    logon_dropdown="Italiano",
    date_format="%d.%m.%Y",  # T005X-DATFM = 1 for country IT
    same_as_en=frozenset(
        {
            "keys.names[Alt]",
            "keys.names[Ctrl]",
            "keys.names[Escape]",
            "popup.abapgit_no_task",
            "popup.abapgit_transport_required",
            "se24.interface_label",
            "se24.interfaces_tab",
            "sm30.display_view",
            "st22.col_error_type",
            "st22.col_time",
            "st22.date_field",
        }
    ),
    common=CommonSection(
        display=Text(("Visualizzare",)),
        not_found=Text(("non è stato trovato", "non trovati")),
        does_not_exist=Text(("inesistente", "non esiste")),
        no_entries=Text(("Non sono stati trovati inserimenti",)),
        user=Text(("Utente",)),
        program=Text(("Programma", "Progr.")),
    ),
    popup=PopupSection(
        type_error=Text(("Errore",)),
        type_info=Text(("Informazione",)),
        type_confirm=Text(("Confermare", "Sì", "No")),
        inactive_objects=Text(("Oggetti inattivi",), fold=False),
        original_language_hint=RegexText(("originale[\\s\\S]*lingua", "lingua[\\s\\S]*originale")),
        maintain_in_original=Text(("Agg. in lingua orig.",)),
        abapgit_error_keywords=Text(("not found", "non trovat", "errore", "fallit")),
        abapgit_button_labels=Text(("Interrompere", "Sì", "No")),
        abapgit_inactive_objects=Text(("Oggetti inattivi", "Inactive Objects")),
        abapgit_transport_required=Text(("transport required",)),
        abapgit_no_task=Text(("no modifiable task", "has no task")),
    ),
    status_type=StatusTypeSection(
        activation_confirmed=Text(("attivato", "attivati", "attivata")),
        activation_denied=Text(
            (
                "non è stato attivato",
                "non è stata attivata",
                "non sono stati attivati",
                "non sono state attivate",
                "non attiv",
                "impossibile",
                "non può",
                "non possibile",
                "fallit",
                "disattiv",
                "inattiv",
            )
        ),
    ),
    session_pages=SessionPagesSection(
        settings_stem=Text(("Impostazion",)),
        debugger_window=Text(("ABAP debugger", "ABAP Debugger"), fold=False),
    ),
    keys=KeysSection(
        names=canonical(
            {
                Key.CTRL: Text(("Ctrl",), word=True),
                Key.SHIFT: Text(("Shift", "Maiusc"), word=True),
                Key.ALT: Text(("Alt",), word=True),
                Key.ENTER: Text(("Invio", "Enter", "Inserimento"), word=True),
                Key.DELETE: Text(("Cancellare", "Delete"), word=True),
                Key.ESCAPE: Text(("Escape", "Esc"), word=True),
            }
        ),
    ),
    abapgit=AbapgitSection(
        status_error=Text(("not found", "non trovat", "errore")),
        screen_errors=Text(("transport required", "non trovat")),
    ),
    catalog=CatalogSection(
        screen_header=Text(("Dynpro", "N.dynpro")),
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
    ),
    se11=Se11Section(
        table_name=Text(("Nome tabella",)),
    ),
    se16=Se16Section(
        results_title=Text(("hit", "inserimenti trovati")),
    ),
    se24=Se24Section(
        initial_screen=Text(("Class Builder: videata iniziale",)),
        object_type=Text(("Tipo oggetto",)),
        interface_label=Text(("Interface",)),
        # The methods/attributes table controls show the DDIC domain texts in English on IT logons too
        # (live check on both releases), so the English words are variants of the IT pack.
        visibility=canonical(
            {
                Visibility.PUBLIC: Text(("Pubblico", "Public")),
                Visibility.PROTECTED: Text(("Protetto", "Protected")),
                Visibility.PRIVATE: Text(("Privato", "Private")),
            }
        ),
        static=Text(("Statico", "Static")),
        abstract=Text(("Astratto", "Abstract")),
        constant=Text(("Costante", "Constant")),
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
        fm_field_label=Text(("Function module",), fold=False),
        attributes_tab=Text(("Proprietà",)),
        import_tab=Text(("Importazione",)),
        export_tab=Text(("Esportazione",)),
        changing_tab=Text(("Modifica",)),
        tables_tab=Text(("Tabelle",)),
        exceptions_tab=Text(("Eccezioni",)),
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
        program_field_title=Text(("Nome programma ABAP", "Programma")),
    ),
    se93=Se93Section(
        transaction_code=Text(("Codice transazione",)),
    ),
    slg1=Slg1Section(
        no_logs_found=Text(("Il log non è stato trovato nel database", "log non è stato trovato")),
        log_object=Text(("Oggetto",)),
        log_subobject=Text(("Sottooggetto",)),
        external_id=Text(("Identif.esterno",)),
        log_number=Text(("Numero registro", "N. registro")),
        col_date=Text(("Data",)),
        col_time=Text(("Ora",)),
        col_messages=Text(("Messaggi totali",)),
    ),
    sm30=Sm30Section(
        maintain=Text(("Agg.",)),
        table_view=Text(("Tabella/view",)),
        display_view=Text(("View",)),
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
        job_name=Text(("Nome job", "Nm. job"), fold=False),  # "Nm. job": header of the job list
        job_log_button=Text(("Registro job", "Visualizzare registro job")),
        job_log_heading=Text(("Riepilogo reg. job",), fold=False),
        job_log_title_ecc=Text(("Registro job per job",)),
        no_jobs=Text(("Nessun job corrisponde",)),
        select_hint=Text(("Per selezionare",), fold=False),
        selected_hint=Text(("selezionati",), fold=False),
        col_start_date=Text(("Data avvio",)),
        col_start_time=Text(("Ora avvio",)),
        col_duration=Text(("Durata", "Durata (sec.)")),
        col_created_by=Text(("Autore job",)),
        col_client=Text(("Man",)),
    ),
    spro=SproSection(
        sap_reference_img=Text(("IMG di riferim. SAP", "IMG di riferimento SAP")),
        search_dialog=Text(("Ricerca nella struttura",)),
        search_field=Text(("Chiave ric.",)),
        column_hits=Text(("Hit trovati",)),
        column_parent=Text(("Nodo sovraordinato",)),
        column_area=Text(("Nell'area",)),
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
    ),
)
