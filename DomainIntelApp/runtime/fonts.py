"""Cross-platform font names with complete Simplified Chinese coverage."""

from __future__ import annotations

import os


UI_FONT = "Segoe UI Variable" if os.name == "nt" else "IntDog UI"
MONO_FONT = "Consolas" if os.name == "nt" else "IntDog Mono"
