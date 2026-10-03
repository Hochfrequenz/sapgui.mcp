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
