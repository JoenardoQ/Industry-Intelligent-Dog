"""Single frozen entry point for the IntDog API and research CLI."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys


def _serve(port: int) -> None:
    import uvicorn
    from DomainIntelWeb.api.main import app
    from DomainIntelWeb.api.lifecycle import register_shutdown

    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, reload=False,
        access_log=False, log_level="info"))
    register_shutdown(lambda: setattr(server, "should_exit", True))
    server.run()


def _cli(arguments: list[str]) -> None:
    sys.argv = ["intdog", *arguments]
    from src.main import main

    main()


def main() -> None:
    parser = argparse.ArgumentParser(prog="intdog-runtime")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    serve = subparsers.add_parser("serve")
    serve.add_argument("--port", type=int, required=True)
    cli = subparsers.add_parser("cli")
    cli.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("INTDOG_DISABLE_EMAIL", "1")
    if args.mode == "serve":
        _serve(args.port)
    else:
        _cli(args.arguments)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
