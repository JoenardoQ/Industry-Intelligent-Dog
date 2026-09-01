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
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen


def available_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def request_json(url: str, *, token: str, method: str = "GET",
                 payload: dict | None = None) -> object:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"X-IntDog-Session": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, method=method, headers=headers)
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def verify_resources(resources: Path) -> None:
    manifest_path = resources / "resource-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "intdog-resource-manifest-v1":
        raise SystemExit("invalid frozen resource manifest")
    for row in manifest.get("files", []):
        target = resources / row["path"]
        if not target.is_file() or target.stat().st_size != row["size"]:
            raise SystemExit(f"frozen resource missing or truncated: {row['path']}")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            raise SystemExit(f"frozen resource digest mismatch: {row['path']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.resolve()
    if not executable.is_file():
        raise SystemExit(f"sidecar missing: {executable}")
    root = Path(__file__).resolve().parents[2]
    resources = root / "DomainIntelDesktop" / "build" / "resources" / "intdog"
    verify_resources(resources)
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
        worker = subprocess.run([str(executable), "worker", "--once"], env=env,
                                capture_output=True, text=True, timeout=30)
        if worker.returncode:
            raise SystemExit(
                f"sidecar Worker failed ({worker.returncode}): {worker.stderr[-4000:]}")
        try:
            worker_result = json.loads(worker.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise SystemExit("sidecar Worker did not return structured diagnostics") from exc
        if not isinstance(worker_result.get("claimed"), int):
            raise SystemExit(f"invalid sidecar Worker result: {worker_result!r}")
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
            origin = f"http://127.0.0.1:{port}/api"
            setup = request_json(f"{origin}/setup", token=token)
            if not setup.get("runtime_ready") or not setup.get("taskpack_ready"):
                raise SystemExit(f"invalid setup contract: {setup!r}")
            request_json(f"{origin}/industries", token=token, method="POST",
                         payload={"folder": "E2E", "name": "发行验收行业"})
            accepted = request_json(
                f"{origin}/industries/E2E/generate", token=token, method="POST",
                payload={"action": "bootstrap", "kind": "", "event": "",
                         "provider": "", "pipeline_mode": "generate"})
            deadline = time.monotonic() + 60
            final = None
            while time.monotonic() < deadline:
                rows = request_json(f"{origin}/jobs", token=token)
                final = next((row for row in rows
                              if row.get("run_id") == accepted.get("run_id")), None)
                if final and final.get("status") not in {
                        "queued", "running", "cancelling"}:
                    break
                time.sleep(0.25)
            if not final or final.get("status") != "completed":
                raise SystemExit(f"frozen first workflow failed: {final!r}")
            overview = request_json(f"{origin}/industries/E2E/overview", token=token)
            if not overview.get("industry") or not isinstance(overview.get("chain"), list):
                raise SystemExit(f"invalid frozen overview: {overview!r}")
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
