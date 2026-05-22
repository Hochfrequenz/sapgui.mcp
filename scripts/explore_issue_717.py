"""Exploratory live probe for issue #717.

Phase 1: Navigate ``/n/NA2/DCS`` on HF R/3, dump the tree, probe every
``id=`` the updated snapshot emits. Captures the snapshot under
``unittests/desktop/testdata/issue_717/`` for the fixture-based
regression test.

Phase 2: Drive the reporter's end-to-end workflow: expand the tree to
``DCS Projekte → AUSBILDUN → AUSB_EXT_PRD → Taskgruppe 100000 →
Taskgruppe 101000``, invoke ``nodeContextMenu`` + ``selectContextMenuItemByText``
for ``Task anlegen``, and verify the follow-up "DCS - Create Task"
screen opens. Proves the snapshot-ID fix is sufficient to unblock the
reporter without any new COM-scripting helper.

Exit code 0 if both phases succeed, 1 otherwise.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.desktop._com_thread import ComThread
from sapguimcp.models.config import get_sap_config
from sapguimcp.tools.com_tools import ComOperationInput, _execute_single_op

TREE_PATH = [
    "DCS Projekte",
    "AUSBILDUN",
    "AUSB_EXT_PRD",
    "Taskgruppe 100000",
    "Taskgruppe 101000",
]
CONTEXT_MENU_ITEM = "Task anlegen"


def _run_op(session, element_id: str, action: str, prop: str, args=None) -> dict:
    op = ComOperationInput(element_id=element_id, action=action, property_or_method=prop, args=args)
    res = _execute_single_op(session, op)
    return {"success": res.success, "error": res.error, "result": res.result}


async def _phase1_capture_and_probe(backend: DesktopBackend, com: ComThread, fixture_path: Path) -> int:
    r = await backend.enter_transaction("/n/NA2/DCS")
    sbar = await backend.get_status_bar()
    print(f"[phase1] nav: success={r.success} title={r.page_title!r}")
    print(f"[phase1] sbar: type={sbar.type!r} message={sbar.message!r}")
    if sbar.type in ("E", "A") and "unbekannt" in (sbar.message or "").lower():
        print("[phase1] /NA2/DCS not installed — skipping both phases")
        return -1

    snapshot, max_depth, hidden = await backend.get_snapshot_with_depth(depth=6)
    text = str(snapshot)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(text, encoding="utf-8")
    print(f"[phase1] saved {fixture_path} ({len(text)} chars, depth_max={max_depth}, hidden={hidden})")

    id_lines = [ln for ln in text.splitlines() if " id=" in ln]
    print(f"[phase1] {len(id_lines)} id= lines")

    session = backend.require_session()
    resolved = 0
    for ln in id_lines:
        eid = ln.rsplit(" id=", 1)[1].strip().split()[0]
        out = await com.run(lambda _eid=eid: _run_op(session, _eid, "get", "Type"))
        if out["success"]:
            resolved += 1
        else:
            print(f"[phase1] FAIL {eid!r}: {out['error']}")
    print(f"[phase1] resolved {resolved}/{len(id_lines)}")
    return resolved


async def _phase2_right_click(backend: DesktopBackend, com: ComThread, shell_id: str) -> bool:
    """Expand the reporter's path and invoke the 'Task anlegen' context menu."""
    print(f"\n[phase2] driving right-click on {shell_id!r}")
    session = backend.require_session()

    # Step 1: discover the node keys via GetAllNodeKeys — the TableTreeControl
    # exposes a flat list of keys that we filter by GetNodeTextByKey.
    all_keys_raw = await com.run(lambda: _run_op(session, shell_id, "call", "GetAllNodeKeys"))
    if not all_keys_raw["success"]:
        print(f"[phase2] GetAllNodeKeys failed: {all_keys_raw['error']}")
        return False

    all_keys = json.loads(all_keys_raw["result"]) if all_keys_raw["result"] else []
    # all_keys is a serialized COM collection — the entries look like
    # {"Id":..., "Type":..., "Name":..., "Text":...}. We only care that it has
    # a handle per entry — the actual key lives in "Text" or similar, but
    # TableTreeControl returns strings. Fall back to iteration via Count/Item(i).
    print(f"[phase2] GetAllNodeKeys -> {len(all_keys)} entries (first 3: {all_keys[:3]})")

    # Step 2: find the node whose text matches our target. Use GetNodeTextByKey.
    # Since the serialized collection above might not expose raw keys directly,
    # iterate a second way: read all keys as strings via Children.Count/Item.
    def _iter_keys() -> list[str]:
        wrapper = _run_op(session, shell_id, "get", "GetAllNodeKeys")
        # Re-fetch and re-interpret — the .result field is a JSON array of dicts
        # for our helper; for raw keys we need the COM collection. Use the
        # underlying FindById to bypass the helper.
        raw_session = getattr(session, "com", getattr(session, "_com", session))
        raw_shell = raw_session.FindById(shell_id)
        coll = raw_shell.GetAllNodeKeys()
        count = coll.Count
        return [str(coll.ElementAt(i)) for i in range(count)]

    try:
        keys = await com.run(_iter_keys)
    except Exception as exc:
        print(f"[phase2] raw iteration failed: {exc}")
        # Try the pysapgui ElementAt variant name
        try:
            keys = await com.run(
                lambda: [
                    str(
                        getattr(session, "com", getattr(session, "_com", session))
                        .FindById(shell_id)
                        .GetAllNodeKeys()
                        .Item(i)
                    )
                    for i in range(
                        getattr(session, "com", getattr(session, "_com", session))
                        .FindById(shell_id)
                        .GetAllNodeKeys()
                        .Count
                    )
                ]
            )
        except Exception as exc2:
            print(f"[phase2] fallback iteration failed too: {exc2}")
            return False

    print(f"[phase2] got {len(keys)} raw keys; sample: {keys[:5]}")

    # Step 3: map keys to their display text by calling GetNodeTextByKey per key.
    def _text_for(key: str) -> str:
        raw_shell = getattr(session, "com", getattr(session, "_com", session)).FindById(shell_id)
        return str(raw_shell.GetNodeTextByKey(key))

    key_texts: list[tuple[str, str]] = []
    for k in keys:
        try:
            t = await com.run(lambda _k=k: _text_for(_k))
            key_texts.append((k, t))
        except Exception:
            pass

    # Step 4: find the leaf by text; expand all ancestors along the way.
    def _find(target: str) -> str | None:
        for k, t in key_texts:
            if t.strip() == target:
                return k
        for k, t in key_texts:
            if target in t:
                return k
        return None

    expand_path = TREE_PATH[:-1]  # all but the last (that one is right-clicked, not expanded)
    for label in expand_path:
        k = _find(label)
        if k is None:
            print(f"[phase2] could not locate node {label!r} among {len(key_texts)} keys")
            return False
        out = await com.run(lambda _k=k: _run_op(session, shell_id, "call", "ExpandNode", args=[_k]))
        if not out["success"]:
            print(f"[phase2] ExpandNode({label!r}, {k!r}) failed: {out['error']}")
            return False
        print(f"[phase2] expanded {label!r} key={k!r}")
        # After expansion new children appear — re-scan keys.
        keys = await com.run(_iter_keys)
        key_texts = []
        for nk in keys:
            try:
                nt = await com.run(lambda _k=nk: _text_for(_k))
                key_texts.append((nk, nt))
            except Exception:
                pass

    target = TREE_PATH[-1]
    target_key = _find(target)
    if target_key is None:
        print(f"[phase2] target {target!r} not in expanded tree")
        return False
    print(f"[phase2] target {target!r} has key {target_key!r}")

    # Step 5: batch SelectNode + NodeContextMenu + SelectContextMenuItemByText
    # in ONE COM lambda — SAP GUI scripting closes the context menu between
    # separate roundtrips, so they must all run inside a single invocation.
    def _right_click(key: str = target_key) -> dict:
        raw = getattr(session, "com", getattr(session, "_com", session)).FindById(shell_id)
        raw.SelectNode(key)
        raw.NodeContextMenu(key)
        raw.SelectContextMenuItemByText(CONTEXT_MENU_ITEM)
        return {"ok": True}

    try:
        res = await com.run(_right_click)
        print(f"[phase2] batched right-click -> {res}")
    except Exception as exc:
        print(f"[phase2] batched right-click RAISED: {exc}")

    # Introspection: after NodeContextMenu, does a popup wnd[1] open?
    def _open_and_snapshot() -> tuple[str, str]:
        raw_session = getattr(session, "com", getattr(session, "_com", session))
        raw = raw_session.FindById(shell_id)
        raw.SelectNode(target_key)
        raw.NodeContextMenu(target_key)
        # Check for wnd[1] popup
        try:
            popup = raw_session.FindById("wnd[1]", False)
            title = str(popup.Text) if popup else ""
        except Exception:
            title = ""
        return title, str(raw_session.FindById("wnd[0]").Text)

    title1, title0 = await com.run(_open_and_snapshot)
    print(f"[phase2] after NodeContextMenu: wnd[0].Text={title0!r} wnd[1].Text={title1!r}")

    # Try SelectContextMenuItem (no ByText) with plausible function codes.
    for fcode in ("CRTSK", "CREA", "TASK_CREATE", "CREATE", "&CRTSK", "ANLG"):

        def _try_fcode(fc: str = fcode) -> dict:
            raw = getattr(session, "com", getattr(session, "_com", session)).FindById(shell_id)
            raw.SelectNode(target_key)
            raw.NodeContextMenu(target_key)
            raw.SelectContextMenuItem(fc)
            return {"ok": True, "fcode": fc}

        try:
            r = await com.run(_try_fcode)
            print(f"[phase2] SelectContextMenuItem({fcode!r}) -> {r}")
            break
        except Exception as exc2:
            print(f"[phase2] SelectContextMenuItem({fcode!r}) failed: {exc2}")

    await asyncio.sleep(0.5)
    new_title = await backend.get_page_title()
    print(f"[phase2] new page title: {new_title!r}")
    return "Create Task" in new_title or "Task anlegen" in new_title


