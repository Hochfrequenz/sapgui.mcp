"""Models for SAP selection screen state parsing and transitions."""

from pydantic import BaseModel, Field

from sapguimcp.models.base import ToolResult


class SelectionScreenState(BaseModel):
    """Parsed state of a SAP selection screen.

    Represents the current (or desired target) state of all interactive
    controls on a SAP selection screen: checkboxes, radio buttons, and
    text input fields.  Parsed from ARIA snapshots where checkbox/radio
    state is encoded via the ``[checked]`` attribute and text field
    values appear after the colon (``textbox "Label": VALUE``).

    Used both for reading current screen state and for declaring the
    target state that ``ensure_screen_state()`` should transition to.
    """

    checkboxes: dict[str, bool] = Field(
        default_factory=dict,
        description="Checkbox labels mapped to their checked state (True=checked, False=unchecked)",
    )
    radios: dict[str, bool] = Field(
        default_factory=dict,
        description="Radio button labels mapped to their selected state (True=selected, False=not)",
    )
    fields: dict[str, str] = Field(
        default_factory=dict,
        description="Text field labels mapped to their current/desired value",
    )
    ambiguous_labels: list[str] = Field(
        default_factory=list,
        description="Labels that appear more than once for the same control type — unsafe to target by name",
    )


class StateChange(BaseModel):
    """A single state transition for one control.

    Records the previous and new value of a checkbox, radio button,
    or text field after ``ensure_screen_state()`` applied a change.
    """

    was: str = Field(description="Previous value before the transition")
    now: str = Field(description="New value after the transition")


class ScreenStateDiff(ToolResult):
    """Result of transitioning a SAP selection screen to a target state.

    Extends ``ToolResult`` so callers get ``success``/``error`` semantics.
    After applying all changes, ``ensure_screen_state()`` re-reads the
    ARIA snapshot and verifies every target control matches.  If any
    control did not reach its target value, ``success=False`` and
    ``mismatches`` lists the specific controls that failed.

    When ``success=True``, the screen is guaranteed to be in the
    requested target state and the tool can safely proceed.
    """

    checkboxes_changed: dict[str, StateChange] = Field(
        default_factory=dict,
        description="Checkboxes that were toggled, keyed by label",
    )
    radios_changed: dict[str, StateChange] = Field(
        default_factory=dict,
        description="Radio buttons that were changed, keyed by label",
    )
    fields_changed: dict[str, StateChange] = Field(
        default_factory=dict,
        description="Text fields that were updated, keyed by label",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Labels not found on screen (e.g. wrong-language labels)",
    )
    mismatches: list[str] = Field(
        default_factory=list,
        description="Controls that did not reach their target value after applying changes",
    )
