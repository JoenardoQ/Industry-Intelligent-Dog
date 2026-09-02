"""Single frozen entry point for the IntDog API and research CLI."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from datetime import datetime
from pathlib import Path


def _install_import_roots() -> Path:
    configured = os.environ.get("INTDOG_PROJECT_ROOT", "").strip()
    if configured:
        project_root = Path(configured)
    elif getattr(sys, "frozen", False):
        project_root = Path(sys.executable).resolve().parent.parent / "intdog"
    else:
        project_root = Path(__file__).resolve().parents[2]
    project_root = project_root.resolve()
    search_root = project_root / "DomainIntelSearch"
    os.environ.setdefault("INTDOG_PROJECT_ROOT", str(project_root))
    os.environ.setdefault("INTDOG_SEARCH_ROOT", str(search_root))
    for root in (project_root / "DomainIntelSearch",
                 project_root / "DomainIntelApp", project_root):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    return project_root


def _load_pipe_credentials() -> None:
    if os.environ.pop("INTDOG_CREDENTIAL_PIPE", "") != "1":
        return
    _install_import_roots()
    from runtime.credential_pipe import read_credential_frame
    from src.services.runtime_credentials import install_runtime_credential

    value = read_credential_frame(sys.stdin.buffer, allow_eof=False)
    install_runtime_credential(value)


def _serve(port: int) -> None:
    _load_pipe_credentials()
    import uvicorn
    from DomainIntelWeb.api.main import app
    from DomainIntelWeb.api.lifecycle import register_shutdown

    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, reload=False,
        access_log=False, log_level="info"))
    register_shutdown(lambda: setattr(server, "should_exit", True))
    server.run()


def _cli(arguments: list[str]) -> None:
    _load_pipe_credentials()
    sys.argv = ["intdog", *arguments]
    from src.main import main

    main()


def _worker_once() -> None:
    """Claim due schedules, await their jobs, then exit without a UI."""
    project_root = _install_import_roots()
    search_root = project_root / "DomainIntelSearch"
    data_root = Path(os.environ.get("DOMAIN_INTEL_DATA_ROOT")
                     or os.environ.get("INTDOG_DATA_ROOT")
                     or project_root / "DomainIntelData")
    _load_pipe_credentials()
    from intdog_core import IntDogService
    from runtime.jobs import JobManager
    from src.background_worker import BackgroundWorker
    from src.services.runtime_credentials import credential_bundle

    service = IntDogService(data_root)
    jobs = JobManager(
        data_root, ledger=service.repo, credential_supplier=credential_bundle)
    worker = BackgroundWorker(
        data_root, jobs, search_root=search_root, project_root=project_root)
    summary = worker.run_once(datetime.now().astimezone())
    print(__import__("json").dumps(summary.__dict__, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(prog="intdog-runtime")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    serve = subparsers.add_parser("serve")
    serve.add_argument("--port", type=int, required=True)
    cli = subparsers.add_parser("cli")
    cli.add_argument("arguments", nargs=argparse.REMAINDER)
    worker = subparsers.add_parser("worker")
    worker.add_argument("--once", action="store_true", required=True)
    args = parser.parse_args()
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("INTDOG_DISABLE_EMAIL", "1")
    _install_import_roots()
    if args.mode == "serve":
        _serve(args.port)
    elif args.mode == "cli":
        _cli(args.arguments)
    else:
        _worker_once()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
