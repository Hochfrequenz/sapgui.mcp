"""Stress test for COM thread under multi-session parallel load.

Reproduces the crash from issues #457/#459: multiple parallel agents
hammering the COM interface until RPC_E_DISCONNECTED.

This test:
1. Uses the shared backend fixture (logged-in DesktopBackend)
2. Fires rapid COM calls to measure baseline latency
3. Opens additional sessions and fires parallel reads
4. Measures: call latency, errors, throttle behavior
5. Proves the adaptive throttling prevents COM disconnection

Run with: pytest unittests/desktop/test_com_thread_stress.py -v -s
"""

import asyncio
import sys
import time

import pytest

from unittests.conftest import has_sap_desktop_creds

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only"),
    pytest.mark.skipif(not has_sap_desktop_creds(), reason="No SAP desktop credentials"),
]


async def _rapid_fire_reads(backend, session_id: str, num_calls: int) -> dict:
    """Fire rapid COM reads on a session. Returns stats."""
    successes = 0
    errors = 0
    latencies = []
    error_codes = []

    for _ in range(num_calls):
        start = time.monotonic()
        try:
            await backend.get_screen_text(session_id)
            duration = time.monotonic() - start
            latencies.append(duration)
            successes += 1
        except Exception as e:
            duration = time.monotonic() - start
            latencies.append(duration)
            errors += 1
            code = getattr(e, "hresult", None)
            if code is None and e.args and isinstance(e.args[0], int):
                code = e.args[0]
            error_codes.append(code)

    return {
        "session_id": session_id,
        "successes": successes,
        "errors": errors,
        "error_codes": error_codes,
        "avg_latency_ms": int(sum(latencies) / len(latencies) * 1000) if latencies else 0,
        "max_latency_ms": int(max(latencies) * 1000) if latencies else 0,
    }


@pytest.mark.anyio
async def test_single_session_rapid_fire(backend):
    """Baseline: 50 rapid COM calls on a single session. Should not crash."""
    stats = await _rapid_fire_reads(backend, "s1", num_calls=50)
    print(f"\nSingle session rapid fire: {stats}")
    print(f"COM thread interval: {backend.com.current_interval_ms}ms")

    assert stats["errors"] == 0, f"Got {stats['errors']} errors: {stats['error_codes']}"
    assert stats["successes"] == 50


@pytest.mark.anyio
async def test_multi_session_parallel_stress(backend):
    """Reproduce #457: parallel reads across multiple sessions.

    Opens 2 additional sessions (3 total), fires 30 reads per session
    in parallel. Without adaptive throttling, this crashes after ~50-70
    calls. With throttling, it should survive by backing off.
    """
    extra_session_ids = []

    try:
        # Open 2 extra sessions
        for _ in range(2):
            sid, _count, _title = await backend.open_new_session("SESSION_MANAGER")
            if sid:
                extra_session_ids.append(sid)
                await asyncio.sleep(2)

        all_sessions = ["s1"] + extra_session_ids
        print(f"\nSessions: {all_sessions}")

        # Fire parallel reads across all sessions
        calls_per_session = 30
        tasks = [_rapid_fire_reads(backend, sid, calls_per_session) for sid in all_sessions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_successes = 0
        total_errors = 0
        for r in results:
            if isinstance(r, Exception):
                print(f"  Task failed: {r}")
                total_errors += calls_per_session
            else:
                print(
                    f"  {r['session_id']}: {r['successes']}/{calls_per_session} ok, "
                    f"avg={r['avg_latency_ms']}ms, max={r['max_latency_ms']}ms, "
                    f"errors={r['error_codes']}"
                )
                total_successes += r["successes"]
                total_errors += r["errors"]

        print(f"\nTotal: {total_successes}/{len(all_sessions) * calls_per_session} ok, {total_errors} errors")
        print(f"Final COM interval: {backend.com.current_interval_ms}ms")

        # Success criteria: zero COM disconnections
        # RETRYLATER errors are acceptable (they get retried internally)
        disconnect_errors = sum(
            1 for r in results if isinstance(r, dict) for code in r.get("error_codes", []) if code == -2147417848
        )
        assert disconnect_errors == 0, f"Got {disconnect_errors} COM disconnections — throttling failed"

    finally:
        # Close extra sessions
        for sid in extra_session_ids:
            try:
                await backend.close_session(sid)
            except Exception:
                pass
