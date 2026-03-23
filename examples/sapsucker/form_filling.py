"""Fill a selection screen and execute a report.

Opens SE38, enters report name RSPARAM, and executes it (F8).
Demonstrates text field filling and virtual key presses.

Prerequisites:
    - SAP GUI running with a logged-in session.
    - Authorization for SE38 and report RSPARAM.
"""

from typing import Any

from sapsucker import SapGui


def main(session: Any = None) -> None:
    """Run the example. Pass a session for testing, or None to auto-connect."""
    if session is None:
        app = SapGui.connect()
        session = app.connections[0].sessions[0]

    # Navigate to SE38
    session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/nSE38"
    session.find_by_id("wnd[0]").send_v_key(0)

    # Fill the program name field
    program_field = session.find_by_id("wnd[0]/usr/ctxtRS38M-PROGRAMM")
    program_field.text = "RSPARAM"
    print(f"Program field: '{program_field.text}'")
    print(f"Max length: {program_field.max_length}")
    print(f"Required: {program_field.is_required}")

    # Press F8 (Execute)
    session.find_by_id("wnd[0]").send_v_key(8)

    print(f"\nNow on screen: {session.info.screen_number}")
    print(f"Program: {session.info.program}")

    # Go back
    session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/n"
    session.find_by_id("wnd[0]").send_v_key(0)


if __name__ == "__main__":
    main()
