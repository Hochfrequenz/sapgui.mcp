"""Render the SAP GUI element tree as text for ``sap_com_snapshot``.

Extracted from ``DesktopBackend.get_snapshot_with_depth`` so it can be
unit-tested without a live SAP connection.

Output format (per line):

    <indent><type>[<name>]: <text-repr> [id=<relative-id>]

The ``id=<relative-id>`` suffix is only added for types the LLM typically
needs to address directly via ``sap_com_evaluate`` — interactive fields,
shells, and dock shells. Pure containers (``GuiUserArea``,
``GuiVContainer``, ...) deliberately omit it to keep the snapshot compact
for large screens; the LLM reconstructs their path from indentation when
it actually needs it, which is rare.

Regression context: https://github.com/Hochfrequenz/sapgui.mcp/issues/717
— reporter could not figure out the full COM ID of a tree inside a
``GuiDockShell`` because the old format ``{type}[{name}]`` hid the path.
"""

from __future__ import annotations

from sapsucker.models import ElementInfo

from sapguimcp.backend.desktop._element_finder import _flatten

# Types for which we emit ``id=<relative-id>`` on the snapshot line.
# Rule of thumb: anything the LLM might call get / set / call on directly,
# plus the handful of always-addressed top-level anchors (main window,
# OkCode field, status bar) the tool description used to list as
# "paths not in the snapshot." Listing them here means the LLM sees one
# consistent rule: "copy the ``id=...`` verbatim from the snapshot."
#
# Intermediate containers (GuiUserArea, GuiVContainer, GuiScrollContainer,
# ...) deliberately omit the ID to keep snapshots compact on busy screens
# (SE80, SPRO IMG tree). The LLM rarely acts on them directly; indentation
# is enough to convey structure.
_TYPES_NEEDING_ID: frozenset[int] = frozenset(
    {
        21,  # GuiMainWindow — for SendVKey, Iconify, etc.
        31,  # GuiTextField
        32,  # GuiCTextField
        33,  # GuiPasswordField
        34,  # GuiComboBox
        35,  # GuiOkCodeField — for tcode entry
        40,  # GuiButton
        41,  # GuiRadioButton
        42,  # GuiCheckBox
        50,  # GuiCustomControl — container-shell host, sometimes addressed
        51,  # GuiContainerShell
        80,  # GuiTableControl
        91,  # GuiTab
        103,  # GuiStatusbar — for reading messages
        122,  # GuiShell (covers trees, ALV grids, ABAP editors, etc.)
        126,  # GuiDockShell
    }
)


def _strip_absolute_prefix(full_id: str) -> str:
    """Drop the ``/app/con[N]/ses[N]/`` prefix so ``wnd[0]/...`` is returned.

    ``sapsucker`` surfaces absolute IDs; the LLM only works with
    window-relative paths. Mirrors the stripping done in
    ``DesktopBackend._find_editor_shell_raw``.
    """
    wnd_idx = full_id.find("wnd[")
    return full_id[wnd_idx:] if wnd_idx >= 0 else full_id


def render_snapshot_lines(tree: list[ElementInfo]) -> list[str]:
    """Render a dumped element tree as one text line per element.

    The indent level is derived from the slash count in the element's
    (absolute) ID, so the relative indentation is correct regardless of
    the absolute prefix.
    """
    lines: list[str] = []
    for elem in _flatten(tree):
        indent = "  " * elem.id.count("/")
        base = f"{indent}{elem.type}[{elem.name}]: {elem.text!r}"
        if elem.type_as_number in _TYPES_NEEDING_ID:
            base = f"{base} id={_strip_absolute_prefix(elem.id)}"
        lines.append(base)
    return lines
