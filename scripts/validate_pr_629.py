"""Manual validation harness for PR #629 (COM thread recovery, fixes #628).

NOT a pytest test. Run directly: ``python scripts/validate_pr_629.py <test>``
where <test> is one of: t1, t2, t3, t4, all.

Captures all log output (stdout + file) so the new forensic snapshots from
``com_thread_crashed`` and ``com_thread_dead_call_attempted`` can be inspected.

Each test exercises BackendManager.get_or_create() the same way ``sap_login_impl``
and other tools do, so the recovery path is faithfully covered.
"""

# pylint: skip-file

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# MUST be set before importing the manager so the singleton picks up desktop.
os.environ["BACKEND_TYPE"] = "desktop"

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# Now safe to import the manager and tools.
from sapguimcp.backend.manager import (  # noqa: E402
    get_backend,
    get_backend_manager,
    reset_backend_manager,
)
from sapguimcp.tools.sap_login_impl import sap_login_impl  # noqa: E402

LOG_DIR = Path("C:/github/sapgui.mcp/scripts/validation_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(test_name: str) -> Path:
    """Capture all log output to a per-test file (and to stdout)."""
    log_file = LOG_DIR / f"{test_name}_{int(time.time())}.log"
    fmt = "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-50s %(message)s"
    datefmt = "%H:%M:%S"
    handlers = [
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(level=logging.DEBUG, format=fmt, datefmt=datefmt, handlers=handlers, force=True)
    # Quiet down noisy libraries
    for noisy in ("asyncio", "httpx", "urllib3", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    print(f"\n=== logging to {log_file} ===\n")
    return log_file


def kill_saplogon() -> bool:
    """Kill saplogon.exe via taskkill /F. Returns True if a process was killed."""
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "saplogon.exe"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        print(f"taskkill rc={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}")
        return result.returncode == 0
    except Exception as exc:
        print(f"taskkill failed: {exc!r}")
        return False


def kill_sapgui_processes() -> int:
    """Kill ALL SAP GUI processes (saplogon.exe, sapgui.exe). Returns count killed."""
    killed = 0
    for image in ("saplogon.exe", "sapgui.exe"):
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", image],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                killed += 1
                print(f"killed {image}")
            else:
                print(f"taskkill {image} rc={result.returncode}: {result.stderr.strip()}")
        except Exception as exc:
            print(f"taskkill {image} failed: {exc!r}")
    return killed


# ----------------------------------------------------------------------------
# Test 1: Happy path
# ----------------------------------------------------------------------------


async def test_1_happy_path() -> bool:
    """Login → enter /nBP → enter /nSE16 → check session_status → cleanup."""
    print("\n--- Test 1: Happy path ---")
    reset_backend_manager()  # fresh manager state

    login_result = await sap_login_impl()
    print(f"sap_login: success={login_result.success} error={login_result.error}")
    if not login_result.success:
        return False

    backend = await get_backend(tool_name="test_1")

    print("entering /nBP")
    bp_result = await backend.enter_transaction("BP")
    print(f"  result={bp_result.success} title={bp_result.page_title!r}")

    print("entering /nSE16")
    se16_result = await backend.enter_transaction("SE16")
    print(f"  result={se16_result.success} title={se16_result.page_title!r}")

    print("get_session_status")
    status = await backend.get_session_status()
    print(f"  status={status.status} message={status.message!r}")

    # Cleanup: F3 a few times to get back to easy access, but don't bother if it fails
    try:
        for _ in range(5):
            await backend.press_key("F3")
    except Exception as exc:
        print(f"cleanup F3 failed: {exc!r}")

    return bp_result.success and se16_result.success and status.status == "active"


# ----------------------------------------------------------------------------
# Test 2: Recovery after kill
# ----------------------------------------------------------------------------


async def test_2_recovery_after_kill() -> bool:
    """Login → start a transaction → kill saplogon → next call should fail
    → call sap_login again → should recover via _recover_desktop_if_dead."""
    print("\n--- Test 2: Recovery after killing saplogon.exe ---")
    reset_backend_manager()

    # Step 1: Login + verify
    login_result = await sap_login_impl()
    print(f"initial sap_login: success={login_result.success}")
    if not login_result.success:
        print(f"FAIL — initial login failed: {login_result.error}")
        return False

    backend = await get_backend(tool_name="test_2_pre")
    bp_result = await backend.enter_transaction("BP")
    print(f"pre-kill BP: success={bp_result.success}")

    # Step 2: Kill saplogon. We can't really do this "while a call is in flight"
    # without race-condition complexity; killing it BETWEEN calls produces the
    # same effect — the next COM call against the dead apartment fails. The
    # important thing is that *some* tool call after the kill triggers the
    # worker to die so the recovery path is exercised.
    print("\nKILLING SAP GUI PROCESSES NOW")
    killed = kill_sapgui_processes()
    print(f"killed {killed} processes")
    await asyncio.sleep(2.0)  # let Windows actually reap them

    # Step 3: Try a tool call — this should fail (the worker may or may not be
    # dead yet; it depends on whether the COM call escapes _execute_with_retry's
    # except handler).
    print("\nattempting tool call against dead/dying SAP GUI")
    try:
        backend2 = await get_backend(tool_name="test_2_post_kill")
        post_kill_status = await backend2.get_session_status()
        print(f"post-kill status: {post_kill_status.status} message={post_kill_status.message!r}")
    except Exception as exc:
        print(f"post-kill call raised: {type(exc).__name__}: {exc}")

    # Step 4: Critical — call sap_login again. This must recover.
    print("\n=== CRITICAL: calling sap_login again to test recovery ===")
    recovery_login = await sap_login_impl()
    print(f"recovery sap_login: success={recovery_login.success} error={recovery_login.error}")
    if not recovery_login.success:
        print("FAIL — recovery login did not succeed")
        return False

    # Step 5: Verify the recovered session works
    backend3 = await get_backend(tool_name="test_2_post_recovery")
    post_recovery_bp = await backend3.enter_transaction("BP")
    print(f"post-recovery BP: success={post_recovery_bp.success}")

    return recovery_login.success and post_recovery_bp.success


# ----------------------------------------------------------------------------
# Test 2b: SYNTHETIC worker death (the actual code path PR #629 fixes)
# ----------------------------------------------------------------------------


async def test_2b_synthetic_worker_death() -> bool:
    """Login → call ComThread.shutdown() to forcibly kill the worker →
    verify is_alive=False → call sap_login_impl() → verify
    desktop_com_thread_dead_rebuilding fired and recovery worked."""
    print("\n--- Test 2b: Synthetic worker death (PR #629's actual code path) ---")
    reset_backend_manager()

    # Step 1: establish working state
    initial = await sap_login_impl()
    print(f"initial sap_login: success={initial.success}")
    if not initial.success:
        return False

    # Verify the session is usable
    backend = await get_backend(tool_name="t2b_pre_kill")
    pre_status = await backend.get_session_status()
    print(f"pre-kill status: {pre_status.status}")
    if pre_status.status != "active":
        return False

    # Step 2: forcibly kill the COM worker thread.
    # This is what the PR's recovery is supposed to handle.
    mgr = get_backend_manager()
    com = mgr._com_thread
    assert com is not None, "manager has no com thread after login?"
    print(f"\nKILLING COM WORKER VIA shutdown()  is_alive_before={com.is_alive}")
    com.shutdown()
    # Wait for join to settle
    await asyncio.sleep(0.5)
    print(f"is_alive_after_shutdown={com.is_alive}")
    if com.is_alive:
        print("FAIL — worker still alive after shutdown()")
        return False

    # Step 3: try a tool call against the dead worker.
    # Per the PR, the call to get_backend() should trigger _recover_desktop_if_dead
    # which logs `desktop_com_thread_dead_rebuilding`. Then sap_login_impl
    # constructs a fresh backend and re-establishes the session.
    print("\n=== calling sap_login_impl (recovery) ===")
    recovery = await sap_login_impl()
    print(f"recovery sap_login: success={recovery.success} error={recovery.error}")
    if not recovery.success:
        print("FAIL — recovery did not succeed")
        return False

    # Step 4: verify the new worker thread is alive and the new backend works
    new_com = get_backend_manager()._com_thread
    print(f"new_com is_alive={new_com.is_alive}  is_same_object={new_com is com}")
    if not new_com.is_alive or new_com is com:
        print("FAIL — new com thread not properly rebuilt")
        return False

    backend2 = await get_backend(tool_name="t2b_post_recovery")
    post_status = await backend2.get_session_status()
    print(f"post-recovery status: {post_status.status} message={post_status.message!r}")

    post_bp = await backend2.enter_transaction("BP")
    print(f"post-recovery BP: success={post_bp.success}")

    return post_status.status == "active" and post_bp.success


# ----------------------------------------------------------------------------
# Test 3: Concurrent recovery (5 parallel)
# ----------------------------------------------------------------------------


async def test_3_concurrent_recovery() -> bool:
    """Synthetic worker death (via shutdown()), then 2 parallel sap_login calls.

    This is a real-SAP **smoke test** for the end-to-end recovery path:
    synthetic worker death → concurrent recovery → both logins succeed →
    fresh ComThread is alive. It does NOT serve as the primary verification
    of PR #629's lock semantics — those are covered by faster, more
    isolated unit tests on Linux/CI:

    * ``unittests/test_backend_manager.py::test_recover_desktop_if_dead_concurrent_only_clears_once``
      — uses mocked dead threads to assert ``desktop_com_thread_dead_rebuilding``
      fires exactly once under ``asyncio.gather`` recovery, no SAP needed.
    * ``unittests/test_backend_manager.py::test_recover_desktop_if_dead_blocks_when_lock_held``
      — pre-acquires the recovery lock externally and proves the second
      caller actually waits, instead of relying on coincidental ordering.

    The unit tests are stronger than this harness test because they
    isolate the property under verification (lock-fires-once) without
    depending on real SAP server-side state. This harness test
    complements them by exercising the *integration* — actual ComThread
    rebuild + DesktopBackend re-cache + real ``_sapsucker_login`` calls.

    Why 2 logins, not 5: cumulative real-SAP logins accumulate user
    sessions on the SAP server (the multiple-logon-popup handler chooses
    "continue without ending other sessions"). Past 3-4 rapid logins,
    ``OpenConnection`` starts hitting RPC errors that take several
    minutes to clear server-side. 2 is the minimum for a meaningful
    concurrency test (two coroutines racing for the lock) and dramatically
    reduces the SAP-side state pressure compared to the previous 5-login
    flood. See issue #635 for the original flakiness investigation.

    Why synthetic worker death: T2 showed that killing saplogon.exe
    externally does not actually kill the COM worker thread — exceptions
    are caught inside ``_execute_with_retry``. To exercise the PR's
    recovery path the worker must actually be dead, so we shut it down
    explicitly via ``com.shutdown()``.

    Known limitations / how to run reliably:

    * Run against a SAP user that has no other active sessions. SM04 in
      another window can show you the current session count for your user.
    * If T3 starts failing with ``Could not open connection`` or
      ``RPC_S_UNKNOWN_IF``, wait several minutes for SAP to prune idle
      sessions, OR log in via SAP GUI manually and close all your sessions.
    * The unit tests above run on every PR in CI and catch regressions to
      the lock semantics — this harness test is for once-per-PR manual
      smoke testing only.
    """
    print("\n--- Test 3: Concurrent recovery (2 parallel logins, smoke test) ---")
    reset_backend_manager()

    # Establish working state
    initial = await sap_login_impl()
    print(f"initial sap_login: success={initial.success}")
    if not initial.success:
        print(f"FAIL — initial login failed: {initial.error}")
        return False

    # Synthetically kill the worker
    mgr = get_backend_manager()
    com = mgr._com_thread
    assert com is not None
    print(f"\nKILLING COM WORKER VIA shutdown()  is_alive_before={com.is_alive}")
    com.shutdown()
    await asyncio.sleep(0.5)
    print(f"is_alive_after_shutdown={com.is_alive}")
    if com.is_alive:
        print("FAIL — worker still alive after shutdown()")
        return False

    # Step 3: 2 parallel sap_login calls — minimum for a meaningful
    # concurrency test, and small enough to keep SAP-side session
    # accumulation manageable across repeated harness runs.
    print("\n=== launching 2 parallel sap_login calls ===")

    async def one_login(i: int):
        try:
            result = await sap_login_impl()
            return (i, result.success, result.error)
        except Exception as exc:
            return (i, False, f"{type(exc).__name__}: {exc}")

    results = await asyncio.gather(*(one_login(i) for i in range(2)))
    for i, success, err in results:
        print(f"login[{i}]: success={success} error={err!r}")

    all_succeeded = all(s for _, s, _ in results)

    # Final state check: only ONE rebuild should have happened. The new
    # com thread should be alive and a different object than the original.
    new_com = get_backend_manager()._com_thread
    print(f"\nfinal: new_com.is_alive={new_com.is_alive}  is_same_object={new_com is com}")

    # Note: counting `desktop_com_thread_dead_rebuilding` log lines from
    # within the test would require a custom handler. The caller will grep
    # the log file after the run to count occurrences. The unit tests
    # cited in this function's docstring assert this exactly via
    # patch.object(logger, 'warning'); refer to those for the canonical
    # count check.

    return all_succeeded and new_com.is_alive and new_com is not com


# ----------------------------------------------------------------------------
# Test 4: Try to reproduce RPC_E_DISCONNECTED
# ----------------------------------------------------------------------------


async def test_4_rpc_disconnect() -> bool:
    """Try to overload COM by hammering it from many concurrent agents."""
    print("\n--- Test 4: Try to reproduce RPC_E_DISCONNECTED ---")
    reset_backend_manager()

    initial = await sap_login_impl()
    if not initial.success:
        print(f"FAIL — initial login failed: {initial.error}")
        return False

    print("hammering COM with 30 concurrent get_session_status calls")

    async def hammer(i: int):
        try:
            backend = await get_backend(tool_name=f"test_4_hammer_{i}")
            status = await backend.get_session_status()
            return (i, True, status.status)
        except Exception as exc:
            return (i, False, f"{type(exc).__name__}: {exc}")

    results = await asyncio.gather(*(hammer(i) for i in range(30)))
    fails = [r for r in results if not r[1]]
    print(f"results: {len(results) - len(fails)} ok, {len(fails)} failed")
    for i, ok, msg in fails[:5]:
        print(f"  fail[{i}]: {msg}")

    # Even if no DISCONNECTED, log throttle stats
    mgr = get_backend_manager()
    if mgr._com_thread is not None:
        print(f"final interval: {mgr._com_thread.current_interval_ms}ms")

    # Test "passes" if we successfully ran all calls; we're really just looking
    # for whether RPC_E_DISCONNECTED appears in logs.
    return True


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------


TESTS = {
    "t1": test_1_happy_path,
    "t2": test_2_recovery_after_kill,
    "t2b": test_2b_synthetic_worker_death,
    "t3": test_3_concurrent_recovery,
    "t4": test_4_rpc_disconnect,
}


async def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in (*TESTS.keys(), "all"):
        print(f"usage: python {sys.argv[0]} {{{'|'.join((*TESTS.keys(), 'all'))}}}")
        return 2

    targets = list(TESTS.keys()) if sys.argv[1] == "all" else [sys.argv[1]]

    overall = True
    for name in targets:
        log_file = setup_logging(name)
        try:
            ok = await TESTS[name]()
            print(f"\n{name}: {'PASS' if ok else 'FAIL'}  log={log_file}")
            overall = overall and ok
        except Exception as exc:
            logging.exception("test %s crashed", name)
            print(f"\n{name}: CRASH ({type(exc).__name__}: {exc})  log={log_file}")
            overall = False
        finally:
            from sapguimcp.backend.manager import close_backend

            try:
                await close_backend()
            except Exception as exc:
                print(f"close_backend failed: {exc!r}")
            reset_backend_manager()

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
