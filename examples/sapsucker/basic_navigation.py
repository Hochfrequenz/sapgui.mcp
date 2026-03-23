"""Connect to SAP GUI, navigate to a transaction, and read the status bar.

Prerequisites:
    - SAP GUI for Windows must be running with at least one logged-in session.
    - SAP GUI Scripting must be enabled (transaction RZ11, parameter
      sapgui/user_scripting = TRUE).

Usage:
    python basic_navigation.py
"""

from typing import Any

from sapsucker import SapGui


def main(session: Any = None) -> None:
    """Run the example. Pass a session for testing, or None to auto-connect."""
    if session is None:
        app = SapGui.connect()
        session = app.connections[0].sessions[0]

    # Print current session info
    info = session.info
    print(f"System: {info.system_name}")
    print(f"Client: {info.client}")
    print(f"User:   {info.user}")
    print(f"Transaction: {info.transaction}")

    # Navigate to SE16 (Data Browser)
    session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/nSE16"
    session.find_by_id("wnd[0]").send_v_key(0)  # Enter

    # Read the status bar
    sbar = session.find_by_id("wnd[0]/sbar")
    print(f"\nStatus bar: {sbar.text}")
    print(f"Now in transaction: {session.info.transaction}")

    # Go back to the main menu
    session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/n"
    session.find_by_id("wnd[0]").send_v_key(0)


if __name__ == "__main__":
    main()