async def main() -> int:
    cfg = get_sap_config()
    key = "HF R3 Mandant 100"
    if key not in cfg.systems:
        print(f"[skip] {key!r} not in systems.json")
        return 0
    sys_ = cfg.systems[key]
    com = ComThread()
    backend = DesktopBackend(com_thread=com)

    print(f"[login] {key} ({sys_.connection_name} client {sys_.client})")
    login = await backend.login(
        "x",
        sys_.user,
        sys_.password.get_secret_value(),
        sys_.client,
        sys_.language,
        connection_name=sys_.connection_name,
    )
    if not login.success:
        print(f"[fail] login: {login.error}")
        com.shutdown()
        return 1
    print(f"[ok] logged in as {login.user}")

    fixture = Path("unittests/desktop/testdata/issue_717/HF_R3_Mandant_100/n_NA2_DCS_snapshot.txt")
    try:
        resolved = await _phase1_capture_and_probe(backend, com, fixture)
        if resolved == -1:
            return 0
        if resolved == 0:
            print("[summary] phase1 resolved nothing")
            return 1

        ok2 = await _phase2_right_click(backend, com, "wnd[0]/shellcont/shell")
        print(f"\n[summary] phase1 resolved={resolved}, phase2 right-click opened create task = {ok2}")
        return 0 if ok2 else 1
    finally:
        try:
            for _ in range(10):
                await backend.press_key("F3")
        except Exception:
            pass
        com.shutdown()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
