"""Windows high-DPI helpers for crisp Tk rendering."""

from __future__ import annotations

import os


def enable_high_dpi() -> None:
    """Opt into native per-monitor pixels before creating the first Tk window."""
    if os.name != "nt":
        return
    import ctypes

    try:
        # Windows 10 Creators Update+: PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        # Windows 8.1 fallback: PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def apply_tk_scaling(root) -> float:
    """Match Tk points to the monitor DPI and return the applied scale."""
    try:
        dpi = float(root.winfo_fpixels("1i"))
        scale = min(3.0, max(1.0, dpi / 72.0))
        root.tk.call("tk", "scaling", scale)
        return scale
    except Exception:
        return 1.0
