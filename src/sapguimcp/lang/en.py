"""English language pack (SAP logon language EN); the fallback merged into every session view."""

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

EN = LanguagePack(
    code="EN",
    html_lang="en",
    logon_dropdown="English",
    date_format="%m/%d/%Y",
    same_as_en=frozenset(),
    common=CommonSection(
        display=Text(("Display",)),
        not_found=Text(("not found",)),
        does_not_exist=Text(("does not exist",)),
        no_entries=Text(("No entries found",)),
        row_select_hint=Text(("To select a row", "To select")),
        user=Text(("User",)),
        program=Text(("Program",)),
    ),
    popup=PopupSection(),
    status_type=StatusTypeSection(),
    session_pages=SessionPagesSection(),
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
        error_keywords=Text(("not found",)),
        status_error=Text(("not found",)),
        screen_errors=Text(("repository not found", "transport required")),
        transport_required=Text(("transport required",)),
        no_task=Text(("no modifiable task", "has no task")),
        button_labels=Text(("OK", "Cancel", "Yes", "No")),
        inactive_objects=Text(("Inactive Objects",)),
        # LIVE CHECK NEEDED (#1044): the real EN title of the SE38 initial screen. "Entry" never matched it
        # (a DE-only check in practice); kept until the title is read live.
        se38_initial_title=Text(("Entry",)),
    ),
    quick_report=QuickReportSection(
        empty_patterns=Text(("no data", "no entries", "no job", "no documents")),
        execute_button=Text(("Execute", "Execute Highlighted")),
    ),
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
        list_region=Text(("List",)),
        organizer_title=Text(("Transport Organizer",)),
        request_word=Text(("Request",)),
    ),
    se11=Se11Section(
        database_table=Text(("Database table",)),
        data_type=Text(("Data type",)),
        table_name=Text(("Table name",)),
        transparent_table=Text(("Transparent Table",)),
        structure=Text(("Structure",)),
        short_description=Text(("Short Description",)),
        row_select_full=RegexText((r"To select a row, press the space bar\.",)),
        dictionary_type=RegexText(("Dictionary.*type",)),
    ),
    se16=Se16Section(
        hit_count_label=Text(("Number of Hits",)),
        column_selection=Text(("Column for row selection",)),
        no_values_found=Text(("no values found",)),
    ),
    se24=Se24Section(
        class_builder=Text(("Class Builder",)),
        initial_screen=Text(("Class Builder: Initial",)),
        display_title=Template(("Class Builder: Display {name}",)),
        object_type=Text(("Object Type",)),
        class_label=Text(("Class",)),
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
    ),
    se37=Se37Section(
        initial_screen=Text(("Function Builder: Initial Screen",)),
        display_title=Template(("Function Builder: Display {name}",)),
    ),
    se93=Se93Section(
        initial_screen=Text(("Transaction Maintenance", "Maintain Transaction")),  # EN title per the captured snapshots
        dialog_transaction=Text(("Dialog Transaction",)),
        report_transaction=Text(("Report Transaction",)),
        gui_html=Text(("SAP GUI for HTML",)),
        gui_java=Text(("SAP GUI for Java",)),
        gui_windows=Text(("SAP GUI for Windows",)),
        screen_number=Text(("Screen number",)),
        selection_screen=Text(("Selection screen",)),
        start_with_variant=Text(("Start with variant",)),
        transaction_code=Text(
            ("Transaction code", "Transaction Code")
        ),  # exact-case title lookups: both spellings exist
        transaction_text=Text(("Transaction text",)),
        package=Text(("Package",)),
        auth_object=Text(("Authorization object",)),
    ),
    slg1=Slg1Section(
        initial_screen=Text(("Analyze Application Log",)),
        log_list_screen=Text(("Display Logs",)),
        # BL 208 in EN. The second variant is the text lang.py expected before #1044; kept until
        # the SLG1 migration confirms no release shows it.
        no_logs_found=Text(("No log found in the database", "No log could be found in the database")),
    ),
    sm30=Sm30Section(
        initial_screen=Text(("Table View Maintenance",)),
        maintain=Text(("Maintain",)),
        table_view=Text(("Table/View",)),
        display_view=Text(("View",)),
        view_not_found=Text(("is not in the Dictionary", "does not exist", "not found")),
        no_maintenance_dialog=Text(("no maintenance dialog",)),
        view_title=Template(("Display View {desc}", "Change View {desc}")),
        row_count=Template(("Entry {current} of {total}",)),
    ),
    sm37=Sm37Section(
        status=canonical(
            {
                JobStatus.SCHEDULED: Text(("Scheduled",)),
                JobStatus.RELEASED: Text(("Released",)),
                JobStatus.READY: Text(("Ready",)),
                JobStatus.ACTIVE: Text(("Active",)),
                JobStatus.FINISHED: Text(("Finished",)),
                JobStatus.CANCELED: Text(("Canceled",)),
            }
        ),
    ),
    spro=SproSection(
        initial_screen=Text(("Customizing: Execute Project",)),
        sap_reference_img=Text(("SAP Reference IMG",)),
        search_button=Text(("Find (Ctrl+F)",)),
        search_dialog=Text(("Search in the structure",)),
        search_field=Text(("Search Term",)),
        results_dialog=Text(("Hit List",)),
        column_hits=Text(("Hits",)),
        column_parent=Text(("Parent Node",)),
        column_area=Text(("In area",)),
        img_heading=Text(("Display IMG",)),
    ),
    st22=St22Section(
        section=canonical(
            {
                DumpSection.WHAT_HAPPENED: Text(("What happened?",)),
                DumpSection.HOW_TO_CORRECT: Text(("How to Correct the Error",)),
                DumpSection.ERROR_ANALYSIS: Text(("Error Analysis",)),
            }
        ),
    ),
)
