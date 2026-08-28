"""One-click bootstrapper: show loading UI, create runtime, then launch IntDog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
SEARCH_DIR = PROJECT_DIR / "DomainIntelSearch"
RUNTIME_DIR = PROJECT_DIR / ".intdog-runtime"
VENV_DIR = RUNTIME_DIR / "venv"
MARKER = RUNTIME_DIR / "environment.json"
LOG_FILE = RUNTIME_DIR / "install.log"


def _venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _fingerprint() -> str:
    source = SEARCH_DIR / "pyproject.toml"
    return hashlib.sha256(source.read_bytes()).hexdigest()[:16] if source.exists() else "missing"


def runtime_state() -> dict:
    marker = {}
    try:
        marker = json.loads(MARKER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    ready = _venv_python().exists() and marker.get("fingerprint") == _fingerprint()
    return {"ready": ready, "python": str(_venv_python()), "runtime": str(RUNTIME_DIR),
            "fingerprint": _fingerprint(), "installed": marker.get("fingerprint", "")}


def ensure_runtime(update) -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    python = _venv_python()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with LOG_FILE.open("a", encoding="utf-8") as log:
        if not python.exists():
            update("首次运行：正在创建隔离环境…")
            subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)],
                           stdout=log, stderr=subprocess.STDOUT, check=True,
                           creationflags=flags)
        if not runtime_state()["ready"]:
            update("正在安装并校验 IntDog 运行组件…")
            subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                            "-e", str(SEARCH_DIR)], stdout=log,
                           stderr=subprocess.STDOUT, check=True,
                           creationflags=flags)
            MARKER.write_text(json.dumps({"fingerprint": _fingerprint(),
                                          "python": str(python)}, indent=2), encoding="utf-8")
    return python


def launch() -> int:
    from desktop.dpi import apply_tk_scaling, enable_high_dpi

    enable_high_dpi()
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    apply_tk_scaling(root)
    root.title("IntDog 正在启动")
    root.geometry("540x270")
    root.resizable(False, False)
    root.configure(bg="#F3F5F6")
    try:
        root.iconbitmap(str(APP_DIR / "app" / "intdog.ico"))
    except tk.TclError:
        pass
    card = tk.Frame(root, bg="#FFFFFF", highlightbackground="#D7DDE1", highlightthickness=1)
    card.pack(fill="both", expand=True, padx=18, pady=18)
    tk.Label(card, text="IntDog", bg="#FFFFFF", fg="#27343B",
             font=("Microsoft YaHei UI", 21, "bold")).pack(anchor="w", padx=26, pady=(30, 2))
    tk.Label(card, text="Industry Intelligence Workspace", bg="#FFFFFF", fg="#7A858B",
             font=("Segoe UI", 9)).pack(anchor="w", padx=26)
    status = tk.StringVar(value="正在检查运行环境…")
    tk.Label(card, textvariable=status, bg="#FFFFFF", fg="#607D8B",
             font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=26, pady=(24, 10))
    bar = ttk.Progressbar(card, mode="indeterminate")
    bar.pack(fill="x", padx=26); bar.start(10)

    def update(text):
        root.after(0, status.set, text)

    def worker():
        try:
            python = ensure_runtime(update)
            update("运行环境就绪，正在加载行业数据…")
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            subprocess.Popen([str(python), "-m", "desktop.main"], cwd=str(APP_DIR), env=env,
                             creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
            root.after(350, root.destroy)
        except Exception as exc:
            def fail():
                bar.stop()
                status.set("启动失败")
                messagebox.showerror("IntDog 启动失败",
                    f"{type(exc).__name__}: {exc}\n\n详细日志：{LOG_FILE}")
            root.after(0, fail)

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只输出运行环境状态")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(runtime_state(), ensure_ascii=False))
        return 0
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
