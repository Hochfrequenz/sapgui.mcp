"""Probe: after 'Task: Anlegen' on /NA2/DCS, enumerate EVERYTHING.

Every SAP COM connection, every session inside each connection, every
window inside each session, every active-window title / transaction /
screen / dynpro. If the 'Create Task' screen opens anywhere, we will
see it here.

Closes all existing SAP GUI sessions at startup so state is clean.
"""

from __future__ import annotations

import asyncio
import json
import sys

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.desktop._com_thread import ComThread
from sapguimcp.models.config import get_sap_config

SHELL_ID = "wnd[0]/shellcont/shell"
TREE_PATH = ["DCS Projekte", "AUSBILDUN", "AUSB_EXT_PRD", "Taskgruppe 100000", "Taskgruppe 101000"]


def _raw(session, element_id: str):
    rs = getattr(session, "com", getattr(session, "_com", session))
    return rs.FindById(element_id)


def _close_all_existing(com: ComThread) -> int:
    """Close every live SAP Logon connection via CloseConnection."""
    from sapsucker import SapGui  # pylint: disable=import-outside-toplevel

    def _inner() -> int:
        app = SapGui.connect()
        raw_app = getattr(app, "com", getattr(app, "_com", app))
        conns = raw_app.Children
        closed = 0
        for i in range(conns.Count - 1, -1, -1):
            try:
                conns(i).CloseConnection()
                closed += 1
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        return closed

    return com._run_sync(_inner)  # pylint: disable=protected-access


def _enumerate_all(session) -> dict:
    """Walk the full SAP COM hierarchy and dump every window we can see."""
    raw_session = getattr(session, "com", getattr(session, "_com", session))
    app = raw_session.Parent.Parent  # session -> connection -> application
    out: dict = {"connections": []}
    for ci in range(app.Children.Count):
        conn = app.Children(ci)
        conn_info: dict = {
            "conn_index": ci,
            "conn_id": str(conn.Id),
            "conn_description": str(conn.Description),
            "conn_disabled_by_server": str(getattr(conn, "DisabledByServer", "?")),
            "sessions": [],
        }
        for si in range(conn.Children.Count):
            ses = conn.Children(si)
            ses_info: dict = {
                "ses_index": si,
                "ses_id": str(ses.Id),
                "tx": str(ses.Info.Transaction),
                "program": str(ses.Info.Program),
                "screen_number": str(ses.Info.ScreenNumber),
                "user": str(ses.Info.User),
                "busy": bool(ses.Busy),
                "windows": [],
            }
            for wi in range(ses.Children.Count):
                wnd = ses.Children(wi)
                try:
                    ses_info["windows"].append(
                        {
                            "wnd_index": wi,
                            "wnd_id": str(wnd.Id),
                            "type": str(getattr(wnd, "Type", "?")),
                            "text": str(getattr(wnd, "Text", "?")),
                        }
                    )
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    ses_info["windows"].append({"wnd_index": wi, "err": str(exc)[:120]})
            conn_info["sessions"].append(ses_info)
        out["connections"].append(conn_info)
    return out


async def _expand_to_target(backend, com) -> str | None:
    session = backend.require_session()

    def _iter_keys() -> list[str]:
        coll = _raw(session, SHELL_ID).GetAllNodeKeys()
        return [str(coll.Item(i)) for i in range(coll.Count)]

    def _text_for(k: str) -> str:
        return str(_raw(session, SHELL_ID).GetNodeTextByKey(k))

    keys = await com.run(_iter_keys)
    key_texts = []
    for k in keys:
        try:
            key_texts.append((k, await com.run(lambda _k=k: _text_for(_k))))
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _find(label: str) -> str | None:
        for k, t in key_texts:
            if t.strip() == label:
                return k
        for k, t in key_texts:
            if label in t:
                return k
        return None

    for label in TREE_PATH[:-1]:
        k = _find(label)
        if k is None:
            return None
        await com.run(lambda _k=k: _raw(session, SHELL_ID).ExpandNode(_k))
        keys = await com.run(_iter_keys)
        key_texts = []
        for nk in keys:
            try:
                key_texts.append((nk, await com.run(lambda _k=nk: _text_for(_k))))
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    return _find(TREE_PATH[-1])


async def main() -> int:
    cfg = get_sap_config()
    key = "HF R3 Mandant 100"
    if key not in cfg.systems:
        print(f"[skip] {key!r} not configured")
        return 0
    sys_ = cfg.systems[key]

    # Use a temporary ComThread to close leftover sessions BEFORE the real login.
    cleanup_com = ComThread()
    try:
        closed = _close_all_existing(cleanup_com)
        print(f"[cleanup] closed {closed} existing connection(s)")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[cleanup] failed: {exc}")
    finally:
        cleanup_com.shutdown()

    com = ComThread()
    backend = DesktopBackend(com_thread=com)
    print(f"[login] {key}")
    r = await backend.login(
        "x",
        sys_.user,
        sys_.password.get_secret_value(),
        sys_.client,
        sys_.language,
        connection_name=sys_.connection_name,
    )
    if not r.success:
        print(f"[fail] {r.error}")
        com.shutdown()
        return 1

    try:
        await backend.enter_transaction("/n/NA2/DCS")
        sbar = await backend.get_status_bar()
        print(f"[nav] title={await backend.get_page_title()!r} sbar={sbar.type!r}:{sbar.message!r}")

        target = await _expand_to_target(backend, com)
        if target is None:
            print("[skip] path not found")
            return 0
        print(f"[target] {target!r}")

        session = backend.require_session()

        print("\n=== BEFORE selection: full enum ===")
        before = await com.run(lambda: _enumerate_all(session))
        print(json.dumps(before, indent=2, default=str))

        print("\n=== firing 'Task: Anlegen' ===")

        def _fire() -> None:
            sh = _raw(session, SHELL_ID)
            sh.SelectNode(target)
            sh.NodeContextMenu(target)
            sh.SelectContextMenuItemByText("Task: Anlegen")

        await com.run(_fire)
        print("[fire] returned; waiting 10s for new session to appear")
        await asyncio.sleep(10)
        print("\n=== AFTER selection + 10s wait: full enum ===")
        after = await com.run(lambda: _enumerate_all(session))
        print(json.dumps(after, indent=2, default=str))

        return 0
    finally:
        com.shutdown()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
