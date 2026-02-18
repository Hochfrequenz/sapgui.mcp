"""Smoke test for the standalone executable.

Starts the exe, sends an MCP initialize request, verifies the response.
Usage: python unittests/smoke_test_exe.py <path-to-exe>
"""

import json
import subprocess
import sys
import time


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python smoke_test_exe.py <path-to-exe>")
        sys.exit(1)

    exe_path = sys.argv[1]
    initialize_request = json.dumps(
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

    print(f"Starting {exe_path}...")
    proc = subprocess.Popen(
        [exe_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Give the server a moment to start
        time.sleep(3)

        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            print(f"FAIL: Process exited early with code {proc.returncode}")
            print(f"stderr: {stderr}")
            sys.exit(1)

        # Send initialize request
        assert proc.stdin is not None
        proc.stdin.write(initialize_request + "\n")
        proc.stdin.flush()

        # Read response with timeout
        assert proc.stdout is not None
        start = time.time()
        while time.time() - start < 10:
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "result" in data:
                    print(f"OK: Got valid MCP initialize response: {json.dumps(data['result'], indent=2)[:200]}")
                    sys.exit(0)
                if "error" in data:
                    print(f"FAIL: Got error response: {data}")
                    sys.exit(1)
            except json.JSONDecodeError:
                continue

        print("FAIL: No valid JSON-RPC response received within 10 seconds")
        sys.exit(1)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
