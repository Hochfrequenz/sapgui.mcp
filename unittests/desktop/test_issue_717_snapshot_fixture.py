"""Regression test for issue #717 using a live-captured snapshot fixture.

The fixture file was captured from HF R/3 Mandant 100 on transaction
``/n/NA2/DCS`` (the reporter's exact scenario) after fix #717 was applied.
It contains the full post-fix snapshot text, with ``id=`` suffixes the LLM
can copy verbatim into ``sap_com_evaluate``.

The key failure mode the reporter hit: they assumed the tree was at
``wnd[0]/usr/...``, but the DockShell for ``/NA2/DCS`` is actually at
``wnd[0]/shellcont`` (directly on the main window), with the tree shell
at ``wnd[0]/shellcont/shell``. The fix makes this path visible in the
snapshot — the LLM no longer has to guess.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "testdata" / "issue_717" / "HF_R3_Mandant_100" / "n_NA2_DCS_snapshot.txt"


@pytest.fixture(scope="module")
def snapshot_text() -> str:
    if not FIXTURE.is_file():
        pytest.skip(f"snapshot fixture not available: {FIXTURE}")
    return FIXTURE.read_text(encoding="utf-8")


def test_reporter_dock_shell_has_resolvable_id(snapshot_text: str):
    """The GuiDockShell the reporter could not reach now carries its ID."""
    dock_lines = [ln for ln in snapshot_text.splitlines() if "GuiDockShell[" in ln]
    assert dock_lines, "fixture should contain at least one GuiDockShell line"
    # Exact-end match so the assertion fails if the ID is e.g.
    # ``wnd[0]/shellcont/shell`` by mistake.
    assert any(ln.rstrip().endswith("id=wnd[0]/shellcont") for ln in dock_lines), (
        "the reporter's DockShell should now surface its full ID in the snapshot — " f"got: {dock_lines}"
    )


def test_reporter_tree_shell_has_resolvable_id(snapshot_text: str):
    """The GuiShell inside the DockShell (the TableTreeControl.1 OCX) is reachable."""
    shell_lines = [ln for ln in snapshot_text.splitlines() if "GuiShell[shell]" in ln]
    assert shell_lines, "fixture should contain the tree shell line"
    assert any(ln.rstrip().endswith("id=wnd[0]/shellcont/shell") for ln in shell_lines), (
        "the tree shell's ID must be present so the LLM can call nodeContextMenu etc. — " f"got: {shell_lines}"
    )


def test_absolute_com_prefix_is_not_leaked(snapshot_text: str):
    """``/app/con[N]/ses[N]/`` is an internal COM detail and must not appear."""
    assert "/app/con" not in snapshot_text
    assert "/ses[" not in snapshot_text


def test_actual_dcs_tree_lives_outside_usr(snapshot_text: str):
    """Document the bug's root cause: the tree is NOT under ``wnd[0]/usr``.

    This is why the reporter's ``wnd[0]/usr/shellcont/shell`` guess failed —
    on this transaction the DockShell sits directly on the main window.
    The fix makes this discoverable without guessing.
    """
    tree_id_lines = [ln for ln in snapshot_text.splitlines() if "id=wnd[0]/shellcont/shell" in ln]
    assert tree_id_lines, "expected the tree shell at window-level shellcont"
    assert not any("id=wnd[0]/usr/shellcont/shell" in ln for ln in snapshot_text.splitlines()), (
        "on /NA2/DCS the tree is at wnd[0]/shellcont/shell, not under /usr — " "this is the bug's root cause"
    )
