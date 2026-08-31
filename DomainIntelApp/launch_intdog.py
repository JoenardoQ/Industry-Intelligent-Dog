"""One-click bootstrapper: show loading UI, create runtime, then launch IntDog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
SEARCH_DIR = PROJECT_DIR / "DomainIntelSearch"
RUNTIME_DIR = PROJECT_DIR / ".intdog-runtime"
RUNTIME_KIND = (("windows" if os.name == "nt" else "linux") +
                f"-py{sys.version_info.major}{sys.version_info.minor}")
VENV_DIR = RUNTIME_DIR / f"venv-{RUNTIME_KIND}"
MARKER = RUNTIME_DIR / f"environment-{RUNTIME_KIND}.json"
LOG_FILE = RUNTIME_DIR / "install.log"
APP_LOG_FILE = RUNTIME_DIR / "app.log"
DATA_DIR = PROJECT_DIR / "DomainIntelData"
WEB_DIR = PROJECT_DIR / "DomainIntelWeb"
WEB_MARKER = RUNTIME_DIR / "web-environment.json"
INSTANCE_LOCK = RUNTIME_DIR / "desktop.lock"


def _venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _fingerprint() -> str:
    digest = hashlib.sha256()
    paths = [SEARCH_DIR / "pyproject.toml", WEB_DIR / "package-lock.json",
             WEB_DIR / "vite.config.ts", WEB_DIR / "index.html"]
    paths.extend(sorted((WEB_DIR / "src").glob("**/*")))
    for source in paths:
        if source.is_file():
            digest.update(source.relative_to(PROJECT_DIR).as_posix().encode())
            digest.update(source.read_bytes())
    return digest.hexdigest()[:16]


def _package_fingerprint() -> str:
    lock = WEB_DIR / "package-lock.json"
    return hashlib.sha256(lock.read_bytes()).hexdigest()[:16] if lock.exists() else "missing"


def _editable_install_command(python: Path) -> list[str]:
    """Install the local backend when the isolated runtime is genuinely absent."""
    return [str(python), "-m", "pip", "install", "--disable-pip-version-check",
            "-e", str(SEARCH_DIR)]


def _python_runtime_ready(python: Path) -> bool:
    """Check the installed distribution and imports without relying on repo cwd."""
    probe = (
        "from importlib.metadata import distribution;"
        "distribution('intdog-domain-intelligence');"
        "import requests,feedparser,yaml,dateutil,fastapi,uvicorn"
    )
    try:
        completed = subprocess.run(
            [str(python), "-c", probe], cwd=str(RUNTIME_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
        return completed.returncode == 0
    except OSError:
        return False


def ensure_web_runtime(update, log, flags) -> None:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    marker = {}
    try:
        marker = json.loads(WEB_MARKER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    if (not (WEB_DIR / "node_modules").is_dir()
            or marker.get("package_fingerprint") != _package_fingerprint()):
        update("正在安装 Web 工作台组件…")
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=str(WEB_DIR),
                       stdout=log, stderr=subprocess.STDOUT, check=True,
                       creationflags=flags)
    update("正在构建专业研究工作台…")
    subprocess.run([npm, "run", "build"], cwd=str(WEB_DIR), stdout=log,
                   stderr=subprocess.STDOUT, check=True, creationflags=flags)
    WEB_MARKER.write_text(json.dumps({
        "package_fingerprint": _package_fingerprint(), "built_at": time.time()}, indent=2),
        encoding="utf-8")


def runtime_state() -> dict:
    marker = {}
    try:
        marker = json.loads(MARKER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    ready = (_venv_python().exists()
             and (WEB_DIR / "dist" / "index.html").is_file()
             and marker.get("fingerprint") == _fingerprint()
             and marker.get("project_root") == str(PROJECT_DIR)
             and marker.get("platform") == platform.system())
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
            update("正在校验 IntDog 运行组件…")
            if not _python_runtime_ready(python):
                update("首次运行：正在安装 IntDog 运行组件…")
                subprocess.run(_editable_install_command(python), stdout=log,
                               stderr=subprocess.STDOUT, check=True,
                                creationflags=flags)
            ensure_web_runtime(update, log, flags)
            MARKER.write_text(json.dumps({"fingerprint": _fingerprint(),
                                          "python": str(python),
                                          "project_root": str(PROJECT_DIR),
                                          "data_root": str(DATA_DIR),
                                          "platform": platform.system()}, indent=2),
                              encoding="utf-8")
    return python


def _port_ready(port: int = 8765) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _windows_browser_candidates() -> tuple[str, ...]:
    """Ordered app-mode browser fallbacks used by the Windows/WSL launcher."""
    return (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    )


def _windows_app_mode_script(url: str, session_token: str = "") -> str:
    candidates = ",".join(f"'{path}'" for path in _windows_browser_candidates())
    # A shared Chrome profile may already be owned by a background browser
    # process. In that case Start-Process returns a short-lived broker process,
    # WaitForExit completes immediately, and the launcher shuts the API down
    # before the app window has loaded. Give each desktop session an isolated
    # disposable profile so the process we wait for owns the app window.
    profile_id = hashlib.sha256(session_token.encode("utf-8")).hexdigest()[:16]
    return (
        f"$browsers=@({candidates});"
        "$browser=$browsers|Where-Object{Test-Path $_}|Select-Object -First 1;"
        "if(!$browser){throw 'Chrome or Edge is required to open IntDog'};"
        "$sessionRoot=Join-Path ([System.IO.Path]::GetTempPath()) 'IntDog\\Sessions';"
        f"$profile=Join-Path $sessionRoot '{profile_id}';"
        "New-Item -ItemType Directory -Force -Path $profile|Out-Null;"
        f"$browserArgs=@('--user-data-dir='+$profile,'--app={url}#session={session_token}','--no-first-run',"
        "'--disable-background-mode','--disable-features=Translate');"
        "try{"
        "Write-Output ('[browser] executable='+$browser);"
        "$p=Start-Process -FilePath $browser -ArgumentList $browserArgs -PassThru;"
        "Write-Output ('[browser] started pid='+$p.Id+' exited='+$p.HasExited);"
        "$p.WaitForExit();"
        "Write-Output ('[browser] exited pid='+$p.Id+' code='+$p.ExitCode);"
        "}finally{"
        f"try{{Invoke-WebRequest -UseBasicParsing -Method Post -Uri '{url}/api/shutdown' "
        f"-Headers @{{'X-IntDog-Session'='{session_token}'}}"
        "|Out-Null}catch{};"
        "Remove-Item -LiteralPath $profile -Recurse -Force -ErrorAction SilentlyContinue;"
        "}"
    )


def _open_workbench_when_ready(session_token: str = "") -> bool:
    for _ in range(80):
        if _port_ready():
            url = "http://127.0.0.1:8765"
            if "microsoft" in platform.release().lower():
                with APP_LOG_FILE.open("a", encoding="utf-8") as browser_log:
                    browser_log.write("[launcher] 正在打开 Windows 应用窗口…\n")
                    completed = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-Command",
                         _windows_app_mode_script(url, session_token)],
                        stdout=browser_log, stderr=subprocess.STDOUT)
                    if completed.returncode:
                        browser_log.write(
                            f"[launcher] Windows 浏览器启动失败 ({completed.returncode})\n")
                    return completed.returncode == 0
            else:
                return bool(webbrowser.open(f"{url}#session={session_token}"))
        time.sleep(0.25)
    return False


def launch() -> int:
    fontconfig = APP_DIR / "app" / "fontconfig-wsl.conf"
    if os.name != "nt" and fontconfig.exists() and Path("/mnt/c/Windows/Fonts").is_dir():
        os.environ.setdefault("FONTCONFIG_FILE", str(fontconfig))
    from runtime.dpi import apply_tk_scaling, enable_high_dpi
    from runtime.fonts import UI_FONT
    from runtime.single_instance import SingleInstanceLock

    instance = SingleInstanceLock(INSTANCE_LOCK)
    if not instance.acquire():
        # The first desktop session owns both the service and its app window.
        # A second shortcut invocation must not create another service/window.
        return 0

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
             font=(UI_FONT, 21, "bold")).pack(anchor="w", padx=26, pady=(30, 2))
    tk.Label(card, text="Industry Intelligence Workspace", bg="#FFFFFF", fg="#7A858B",
             font=(UI_FONT, 9)).pack(anchor="w", padx=26)
    status = tk.StringVar(value="正在检查运行环境…")
    tk.Label(card, textvariable=status, bg="#FFFFFF", fg="#607D8B",
             font=(UI_FONT, 10)).pack(anchor="w", padx=26, pady=(24, 10))
    bar = ttk.Progressbar(card, mode="indeterminate")
    bar.pack(fill="x", padx=26); bar.start(10)
    launch_state = {"python": None, "failed": False}

    def update(text):
        root.after(0, status.set, text)

    def worker():
        try:
            python = ensure_runtime(update)
            update("运行环境就绪，正在加载行业数据…")
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            # The one-click production launcher always owns its adjacent data
            # directory. CLI users can still override the root explicitly.
            env["DOMAIN_INTEL_DATA_ROOT"] = str(DATA_DIR)
            env["INTDOG_PROJECT_ROOT"] = str(PROJECT_DIR)
            launch_state["python"] = python
            root.after(350, root.destroy)
        except Exception as exc:
            launch_state["failed"] = True
            def fail():
                bar.stop()
                status.set("启动失败")
                messagebox.showerror("IntDog 启动失败",
                    f"{type(exc).__name__}: {exc}\n\n详细日志：{LOG_FILE}")
            root.after(0, fail)

    threading.Thread(target=worker, daemon=True).start()
    try:
        root.mainloop()
        python = launch_state["python"]
        if python is None:
            return 1 if launch_state["failed"] else 0
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["DOMAIN_INTEL_DATA_ROOT"] = str(DATA_DIR)
        env["INTDOG_PROJECT_ROOT"] = str(PROJECT_DIR)
        session_token = secrets.token_urlsafe(32)
        env["INTDOG_SESSION_TOKEN"] = session_token
        env["INTDOG_DISABLE_EMAIL"] = "1"
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        with APP_LOG_FILE.open("a", encoding="utf-8") as log:
            log.write("\n=== IntDog desktop session ===\n")
            log.flush()
            command = [str(python), "-m", "DomainIntelWeb.api"]
            cwd = PROJECT_DIR
            server = subprocess.Popen(
                command, cwd=str(cwd), env=env,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
            browser_ok = _open_workbench_when_ready(session_token)
            if not browser_ok and server.poll() is None:
                server.terminate()
            if "microsoft" in platform.release().lower() and server.poll() is None:
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.terminate()
            return server.wait()
    finally:
        instance.release()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只输出运行环境状态")
    parser.add_argument("--prepare", action="store_true", help="准备运行环境后退出")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(runtime_state(), ensure_ascii=False))
        return 0
    if args.prepare:
        ensure_runtime(print)
        print(json.dumps(runtime_state(), ensure_ascii=False))
        return 0
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
