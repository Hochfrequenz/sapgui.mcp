"""Narrow probe for TableTreeControl.1 context-menu scripting contract.

After issue #717's fix, ``wnd[0]/shellcont/shell`` on ``/n/NA2/DCS`` is
reachable. ``SelectNode``, ``ExpandNode``, ``NodeContextMenu`` all
succeed. ``SelectContextMenuItemByText("Task anlegen")`` fails with
SAP Error 613.

This probe figures out WHICH of the standard context-menu invocations
this OCX actually honors, so we can ship a working
``sap_tree_context_menu`` tool.

Probes (in order, each in its own COM lambda):
  1. list all attributes/methods on the raw shell via dir()
  2. after NodeContextMenu, dump the active window + any wnd[1] popup
  3. try SelectContextMenuItemByPosition(0..7)
  4. try SelectContextMenuItem("") and common fcodes
  5. try shell.ContextMenu / shell.CurrentContextMenu / any property
     that might expose the menu items

Output goes to stdout — save and study.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.desktop._com_thread import ComThread
from sapguimcp.models.config import get_sap_config

SHELL_ID = "wnd[0]/shellcont/shell"
TREE_PATH = ["DCS Projekte", "AUSBILDUN", "AUSB_EXT_PRD", "Taskgruppe 100000", "Taskgruppe 101000"]


def _raw(session, element_id: str):
    raw_session = getattr(session, "com", getattr(session, "_com", session))
    return raw_session.FindById(element_id)


async def _expand_and_target(backend: DesktopBackend, com: ComThread) -> str | None:
    """Expand the tree to Taskgruppe 101000 and return its key."""
    session = backend.require_session()

    def _iter_keys() -> list[str]:
        sh = _raw(session, SHELL_ID)
        coll = sh.GetAllNodeKeys()
        return [str(coll.Item(i)) for i in range(coll.Count)]

    def _text_for(k: str) -> str:
        return str(_raw(session, SHELL_ID).GetNodeTextByKey(k))

    def _expand(k: str) -> None:
        _raw(session, SHELL_ID).ExpandNode(k)

    keys = await com.run(_iter_keys)
    key_texts = []
    for k in keys:
        try:
            key_texts.append((k, await com.run(lambda _k=k: _text_for(_k))))
        except Exception:
            pass

    def _find(target: str) -> str | None:
        for k, t in key_texts:
            if t.strip() == target:
                return k
        for k, t in key_texts:
            if target in t:
                return k
        return None

    for label in TREE_PATH[:-1]:
        k = _find(label)
        if k is None:
            print(f"[target] could not find {label!r}")
            return None
        await com.run(lambda _k=k: _expand(_k))
        keys = await com.run(_iter_keys)
        key_texts = []
        for nk in keys:
            try:
                key_texts.append((nk, await com.run(lambda _k=nk: _text_for(_k))))
            except Exception:
                pass

    return _find(TREE_PATH[-1])


def _p1_dir_shell(session) -> list[str]:
    """List attributes on the raw shell (plus its _oleobj_ if present)."""
    sh = _raw(session, SHELL_ID)
    names = sorted({n for n in dir(sh) if not n.startswith("_")})
    return names


def _p2_after_context_menu(session, key: str) -> dict:
    sh = _raw(session, SHELL_ID)
    sh.SelectNode(key)
    sh.NodeContextMenu(key)
    raw_session = getattr(session, "com", getattr(session, "_com", session))
    popup = None
    try:
        popup = raw_session.FindById("wnd[1]", False)
    except Exception:
        pass
    info: dict = {
        "wnd0_type": str(raw_session.FindById("wnd[0]").Type),
        "wnd0_text": str(raw_session.FindById("wnd[0]").Text),
        "wnd1_exists": popup is not None,
    }

    # Enumerate CurrentContextMenu in detail — this is the live menu.
    try:
        ccm = sh.CurrentContextMenu
        info["ccm_type"] = str(getattr(ccm, "Type", "?"))
        info["ccm_attrs"] = sorted({n for n in dir(ccm) if not n.startswith("_")})
        # Common menu-collection properties
        for prop in ("Children", "Count", "Items", "ItemCount", "MenuText", "Text", "Id"):
            try:
                v = getattr(ccm, prop)
                info[f"ccm_{prop}"] = str(v)[:200]
            except Exception as exc:
                info[f"ccm_{prop}_err"] = str(exc)[:100]
        # If Children works, dump them
        try:
            ch = ccm.Children
            info["ccm_children_count"] = ch.Count
            items = []
            for i in range(min(ch.Count, 30)):
                item = ch.Item(i)
                items.append(
                    {
                        "i": i,
                        "Type": str(getattr(item, "Type", "?")),
                        "Text": str(getattr(item, "Text", "?")),
                        "Id": str(getattr(item, "Id", "?")),
                        "Name": str(getattr(item, "Name", "?")),
                    }
                )
            info["ccm_items"] = items
        except Exception as exc:
            info["ccm_children_err"] = str(exc)[:200]
    except Exception as exc:
        info["ccm_err"] = str(exc)[:300]

    return info


def _p3_try_positions(session, key: str) -> list[dict]:
    """Try SelectContextMenuItemByPosition(0..7), measuring failure mode."""
    sh = _raw(session, SHELL_ID)
    out = []
    for pos in range(8):
        try:
            sh.SelectNode(key)
            sh.NodeContextMenu(key)
            sh.SelectContextMenuItemByPosition(pos)
            out.append({"pos": pos, "ok": True})
            # First success changes the screen — stop.
            break
        except Exception as exc:
            out.append({"pos": pos, "ok": False, "err": str(exc)[:180]})
    return out


def _p4_try_fcodes(session, key: str) -> list[dict]:
    """Use the actual fcodes discovered in P2 (CurrentContextMenu.Children[i].Name)."""
    sh = _raw(session, SHELL_ID)
    # T_1310 = "Task: Anlegen" (what the reporter wanted)
    # T_1232 = "Taskgruppe: Anlegen mit Vorlage"
    fcodes = ["T_1310", "T_1232", "T_1312"]
    out = []
    for fc in fcodes:
        try:
            sh.SelectNode(key)
            sh.NodeContextMenu(key)
            sh.SelectContextMenuItem(fc)
            out.append({"fcode": fc, "ok": True})
            break
        except Exception as exc:
            out.append({"fcode": fc, "ok": False, "err": str(exc)[:180]})
    return out


def _p5_try_exact_text(session, key: str) -> list[dict]:
    sh = _raw(session, SHELL_ID)
    # These come from the actual CurrentContextMenu.Children[i].Text values.
    texts = ["Task: Anlegen", "Task: anlegen", "Task anlegen", "Taskgruppe: Anlegen mit Vorlage"]
    out = []
    for t in texts:
        try:
            sh.SelectNode(key)
            sh.NodeContextMenu(key)
            sh.SelectContextMenuItemByText(t)
            out.append({"text": t, "ok": True})
            break
        except Exception as exc:
            out.append({"text": t, "ok": False, "err": str(exc)[:180]})
    return out


def _p7_try_double_click(session, key: str) -> dict:
    sh = _raw(session, SHELL_ID)
    try:
        sh.SelectNode(key)
        sh.DoubleClickNode(key)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "err": str(exc)[:180]}


def _p6_diagnose_after_select(session) -> dict:
    raw_session = getattr(session, "com", getattr(session, "_com", session))
    info: dict = {
        "wnd0_text": str(raw_session.FindById("wnd[0]").Text),
        "wnd0_active_dynpro": "",
    }
    try:
        info["sbar_text"] = str(raw_session.FindById("wnd[0]/sbar").Text)
        info["sbar_type"] = str(raw_session.FindById("wnd[0]/sbar").MessageType)
    except Exception as exc:
        info["sbar_err"] = str(exc)[:120]
    for w in range(1, 4):
        try:
            p = raw_session.FindById(f"wnd[{w}]", False)
            if p:
                info[f"wnd{w}_text"] = str(p.Text)
                info[f"wnd{w}_type"] = str(p.Type)
        except Exception:
            pass
    try:
        info["program"] = str(raw_session.Info.Program)
        info["transaction"] = str(raw_session.Info.Transaction)
        info["screen_number"] = str(raw_session.Info.ScreenNumber)
    except Exception as exc:
        info["info_err"] = str(exc)[:120]
    return info


async def main() -> int:
    cfg = get_sap_config()
    key = "HF R3 Mandant 100"
    if key not in cfg.systems:
        print(f"[skip] {key!r} not configured")
        return 0
    sys_ = cfg.systems[key]
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
        if sbar.type == "E" and "unbekannt" in (sbar.message or "").lower():
            print("[skip] /NA2/DCS not on this system")
            return 0

        session = backend.require_session()
        print("\n=== P1: dir(shell) ===")
        names = await com.run(lambda: _p1_dir_shell(session))
        context_names = [n for n in names if "Context" in n or "Menu" in n or "Select" in n or "fcode" in n.lower()]
        print(f"context-related methods: {context_names}")
        print(f"(total {len(names)} attrs)")

        print("\n=== P0: expand to target ===")
        target = await _expand_and_target(backend, com)
        if target is None:
            print("[fatal] could not find Taskgruppe 101000")
            return 1
        print(f"target key: {target!r}")

        print("\n=== P2: after NodeContextMenu ===")
        try:
            info = await com.run(lambda: _p2_after_context_menu(session, target))
            print(json.dumps(info, indent=2, default=str))
        except Exception as exc:
            print(f"P2 raised: {exc}")

        print("\n=== P3: SelectContextMenuItemByPosition(0..7) ===")
        try:
            results = await com.run(lambda: _p3_try_positions(session, target))
            for r in results:
                print(f"  {r}")
        except Exception as exc:
            print(f"P3 raised: {exc}")

        # Go back if the screen changed
        for _ in range(3):
            try:
                await backend.press_key("F3")
            except Exception:
                break
        await backend.enter_transaction("/n/NA2/DCS")
        target = await _expand_and_target(backend, com)

        print("\n=== P4: SelectContextMenuItem(real fcode from P2) ===")
        try:
            results = await com.run(lambda: _p4_try_fcodes(session, target))
            for r in results:
                print(f"  {r}")
            if any(r.get("ok") for r in results):
                new_title = await backend.get_page_title()
                print(f"  page title after fcode select: {new_title!r}")
        except Exception as exc:
            print(f"P4 raised: {exc}")

        # Go back and retry for the text probe
        for _ in range(3):
            try:
                await backend.press_key("F3")
            except Exception:
                break
        await backend.enter_transaction("/n/NA2/DCS")
        target = await _expand_and_target(backend, com)

        print("\n=== P5: SelectContextMenuItemByText(real text from P2) ===")
        try:
            results = await com.run(lambda: _p5_try_exact_text(session, target))
            for r in results:
                print(f"  {r}")
            if any(r.get("ok") for r in results):
                import asyncio as _a

                await _a.sleep(3.0)
                diag = await com.run(lambda: _p6_diagnose_after_select(session))
                print(f"  diagnose after select+3s wait: {json.dumps(diag, indent=2, default=str)}")
        except Exception as exc:
            print(f"P5 raised: {exc}")

        # Reset and try double-click
        for _ in range(3):
            try:
                await backend.press_key("F3")
            except Exception:
                break
        await backend.enter_transaction("/n/NA2/DCS")
        target = await _expand_and_target(backend, com)

        print("\n=== P7: DoubleClickNode ===")
        try:
            r = await com.run(lambda: _p7_try_double_click(session, target))
            print(f"  {r}")
            import asyncio as _a

            await _a.sleep(2.0)
            diag = await com.run(lambda: _p6_diagnose_after_select(session))
            print(f"  diagnose after dblclick: {json.dumps(diag, indent=2, default=str)}")
        except Exception as exc:
            print(f"P7 raised: {exc}")

        return 0
    finally:
        for _ in range(5):
            try:
                await backend.press_key("F3")
            except Exception:
                break
        com.shutdown()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
