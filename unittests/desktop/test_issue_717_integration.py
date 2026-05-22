"""End-to-end integration test for issue #717.

Navigates to ``/n/NA2/DCS`` on the configured default SAP system, takes a
``sap_com_snapshot`` at depth sufficient to include the DockShell + Shell,
and verifies that every ``id=...`` emitted on the snapshot resolves via
``sap_com_evaluate``.

If ``/NA2/DCS`` is not installed on the target system, the test is
skipped cleanly — the fixture-based unit test
(``test_issue_717_snapshot_fixture.py``) still guards the regression.
"""

from __future__ import annotations

import sys

import pytest

from sapguimcp.tools.com_tools import ComOperationInput, _execute_single_op
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


_NOT_FOUND_MARKERS = (
    "unbekannt",
    "does not exist",
    "nicht definiert",
    "is unknown",
    "not defined",
    "not found",
    "ungültig",
    "invalid",
)

_SHELL_TYPE_TOKENS = ("GuiShell[", "GuiDockShell[", "GuiContainerShell[")


def _looks_missing(sbar_type: str, sbar_message: str | None) -> bool:
    """Classify a post-enter_transaction status bar as 'transaction not available'.

    Triggers on any error/abort/warning status whose message matches one of the
    common missing-transaction phrases, in either SAP language.
    """
    if sbar_type not in ("E", "A", "W"):
        return False
    msg = (sbar_message or "").lower()
    return any(m in msg for m in _NOT_FOUND_MARKERS)


@skip_no_sap
@pytest.mark.anyio
async def test_na2_dcs_shell_ids_are_reachable(backend):
    """On /NA2/DCS the snapshot must expose IDs the LLM can resolve (issue #717)."""
    r = await backend.enter_transaction("/n/NA2/DCS")
    sbar = await backend.get_status_bar()
    try:
        if _looks_missing(sbar.type, sbar.message):
            pytest.skip(f"/NA2/DCS not available on this system: {sbar.message}")
        # enter_transaction failed for some *other* reason — not the skip
        # we want, so surface it as a test failure.
        assert r.success, f"enter_transaction failed unexpectedly: {r.error}"

        # The DCS tree sits at wnd[0]/shellcont — directly on the window,
        # not under /usr. Depth 3 is enough to reach it.
        snapshot, _, _ = await backend.get_snapshot_with_depth(depth=3)
        text = str(snapshot)

        id_lines = [ln for ln in text.splitlines() if " id=" in ln]
        assert id_lines, "snapshot must emit id= suffixes after #717 fix"

        # Match only real shell-type tokens, not any line that happens to
        # contain the substring "Shell" (menu labels, tooltips, ...).
        shell_id_lines = [ln for ln in id_lines if any(tok in ln for tok in _SHELL_TYPE_TOKENS)]
        assert shell_id_lines, (
            "expected at least one GuiShell / GuiDockShell / GuiContainerShell "
            "line with an id — this is the reporter's exact unreachable control class"
        )

        session = backend.require_session()

        # Probe every shell-ish ID; ALL must resolve (that is the whole
        # promise of the fix).
        failures: list[str] = []
        for ln in shell_id_lines:
            element_id = ln.rsplit(" id=", 1)[1].strip().split()[0]

            def _probe(eid: str = element_id) -> tuple[bool, str | None]:
                op = ComOperationInput(element_id=eid, action="get", property_or_method="Type")
                res = _execute_single_op(session, op)
                return res.success, res.error

            ok, err = await backend.com.run(_probe)
            if not ok:
                failures.append(f"{element_id}: {err}")

        assert not failures, (
            "every Shell/DockShell id in the snapshot must resolve via sap_com_evaluate — " f"failures: {failures}"
        )
    finally:
        await go_home(backend)
