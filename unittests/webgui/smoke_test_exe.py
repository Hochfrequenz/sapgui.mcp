"""Smoke test for the standalone executable.

Starts the exe, sends an MCP initialize request (line-delimited JSON on stdin),
and verifies the response (line-delimited JSON on stdout).

Usage: python unittests/smoke_test_exe.py <path-to-exe>
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python smoke_test_exe.py <path-to-exe>")
        sys.exit(1)

    exe_path = sys.argv[1]

    if not os.path.isfile(exe_path):
        print(f"FAIL: Executable not found: {exe_path}")
        sys.exit(1)

    print(f"Starting {exe_path}...")
    stderr_file = tempfile.TemporaryFile(mode="w+b")
    proc = subprocess.Popen(
        [exe_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_file,
    )

    try:
        # Wait for the server to start (PyInstaller --onefile decompresses on first run)
        for i in range(20):
            time.sleep(1)
            if proc.poll() is not None:
                stderr_file.seek(0)
                stderr = stderr_file.read().decode("utf-8", errors="replace")
                print(f"FAIL: Process exited early with code {proc.returncode}")
                print(f"stderr: {stderr[:2000]}")
                sys.exit(1)
            if i >= 4:  # Wait at least 5 seconds before proceeding
                break

        print("Server running. Sending MCP initialize request...")

        # MCP stdio transport uses line-delimited JSON (one JSON object per line)
        msg = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "smoke-test", "version": "0.1.0"},
                },
            }
        )
        assert proc.stdin is not None
        proc.stdin.write(msg.encode("utf-8") + b"\n")
        proc.stdin.flush()

        # Read response lines from stdout in a thread (with timeout)
        assert proc.stdout is not None
        output_lines: list[bytes] = []

        def reader() -> None:
            assert proc.stdout is not None
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                output_lines.append(line)
                # Stop after we get a JSON-RPC response
                try:
                    data = json.loads(line)
                    if "result" in data or "error" in data:
                        return
                except json.JSONDecodeError:
                    continue

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout=15.0)

        if not output_lines:
            stderr_file.seek(0)
            stderr = stderr_file.read().decode("utf-8", errors="replace")
            print("FAIL: No output received within 15 seconds")
            print(f"stderr: {stderr[:2000]}")
            sys.exit(1)

        # Find the JSON-RPC response
        for line in output_lines:
            try:
                data = json.loads(line)
                if "result" in data:
                    print(f"OK: Got valid MCP initialize response: {json.dumps(data['result'], indent=2)[:300]}")
                    sys.exit(0)
                if "error" in data:
                    print(f"FAIL: Got error response: {json.dumps(data['error'])}")
                    sys.exit(1)
            except json.JSONDecodeError:
                continue

        print(f"FAIL: No JSON-RPC response found in {len(output_lines)} output lines")
        for line in output_lines[:5]:
            print(f"  line: {line[:200]}")
        sys.exit(1)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr_file.close()


if __name__ == "__main__":
    main()
