"""Unit tests for snapshot line rendering.

Regression test for https://github.com/Hochfrequenz/sapgui.mcp/issues/717
— the reporter could not figure out the full COM ID of a tree inside a
``GuiDockShell`` because the snapshot only showed ``{type}[{name}]`` and
they had to reconstruct the path from indentation. The fix is to also
emit ``id=<relative-id>`` for interactive / shell / dock-shell types so
the LLM can copy the path verbatim.
"""

from __future__ import annotations

from sapsucker.models import ElementInfo

from sapguimcp.backend.desktop._snapshot_render import render_snapshot_lines


def _elem(
    id_: str,
    type_: str,
    type_as_number: int,
    name: str = "",
    text: str = "",
    children: list[ElementInfo] | None = None,
) -> ElementInfo:
    return ElementInfo(
        id=id_,
        type=type_,
        type_as_number=type_as_number,
        name=name or id_.rsplit("/", 1)[-1],
        text=text,
        changeable=False,
        children=children or [],
    )


# Reporter's DCS tree shape: DockShell inside usr, Shell inside DockShell.
def _build_dcs_like_tree() -> list[ElementInfo]:
    return [
        _elem(
            "/app/con[0]/ses[0]/wnd[0]",
            "GuiMainWindow",
            21,
            name="wnd[0]",
            text="DCS",
            children=[
                _elem(
                    "/app/con[0]/ses[0]/wnd[0]/usr",
                    "GuiUserArea",
                    74,
                    name="usr",
                    children=[
                        _elem(
                            "/app/con[0]/ses[0]/wnd[0]/usr/shellcont",
                            "GuiDockShell",
                            126,
                            name="shellcont",
                            children=[
                                _elem(
                                    "/app/con[0]/ses[0]/wnd[0]/usr/shellcont/shell",
                                    "GuiShell",
                                    122,
                                    name="shell",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ]


def test_dock_shell_line_includes_relative_id():
    """Issue #717: the reporter needed the full ID of the DockShell."""
    lines = render_snapshot_lines(_build_dcs_like_tree())
    dock_lines = [ln for ln in lines if "GuiDockShell[" in ln]
    assert len(dock_lines) == 1
    assert dock_lines[0].rstrip().endswith("id=wnd[0]/usr/shellcont")


def test_shell_line_includes_relative_id():
    """Issue #717: the reporter needed the full ID of the Shell inside the DockShell."""
    lines = render_snapshot_lines(_build_dcs_like_tree())
    shell_lines = [ln for ln in lines if "GuiShell[shell]" in ln]
    assert len(shell_lines) == 1
    assert shell_lines[0].rstrip().endswith("id=wnd[0]/usr/shellcont/shell")


def test_absolute_prefix_is_stripped():
    """The ``/app/con[N]/ses[N]/`` absolute prefix must not appear in any line."""
    lines = render_snapshot_lines(_build_dcs_like_tree())
    for line in lines:
        assert "/app/con" not in line, f"absolute prefix leaked into: {line}"
        assert "/ses[" not in line, f"absolute prefix leaked into: {line}"


def test_container_lines_do_not_include_id():
    """IDs for pure containers (GuiUserArea) would bloat the snapshot for no gain."""
    lines = render_snapshot_lines(_build_dcs_like_tree())
    usr_lines = [ln for ln in lines if "GuiUserArea" in ln]
    assert len(usr_lines) == 1
    assert "id=" not in usr_lines[0]


def test_interactive_text_field_includes_id():
    """GuiTextField is interactive — LLM needs the ID to get/set Text."""
    tree = [
        _elem(
            "/app/con[0]/ses[0]/wnd[0]",
            "GuiMainWindow",
            21,
            name="wnd[0]",
            children=[
                _elem(
                    "/app/con[0]/ses[0]/wnd[0]/usr",
                    "GuiUserArea",
                    74,
                    name="usr",
                    children=[
                        _elem(
                            "/app/con[0]/ses[0]/wnd[0]/usr/txtFOO",
                            "GuiTextField",
                            31,
                            name="FOO",
                            text="bar",
                        ),
                    ],
                ),
            ],
        ),
    ]
    lines = render_snapshot_lines(tree)
    txt_lines = [ln for ln in lines if "GuiTextField[" in ln]
    assert len(txt_lines) == 1
    assert txt_lines[0].rstrip().endswith("id=wnd[0]/usr/txtFOO")


def test_preserves_existing_format_fields():
    """The ``{type}[{name}]: {text!r}`` portion stays intact — legacy expectations hold."""
    tree = [
        _elem(
            "/app/con[0]/ses[0]/wnd[0]",
            "GuiMainWindow",
            21,
            name="wnd[0]",
            text="SAP Easy Access",
        )
    ]
    lines = render_snapshot_lines(tree)
    assert "GuiMainWindow[wnd[0]]: 'SAP Easy Access'" in lines[0]


def test_indentation_is_relative_not_absolute():
    """Indent depth should reflect nesting, not the absolute-path prefix."""
    lines = render_snapshot_lines(_build_dcs_like_tree())
    # wnd[0] has no leading spaces, usr has some, shellcont more, shell most.
    wnd_line = next(ln for ln in lines if "GuiMainWindow" in ln)
    usr_line = next(ln for ln in lines if "GuiUserArea" in ln)
    dock_line = next(ln for ln in lines if "GuiDockShell" in ln)
    shell_line = next(ln for ln in lines if "GuiShell[shell]" in ln)

    def leading_spaces(s: str) -> int:
        return len(s) - len(s.lstrip(" "))

    assert leading_spaces(wnd_line) < leading_spaces(usr_line) < leading_spaces(dock_line) < leading_spaces(shell_line)
