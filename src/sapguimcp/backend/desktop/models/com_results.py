"""Pydantic models for COM evaluate tool results."""

from pydantic import BaseModel, Field

from sapguimcp.models.base import ToolResult


class ComOperation(ToolResult):
    """Result of a single COM operation."""

    element_id: str = Field(default="", description="SAP GUI element path")
    action: str = Field(default="", description="Action performed: get, set, or call")
    property_or_method: str = Field(default="", description="Property or method name")
    result: str | None = Field(default=None, description="JSON-serialized result value")


class ComEvaluateResult(ToolResult):
    """Result from sap_com_evaluate tool. Supports batch operations."""

    operations: list[ComOperation] = Field(default_factory=list, description="Results of each operation")
    failed_count: int = Field(
        default=0,
        description="Number of returned operations with success=False.",
    )
    aborted_at_index: int | None = Field(
        default=None,
        description=(
            "With stop_on_error=True: 0-based index into the REQUESTED operations list at which "
            "execution stopped (the first failed operation). None when the batch was not aborted — "
            "either stop_on_error=False or no operation failed. The operations list then contains "
            "only the ops that ran, so this index is what tells 'aborted after N' apart from "
            "'only N submitted'."
        ),
    )


class ComSnapshotResult(ToolResult):
    """Result from sap_com_snapshot tool — element tree with IDs."""

    snapshot: str | None = Field(
        default=None, description="Indented element tree. Each line: Type[path]: 'text'. Use path as element_id."
    )
    depth_shown: int | None = Field(default=None, description="Tree depth shown in this response")
    max_depth_found: int | None = Field(default=None, description="Maximum depth in the full tree")
    elements_hidden: int | None = Field(default=None, description="Elements beyond depth cutoff not shown")


class TreeContextMenuItem(BaseModel):
    """One entry from a tree-shell's context menu — a payload, not a tool envelope."""

    position: int = Field(description="0-based index into the menu")
    text: str = Field(description="Display label shown to the user (e.g. 'Task: Anlegen')")
    fcode: str = Field(description="Internal function code / Name (e.g. 'T_1310')")


class TreeContextMenuResult(ToolResult):
    """Result from sap_tree_context_menu — enumerated items + optional selection."""

    items: list[TreeContextMenuItem] = Field(
        default_factory=list,
        description="All context-menu items for the given node, in the order SAP returned them.",
    )
    selected: TreeContextMenuItem | None = Field(
        default=None,
        description=(
            "The item that was invoked. Only populated for select_fcode and select_position — "
            "for select_text this is set only when exactly one item matches (ambiguous on duplicates)."
        ),
    )
    current_session_title_after: str | None = Field(
        default=None,
        description=(
            "Title of the topmost active window in the CURRENT SAP session after the selection. "
            "Note: some menu actions (e.g. DCS 'Task: Anlegen') open a PARALLEL session rather "
            "than replacing the current window — in that case this title is unchanged. Use "
            "sap_com_snapshot or iterate the connection's child sessions to find the new screen."
        ),
    )


class TreeColumn(BaseModel):
    """One named column of a column tree."""

    name: str = Field(description="Internal column name (use with GetItemText / ClickLink)")
    title: str = Field(default="", description="Column header text")


class TreeNode(BaseModel):
    """One loaded node of a tree control — a payload, not a tool envelope."""

    key: str = Field(description="Node key, an opaque string with significant padding (never strip it)")
    text: str = Field(description="Node label")
    level: int = Field(description="Hierarchy level (0 = root level)")
    path: list[str] = Field(default_factory=list, description="Ancestor labels from the root down to the parent")
    is_folder: bool = Field(
        description="True when the node is expandable. A collapsed, not yet loaded folder may have no loaded children."
    )
    expanded: bool | None = Field(default=None, description="Whether the folder is expanded (None when unknown)")
    items: dict[str, str] = Field(default_factory=dict, description="Column name to text (column trees only)")


class TreeReadResult(ToolResult):
    """Result from sap_tree_read — loaded nodes of a tree, never expanded by the tool."""

    tree_id: str = Field(default="", description="Element ID of the tree that was read")
    tree_type: str = Field(default="", description="simple, list or column")
    columns: list[TreeColumn] = Field(default_factory=list, description="Named columns (column trees only)")
    nodes: list[TreeNode] = Field(default_factory=list, description="Returned nodes (at most max_nodes)")
    total_nodes: int = Field(default=0, description="Number of nodes currently loaded in the tree")
    returned_nodes: int = Field(default=0, description="Number of nodes in `nodes`")
    scanned_nodes: int = Field(default=0, description="Number of loaded nodes examined")
    skipped_nodes: int = Field(default=0, description="Nodes skipped because of a per-node COM error")
    truncated: bool = Field(default=False, description="True when more matching nodes exist than max_nodes")
    scan_limit_hit: bool = Field(default=False, description="True when the tree exceeded the internal scan ceiling")
