"""English language pack (SAP logon language EN); the fallback merged into every session view.

A new language starts as a copy of this module; follow ``ADDING_A_LANGUAGE.md`` in this package.
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

EN = LanguagePack(
    code="EN",
    date_format="%m/%d/%Y",
    same_as_en=frozenset(),
    common=CommonSection(
        display=Text(("Display",)),
        not_found=Text(("not found",)),
        does_not_exist=Text(("does not exist",)),
        no_entries=Text(("No entries found",)),
        user=Text(("User",)),
        program=Text(("Program",)),
    ),
    popup=PopupSection(
        type_error=Text(("Error",)),
        type_info=Text(("Information",)),
        type_confirm=Text(("Confirm", "Yes", "No")),
        inactive_objects=Text(("Inactive Objects",), fold=False),
        original_language_hint=RegexText((r"original[\s\S]*language", r"language[\s\S]*original")),
        maintain_in_original=Text(("Maint. in orig. lang.",)),
        abapgit_error_keywords=Text(("not found",)),
        abapgit_button_labels=Text(("OK", "Cancel", "Yes", "No")),
        abapgit_inactive_objects=Text(("Inactive Objects",)),
        abapgit_transport_required=Text(("transport required",)),
        abapgit_no_task=Text(("no modifiable task", "has no task")),
    ),
    status_type=StatusTypeSection(
        # Case-sensitive: "executed successfully" or "authorized to execute" in a message must survive.
        activation_confirmed=Text(("activated",)),
        activation_denied=Text(("not activated", "not active", "could not", "cannot", "can't", "failed")),
    ),
    session_pages=SessionPagesSection(
        debugger_window=Text(("ABAP Debugger",), fold=False),
    ),
    keys=KeysSection(
        names=canonical(
            {
                Key.CTRL: Text(("Ctrl",), word=True),
                Key.SHIFT: Text(("Shift",), word=True),
                Key.ALT: Text(("Alt",), word=True),
                Key.ENTER: Text(("Enter",), word=True),
                Key.DELETE: Text(("Delete",), word=True),
                Key.ESCAPE: Text(("Escape", "Esc"), word=True),
            }
        ),
    ),
    abapgit=AbapgitSection(
        status_error=Text(("not found",)),
        screen_errors=Text(("transport required",)),
        # Read live with an EN logon: the SE38 initial screen is titled "ABAP Editor: Initial Screen".
    ),
    catalog=CatalogSection(screen_header=Text(("Screen number",))),
    se09=Se09Section(
        status=canonical(
            {
                TransportStatus.MODIFIABLE: Text(("Modifiable",)),
                TransportStatus.RELEASED: Text(("Released",)),
            }
        ),
        display_button=Text(("Display",), fold=False),
        workbench_requests=Text(("Workbench Requests",)),
        customizing_requests=Text(("Customizing Requests",)),
        expand=Text(("Expand",)),
        compress=Text(("Compress",)),
    ),
    se11=Se11Section(
        table_name=Text(("Table name",)),
    ),
    se16=Se16Section(
        results_title=Text(("hits", "entries")),
    ),
    se24=Se24Section(
        initial_screen=Text(("Class Builder: Initial Screen", "Class Builder: Initial")),
        object_type=Text(("Object Type",)),
        interface_label=Text(("Interface",)),
        visibility=canonical(
            {
                Visibility.PUBLIC: Text(("Public",)),
                Visibility.PROTECTED: Text(("Protected",)),
                Visibility.PRIVATE: Text(("Private",)),
            }
        ),
        static=Text(("Static",)),
        abstract=Text(("Abstract",)),
        constant=Text(("Constant",)),
        class_field_label=Text(("Object Type", "Class/Interface")),
        methods_tab=Text(("Methods",)),
        attributes_tab=Text(("Attributes",)),
        interfaces_tab=Text(("Interfaces",)),
        properties_tab=Text(("Properties",)),
        source_button=Text(("Source Code", "Sourcecode")),
        method_column=Text(("Method",)),
        attribute_column=Text(("Attribute",)),
        kind_column=Text(("Level",)),
        visibility_column=Text(("Visibility",)),
        description_column=Text(("Description",)),
        type_ref_column=Text(("Assoc.Type",)),
        initial_value_column=Text(("Initial Value",)),
    ),
    se37=Se37Section(
        fm_field_label=Text(("Function Module", "Function module"), fold=False),
        attributes_tab=Text(("Attributes",)),
        import_tab=Text(("Import",)),
        export_tab=Text(("Export",)),
        changing_tab=Text(("Changing",)),
        tables_tab=Text(("Tables",)),
        exceptions_tab=Text(("Exceptions",)),
        source_tab=Text(("Source Code", "Source text")),
        parameter_name_column=Text(("Parameter Name",)),
        typing_column=Text(("Typing",)),
        type_ref_column=Text(("Associated Type",)),
        default_column=Text(("Default Value",)),
        optional_column=Text(("Optional",)),
        pass_value_column=Text(("Pass Value",)),
        short_text_column=Text(("Short Text",)),
        exception_column=Text(("Exception",)),
    ),
    se38=Se38Section(
        initial_screen=Text(("Initial Screen",)),
        program_field_title=Text(("ABAP Program Name", "Program")),
    ),
    se93=Se93Section(
        transaction_code=Text(
            ("Transaction code", "Transaction Code")
        ),  # exact-case title lookups: both spellings exist
    ),
    slg1=Slg1Section(
        # BL 208 in EN.
        no_logs_found=Text(("No log found in the database", "No logs", "No application log")),
        log_object=Text(("Object",)),
        log_subobject=Text(("Subobject",)),
        external_id=Text(("External ID",)),
        log_number=Text(("Log Number",)),
        col_date=Text(("Date",)),
        col_time=Text(("Time",)),
        col_messages=Text(("No. Messages",)),
    ),
    sm30=Sm30Section(
        maintain=Text(("Maintain", "Edit")),
        table_view=Text(("Table/View",)),
        display_view=Text(("View",)),
    ),
    sm37=Sm37Section(
        status=canonical(
            {
                JobStatus.SCHEDULED: Text(("Scheduled", "Sched.")),
                JobStatus.RELEASED: Text(("Released",)),
                JobStatus.READY: Text(("Ready",)),
                JobStatus.ACTIVE: Text(("Active",)),
                JobStatus.FINISHED: Text(("Finished",)),
                JobStatus.CANCELED: Text(("Canceled",)),
            }
        ),
        col_status=Text(("Status",)),
        job_name=Text(("Job Name", "Job name", "JobName"), fold=False),  # "JobName": header of the job list
        job_log_button=Text(("Job Log",)),
        job_log_heading=Text(("Job Log Entries",), fold=False),
        job_log_title_ecc=Text(("Job Log for Job",)),
        no_jobs=Text(("No job match", "No jobs found")),
        select_hint=Text(("To select",), fold=False),
        selected_hint=Text(("Selected",), fold=False),
        col_start_date=Text(("Start Date",)),
        col_start_time=Text(("Start Time",)),
        col_duration=Text(("Duration", "Duration(sec.)")),
        col_created_by=Text(("Created By", "Job Created By", "Job CreatedB")),  # "Job CreatedB": truncated header
        col_client=Text(("Client", "Cli")),
    ),
    spro=SproSection(
        sap_reference_img=Text(("SAP Reference IMG",)),
        search_dialog=Text(("Search in the structure",)),
        search_field=Text(("Search Term",)),
        column_hits=Text(("Hits",)),
        column_parent=Text(("Parent Node",)),
        column_area=Text(("In area",)),
    ),
    st22=St22Section(
        section=canonical(
            {
                DumpSection.WHAT_HAPPENED: Text(("What happened?",)),
                DumpSection.HOW_TO_CORRECT: Text(("How to Correct the Error", "What can you do?")),
                DumpSection.ERROR_ANALYSIS: Text(("Error Analysis",)),
            }
        ),
        today=Text(("Today",)),
        yesterday=Text(("Yesterday",)),
        date_field=Text(("Date",)),
        no_dumps=Text(("No entries found", "No short dumps", "No dumps")),
        col_time=Text(("Time",)),
        col_program=Text(("Program", "Terminated Program", "Canceled Program")),
        col_error_type=Text(("Runtime Errors", "Runtime Error")),
        col_short_text=Text(("Short Text",)),
        call_stack_heading=Text(("Active Calls/Events", "Active Calls", "Call Stack")),
        termination_heading=Text(("Information on Where Terminated",)),
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
        ),
    ),
)
