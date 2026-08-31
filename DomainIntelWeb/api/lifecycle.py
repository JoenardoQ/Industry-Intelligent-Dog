"""Cross-platform API server lifecycle bridge."""

from __future__ import annotations

import os
import signal
from collections.abc import Callable


_shutdown: Callable[[], None] | None = None


def register_shutdown(callback: Callable[[], None] | None) -> None:
    global _shutdown
    _shutdown = callback


def request_shutdown() -> None:
    if _shutdown is not None:
        _shutdown()
        return
    os.kill(os.getpid(), signal.SIGINT)
