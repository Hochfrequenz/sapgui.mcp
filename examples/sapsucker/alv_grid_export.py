"""Read data from an ALV grid in SE16N and print it.

Opens SE16N, queries table T000 (SAP clients), and reads all
cell values from the ALV grid result.

Prerequisites:
    - SAP GUI running with a logged-in session.
    - Authorization for SE16N and table T000.
"""

import time
from typing import Any

from sapsucker import SapGui
from sapsucker.components.grid import GuiGridView


def main(session: Any = None) -> None:
    """Run the example. Pass a session for testing, or None to auto-connect."""
    if session is None:
        app = SapGui.connect()
        session = app.connections[0].sessions[0]

    # Navigate to SE16N
    session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/nSE16N"
    session.find_by_id("wnd[0]").send_v_key(0)
    time.sleep(1)

    # Enter table name and execute
    session.find_by_id("wnd[0]/usr/ctxtGD-TAB").text = "T000"
    session.find_by_id("wnd[0]").send_v_key(8)  # F8 = Execute
    time.sleep(2)

    # Find the ALV grid (ID may vary by SAP release)
    for grid_id in [
        "wnd[0]/shellcont/shell",
        "wnd[0]/usr/cntlGRID1/shellcont/shell/shellcont[1]/shell",
        "wnd[0]/usr/cntlGRID1/shellcont/shell",
    ]:
        try:
            grid = session.find_by_id(grid_id)
            if isinstance(grid, GuiGridView):
                break
        except Exception:
            continue
    else:
        print("Could not find ALV grid in SE16N")
        return

    print(f"Rows: {grid.row_count}, Columns: {grid.column_count}")

    # Get column names (column_order may be a list or COM collection)
    col_order = grid.column_order
    if isinstance(col_order, list):
        columns = col_order
    else:
        columns = [str(col_order(i)) for i in range(col_order.Count)]
    print(f"Columns: {columns}")
    print()

    # Read all rows
    for row in range(grid.row_count):
        values = {}
        for col in columns:
            values[col] = grid.get_cell_value(row, col)
        print(values)

    # Go back
    session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/n"
    session.find_by_id("wnd[0]").send_v_key(0)


if __name__ == "__main__":
    main()
