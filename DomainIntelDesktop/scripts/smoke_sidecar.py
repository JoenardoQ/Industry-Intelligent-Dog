"""Native, headless smoke test for the frozen IntDog sidecar."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen


def available_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.resolve()
    if not executable.is_file():
        raise SystemExit(f"sidecar missing: {executable}")
    root = Path(__file__).resolve().parents[2]
    resources = root / "DomainIntelDesktop" / "build" / "resources" / "intdog"
    token = secrets.token_urlsafe(32)
    port = available_port()
    with tempfile.TemporaryDirectory(prefix="intdog-package-smoke-") as temporary:
        env = {
            **os.environ,
            "INTDOG_PROJECT_ROOT": str(resources),
            "INTDOG_SEARCH_ROOT": str(resources / "DomainIntelSearch"),
            "DOMAIN_INTEL_DATA_ROOT": str(Path(temporary) / "data"),
            "INTDOG_SEARCH_EXECUTABLE": str(executable),
            "INTDOG_SESSION_TOKEN": token,
            "INTDOG_DISABLE_EMAIL": "1",
            "PYTHONUTF8": "1",
        }
        cli = subprocess.run([str(executable), "cli", "industries"], env=env,
                             capture_output=True, text=True, timeout=30)
        if cli.returncode:
            raise SystemExit(f"sidecar CLI failed ({cli.returncode}): {cli.stderr}")
        process = subprocess.Popen([str(executable), "serve", "--port", str(port)],
                                   env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 30
            health = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise SystemExit(f"sidecar exited early ({process.returncode})")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                        health = json.load(response)
                    break
                except OSError:
                    time.sleep(0.25)
            if not health or health.get("status") != "ready" or not health.get("session_required"):
                raise SystemExit(f"invalid sidecar health: {health!r}")
            request = Request(f"http://127.0.0.1:{port}/api/shutdown", method="POST",
                              headers={"X-IntDog-Session": token})
            with urlopen(request, timeout=2) as response:
                if response.status != 202:
                    raise SystemExit(f"shutdown returned {response.status}")
            returncode = process.wait(timeout=5)
            if returncode != 0:
                raise SystemExit(f"sidecar did not shut down gracefully ({returncode})")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
