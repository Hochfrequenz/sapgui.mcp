"""Navigate a tree control in SE80 (Object Navigator).

Finds the repository browser tree, reads node information,
and expands/collapses nodes.

Prerequisites:
    - SAP GUI running with a logged-in session.
    - Authorization for SE80.
"""

import time
from typing import Any

from sapsucker import SapGui
from sapsucker.components.tree import GuiTree


def main(session: Any = None) -> None:
    """Run the example. Pass a session for testing, or None to auto-connect."""
    if session is None:
        app = SapGui.connect()
        session = app.connections[0].sessions[0]

    # Navigate to SE80
    session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/nSE80"
    session.find_by_id("wnd[0]").send_v_key(0)
    time.sleep(1)

    # Find the tree (inside the splitter shell)
    tree = session.find_by_id("wnd[0]/shellcont/shell/shellcont[1]/shell/shellcont[2]/shell")
    assert isinstance(tree, GuiTree), f"Expected GuiTree, got {type(tree)}"

    print(f"Tree type: {tree.tree_type}  (0=Simple, 1=List, 2=Column)")
    print(f"Top node key: {tree.top_node}")
    print()

    # Read the top node
    key = tree.top_node
    text = tree.get_node_text_by_key(key)
    children = tree.get_node_children_count(key)
    is_folder = tree.is_folder(key)
    style = tree.get_node_style(key)

    print(f"Node '{key}': text='{text}', children={children}, folder={is_folder}, style={style}")

    # Expand the top node and list its children
    if is_folder:
        tree.expand_node(key)
        print(f"\nExpanded node '{key}'. Children count: {tree.get_node_children_count(key)}")
        tree.collapse_node(key)
        print("Collapsed.")

    # Go back
    session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/n"
    session.find_by_id("wnd[0]").send_v_key(0)


if __name__ == "__main__":
    main()
