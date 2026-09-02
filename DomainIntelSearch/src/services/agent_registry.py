"""Conservative Agent discovery and bounded, redaction-safe diagnosis."""

from __future__ import annotations

import hashlib
import os
import re
import signal
import shutil
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

from .capability_manifest import AGENT_SPECS, capability_or_unknown

AGENTS = AGENT_SPECS  # compatibility alias
MAX_DIAGNOSTIC_OUTPUT_BYTES = 16 * 1024
MAX_EXECUTABLE_FINGERPRINT_BYTES = 512 * 1024 * 1024
MAX_CONCURRENT_DIAGNOSES = 4
_DIAGNOSIS_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_DIAGNOSES)
COMMAND = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
DIAGNOSTIC_ENV_ALLOWLIST = frozenset({
    "APPDATA", "CLAUDE_CONFIG_DIR", "CODEX_HOME", "COMSPEC", "HOME", "LANG",
    "LC_ALL", "LC_CTYPE", "LOCALAPPDATA", "PATH", "PATHEXT", "PROGRAMDATA",
    "SYSTEMROOT", "TEMP", "TERM", "TMP", "TMPDIR", "USERPROFILE", "WINDIR",
    "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
})


@dataclass(frozen=True)
class _Probe:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    oversized: bool = False


class ExecutableBindingError(RuntimeError):
    """The executable changed after diagnosis and must be diagnosed again."""


class ExecutableFingerprintError(RuntimeError):
    def __init__(self, code: str, detail: str, *, status: str = "invalid_configuration"):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def _safe_diagnostic_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if key.upper() in DIAGNOSTIC_ENV_ALLOWLIST}


def _drain(stream: BinaryIO, sink: bytearray, budget: list[int], lock: threading.Lock,
           oversized: threading.Event) -> None:
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            with lock:
                remaining = max(0, MAX_DIAGNOSTIC_OUTPUT_BYTES - budget[0])
                if remaining:
                    accepted = chunk[:remaining]
                    sink.extend(accepted)
                    budget[0] += len(accepted)
                if len(chunk) > remaining:
                    oversized.set()
    finally:
        stream.close()


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, shell=False, timeout=5, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            pass
        if process.poll() is None:
            process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        process.kill()


def _run_bounded_argv(argv: list[str], *, timeout_seconds: float) -> _Probe:
    """Run an argv-only public probe with bounded retained output."""
    windows_flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0) |
                     getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    process = subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=False, env=_safe_diagnostic_env(),
        creationflags=(windows_flags if os.name == "nt" else 0),
        start_new_session=os.name != "nt",
    )
    stdout = bytearray()
    stderr = bytearray()
    budget = [0]
    lock = threading.Lock()
    oversized = threading.Event()
    readers = [
        threading.Thread(target=_drain, args=(process.stdout, stdout, budget, lock, oversized),
                         name="intdog-diagnostic-stdout"),
        threading.Thread(target=_drain, args=(process.stderr, stderr, budget, lock, oversized),
                         name="intdog-diagnostic-stderr"),
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=max(0.01, float(timeout_seconds)))
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        process.wait(timeout=2)
    for reader in readers:
        reader.join(timeout=2)
    for stream, reader in zip((process.stdout, process.stderr), readers):
        if reader.is_alive():
            stream.close()
            reader.join(timeout=1)
        if reader.is_alive():
            raise RuntimeError("diagnostic pipe reader did not terminate")
    return _Probe(process.returncode, bytes(stdout), bytes(stderr), timed_out, oversized.is_set())


def _which(command: str, path: str | None) -> str:
    if path is None:
        return shutil.which(command) or ""
    try:
        return shutil.which(command, path=path) or ""
    except TypeError:
        # Preserve compatibility with simple test/platform shims that expose
        # the historic one-argument signature.
        return shutil.which(command) or ""


def _selected_file(raw: str) -> Path | None:
    if not raw or "\x00" in raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute() or not candidate.is_file():
        return None
    return candidate


def default_agent_search_path(environment: dict[str, str] | None = None,
                              *, platform: str | None = None) -> str:
    """Return a bounded same-OS search path for GUI-launched desktop builds.

    Desktop applications do not reliably inherit terminal profile PATH changes.
    Add only conventional executable directories; never traverse a home folder.
    """
    env = environment if environment is not None else dict(os.environ)
    target = platform or sys.platform
    separator = ";" if target == "win32" else os.pathsep
    values = [item for item in str(env.get("PATH") or "").split(separator) if item]
    home = Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())
    if target == "win32":
        appdata = env.get("APPDATA")
        local = env.get("LOCALAPPDATA")
        candidates = [
            Path(appdata) / "npm" if appdata else None,
            Path(local) / "Microsoft" / "WindowsApps" if local else None,
            home / ".local" / "share" / "pnpm",
            home / ".bun" / "bin",
            home / ".codex" / "bin",
        ]
    else:
        candidates = [
            home / ".local" / "bin", home / ".local" / "share" / "pnpm",
            home / ".npm-global" / "bin", home / ".bun" / "bin",
            Path("/opt/homebrew/bin"), Path("/usr/local/bin"),
        ]
    seen = {os.path.normcase(os.path.normpath(item)) for item in values}
    for candidate in candidates:
        if candidate is None:
            continue
        value = str(candidate)
        identity = os.path.normcase(os.path.normpath(value))
        if identity not in seen:
            values.append(value)
            seen.add(identity)
    return separator.join(values)


def discover_local_agents(*, path: str, selected_executables: list[str]) -> list[dict]:
    """Check only a supplied PATH and explicit user-selected executable files."""
    selected: dict[str, str] = {}
    command_to_id = {
        _command_identity(command): spec.id
        for spec in AGENT_SPECS for command in spec.commands
    }
    unknown_selected: list[tuple[str, str]] = []
    for raw in selected_executables:
        candidate = _selected_file(raw)
        if candidate is None:
            continue
        basename = _command_identity(candidate.name)
        item_id = command_to_id.get(basename)
        if item_id:
            selected.setdefault(item_id, str(candidate))
        else:
            unknown_selected.append((f"selected-{len(unknown_selected) + 1}", str(candidate)))

    rows = []
    for spec in AGENT_SPECS:
        executable = selected.get(spec.id, "")
        if not executable:
            for command in spec.commands:
                executable = _which(command, path)
                if executable:
                    break
        installed = bool(executable)
        rows.append({
            **spec.public(), "installed": installed, "authenticated": None,
            "version_verified": False, "ready": False, "executable": executable,
            "status": "detected" if installed else "missing",
            "failure_code": None if installed else "executable_missing",
            "version": "",
            "detail": ("Detected; run diagnosis before direct execution" if installed
                       else "CLI was not found in the supplied PATH or selected files"),
        })
    for item_id, executable in unknown_selected:
        spec = capability_or_unknown(item_id)
        rows.append({
            **spec.public(), "installed": True, "authenticated": None,
            "version_verified": False, "ready": False, "executable": executable,
            "status": "import_only", "failure_code": "unknown_agent",
            "version": "", "detail": "Unknown executable; result import only",
        })
    return rows


def _base_result(item_id: str) -> dict:
    spec = capability_or_unknown(item_id)
    return {
        "id": spec.id, "connection": spec.connection,
        "execution_level": spec.execution_level, "installed": False,
        "version_verified": False, "authenticated": None, "ready": False,
        "status": "missing", "failure_code": "executable_missing",
        "executable": "", "version": "", "detail": "Executable is missing",
    }


def _diagnose_api(profile: dict, item_id: str) -> dict:
    spec = capability_or_unknown(item_id)
    result = _base_result(item_id)
    result.update(installed=True, status="not_configured", failure_code="missing_configuration",
                  detail="API configuration is incomplete")
    if spec.execution_level != "direct":
        result.update(status="import_only", failure_code="direct_adapter_unavailable",
                      detail="No verified direct API adapter is available")
        return result
    base = str(profile.get("api_base") or spec.default_api_base or "").strip().rstrip("/")
    model = str(profile.get("model") or spec.default_model or "").strip()
    auth_type = str(profile.get("auth_type") or
                    ("" if spec.auth == "explicit" else spec.auth)).strip().lower()
    if not base:
        result.update(failure_code="missing_api_base", detail="An explicit API base is required")
        return result
    parsed = urlsplit(base)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        result.update(status="invalid_configuration", failure_code="invalid_api_base",
                      detail="Remote API bases must use HTTPS")
        return result
    if auth_type not in {"bearer", "api_key_header"}:
        result.update(status="invalid_configuration", failure_code="invalid_auth_type",
                      detail="Authentication type must be bearer or api_key_header")
        return result
    if spec.auth != "explicit" and auth_type != spec.auth:
        result.update(status="invalid_configuration", failure_code="invalid_auth_type",
                      detail=f"{spec.id} requires the manifest authentication type {spec.auth}")
        return result
    if not model:
        result.update(failure_code="missing_model", detail="An explicit model is required")
        return result
    if not bool(profile.get("credential_configured")):
        result.update(failure_code="missing_credential", detail="A credential is not configured")
        return result
    result.update(ready=True, status="ready", failure_code=None,
                  authenticated=True, detail="Explicit API configuration is ready")
    return result


def _profile_executable(profile: dict, spec) -> tuple[str, str | None]:
    if "executable" in profile:
        return str(profile.get("executable") or ""), None
    if profile.get("executable_path"):
        return str(profile["executable_path"]), None
    command = str(profile.get("command") or (spec.commands[0] if spec.commands else ""))
    if not COMMAND.fullmatch(command):
        return "", "invalid_executable"
    return _which(command, os.environ.get("PATH", "")), None


def _command_identity(value: str) -> str:
    """Return a platform-neutral executable basename for allowlist checks."""
    basename = re.split(r"[/\\]", str(value or ""))[-1].casefold()
    for suffix in (".exe", ".cmd", ".bat"):
        if basename.endswith(suffix):
            return basename[:-len(suffix)]
    return basename


def executable_fingerprint(executable: str, *, deadline: float | None = None) -> dict:
    """Capture a canonical identity; this narrows, not eliminates, local races."""
    def check_deadline() -> None:
        if deadline is not None and time.monotonic() >= deadline:
            raise ExecutableFingerprintError(
                "fingerprint_timeout", "Executable fingerprint exceeded diagnosis timeout",
                status="timeout")

    check_deadline()
    source = Path(executable)
    if not source.is_absolute():
        resolved_command = _which(executable, os.environ.get("PATH", ""))
        if not resolved_command:
            raise FileNotFoundError(executable)
        source = Path(resolved_command)
    source = Path(os.path.abspath(source))
    canonical = source.resolve(strict=True)
    metadata = canonical.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ExecutableFingerprintError(
            "executable_not_regular", "Selected executable is not a regular file")
    if metadata.st_size > MAX_EXECUTABLE_FINGERPRINT_BYTES:
        raise ExecutableFingerprintError(
            "executable_too_large", "Selected executable exceeds the 512 MiB fingerprint limit")
    check_deadline()
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(canonical, flags)
    except OSError as exc:
        raise ExecutableFingerprintError(
            "executable_unreadable", "Selected executable cannot be read") from exc
    digest = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ExecutableFingerprintError(
                "executable_not_regular", "Selected executable is not a regular file")
        if opened.st_size > MAX_EXECUTABLE_FINGERPRINT_BYTES:
            raise ExecutableFingerprintError(
                "executable_too_large",
                "Selected executable exceeds the 512 MiB fingerprint limit")
        if ((opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)):
            raise ExecutableFingerprintError(
                "executable_changed", "Selected executable changed during fingerprinting")
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            while True:
                check_deadline()
                chunk = handle.read(256 * 1024)
                check_deadline()
                if not chunk:
                    break
                digest.update(chunk)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return {
        "source_path": str(source), "canonical_path": str(canonical),
        "device": int(opened.st_dev), "inode": int(opened.st_ino),
        "size": int(opened.st_size), "mtime_ns": int(opened.st_mtime_ns),
        "sha256": digest.hexdigest(),
    }


def validate_executable_binding(binding: dict) -> str:
    """Revalidate a diagnosed executable immediately before execution.

    This detects ordinary path, symlink, and file replacement. It cannot claim
    absolute protection against a same-account nanosecond TOCTOU race.
    """
    expected = binding.get("executable_fingerprint") or binding
    if not isinstance(expected, dict):
        raise ExecutableBindingError("Executable diagnosis is missing")
    try:
        current = executable_fingerprint(
            str(expected.get("source_path") or ""), deadline=time.monotonic() + 10)
    except (OSError, ValueError, ExecutableFingerprintError) as exc:
        raise ExecutableBindingError(
            "Diagnosed executable is unavailable; re-diagnose the provider") from exc
    compared = ("canonical_path", "device", "inode", "size", "mtime_ns", "sha256")
    if any(current.get(key) != expected.get(key) for key in compared):
        raise ExecutableBindingError(
            "Diagnosed executable changed; re-diagnose the provider")
    return str(current["canonical_path"])


def _diagnose_agent_unlocked(profile: dict, *, timeout_seconds: int = 10) -> dict:
    """Diagnose a capability without reading or returning credential contents."""
    deadline = time.monotonic() + max(0.01, float(timeout_seconds))
    raw_id = str(profile.get("capability_id") or profile.get("id") or "unknown").strip().lower()
    spec = capability_or_unknown(raw_id)
    if spec.execution_level == "import_only" and profile.get("command"):
        command = str(profile.get("command") or "").casefold().removesuffix(".exe")
        matched = next((item for item in AGENT_SPECS
                        if command in {value.casefold().removesuffix('.exe')
                                       for value in item.commands}), None)
        if matched is not None:
            spec = matched
            raw_id = matched.id
    if spec.connection == "api":
        return _diagnose_api(profile, raw_id)
    result = _base_result(raw_id)
    if spec.connection == "mcp":
        result.update(installed=True, ready=True, status="handoff", failure_code=None,
                      detail="MCP handoff is available")
        return result
    if spec.connection == "taskpack":
        result.update(installed=True, ready=True, status="import_only", failure_code=None,
                      detail="Task-package export and result import are available")
        return result

    executable, invalid = _profile_executable(profile, spec)
    if invalid:
        result.update(status="invalid_configuration", failure_code=invalid,
                      detail="Executable must be a command name or an explicit absolute file")
        return result
    if not executable:
        return result
    candidate = Path(executable)
    if (candidate.is_absolute() and not candidate.exists()) or "\x00" in executable:
        if "\x00" in executable or not COMMAND.fullmatch(executable):
            result.update(status="invalid_configuration", failure_code="invalid_executable",
                          detail="Selected executable is invalid")
        return result
    if not candidate.is_absolute() and not COMMAND.fullmatch(executable):
        result.update(status="invalid_configuration", failure_code="invalid_executable",
                      detail="Executable contains unsupported characters")
        return result

    if spec.execution_level == "direct" or spec.native_session_implemented:
        allowed = {_command_identity(command) for command in spec.commands}
        declared = str(profile.get("command") or "")
        identities = [_command_identity(executable)]
        if declared:
            identities.append(_command_identity(declared))
        if not allowed or any(identity not in allowed for identity in identities):
            result.update(
                connection="restricted_cli", execution_level="import_only",
                installed=True, executable=executable, status="invalid_configuration",
                failure_code="capability_command_mismatch",
                detail="Executable is not allowlisted for the declared direct capability",
            )
            return result
    try:
        fingerprint = executable_fingerprint(executable, deadline=deadline)
    except ExecutableFingerprintError as exc:
        result.update(status=exc.status, failure_code=exc.code, detail=exc.detail)
        return result
    except OSError:
        result.update(status="missing", failure_code="executable_missing",
                      detail="Executable disappeared before diagnosis")
        return result
    executable = str(fingerprint["canonical_path"])
    result.update(installed=True, executable=executable,
                  resolved_executable=executable,
                  executable_fingerprint=fingerprint, status="detected",
                  failure_code=None, detail="Executable detected")

    if spec.execution_level != "direct" and not spec.native_session_implemented:
        result.update(ready=spec.execution_level == "handoff",
                      status=spec.execution_level, detail=(
                          "Detected restricted CLI; use handoff" if spec.execution_level == "handoff"
                          else "Unknown CLI; result import only"))
        return result

    try:
        version_probe = _run_bounded_argv(
            [executable, *spec.version_args],
            timeout_seconds=max(0.01, deadline - time.monotonic()))
    except OSError as exc:
        result.update(installed=False, status="missing", failure_code="probe_start_failed",
                      detail=f"Version probe failed to start: {type(exc).__name__}")
        return result
    if version_probe.timed_out:
        result.update(status="timeout", failure_code="probe_timeout",
                      detail="Version probe timed out")
        return result
    if version_probe.oversized:
        result.update(status="output_limit", failure_code="probe_output_limit",
                      detail="Version probe exceeded the output budget")
        return result
    version_text = (version_probe.stdout + b"\n" + version_probe.stderr).decode(
        "utf-8", errors="replace")
    match = (re.search(spec.version_pattern, version_text) if spec.version_pattern
             else re.search(r"(?im)^\s*[^\r\n]{1,120}$", version_text))
    if version_probe.returncode != 0 or match is None:
        result.update(status="incompatible", failure_code="unrecognized_version",
                      detail="Executable did not return a recognized version")
        return result
    result.update(version_verified=True, version=match.group(0)[:120])

    if spec.native_session_implemented and spec.execution_level != "direct":
        result.update(ready=True, status="ready", failure_code=None,
                      detail="Native session command verified; authentication is checked by its protocol handshake")
        return result
    if not spec.auth_args:
        result.update(ready=True, status="ready", failure_code=None,
                      detail="Verified direct CLI is ready")
        return result
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        result.update(authenticated=False, status="timeout", failure_code="probe_timeout",
                      detail="Diagnosis time budget was exhausted before authentication")
        return result
    try:
        auth_probe = _run_bounded_argv(
            [executable, *spec.auth_args], timeout_seconds=remaining)
    except OSError as exc:
        result.update(authenticated=False, status="auth_failed",
                      failure_code="auth_probe_start_failed",
                      detail=f"Authentication probe failed to start: {type(exc).__name__}")
        return result
    if auth_probe.timed_out:
        result.update(authenticated=False, status="timeout", failure_code="probe_timeout",
                      detail="Authentication probe timed out")
        return result
    if auth_probe.oversized:
        result.update(authenticated=False, status="output_limit",
                      failure_code="probe_output_limit",
                      detail="Authentication probe exceeded the output budget")
        return result
    authenticated = auth_probe.returncode == 0
    result.update(authenticated=authenticated, ready=authenticated,
                  status="ready" if authenticated else "auth_failed",
                  failure_code=None if authenticated else "authentication_failed",
                  detail=("Authenticated native CLI is ready" if authenticated
                          else "Public authentication status check failed"))
    return result


def diagnose_agent(profile: dict, *, timeout_seconds: int = 10) -> dict:
    """Bounded diagnosis with a typed capacity failure and no queued probes."""
    raw_id = str(profile.get("capability_id") or profile.get("id") or
                 "unknown").strip().lower()
    if not _DIAGNOSIS_SLOTS.acquire(blocking=False):
        result = _base_result(raw_id)
        result.update(status="busy", failure_code="diagnosis_busy",
                      detail="Diagnostic capacity is busy; retry later")
        return result
    try:
        return _diagnose_agent_unlocked(profile, timeout_seconds=timeout_seconds)
    finally:
        _DIAGNOSIS_SLOTS.release()


def discover_agents(*, check_auth: bool = True) -> list[dict]:
    """Compatibility setup view backed by conservative discovery."""
    rows = discover_local_agents(
        path=default_agent_search_path(), selected_executables=[])
    for row in rows:
        spec = capability_or_unknown(row["id"])
        if not row["installed"]:
            row["detail"] = "未在 PATH 中检测到公开 CLI"
        elif (spec.connection == "native_cli" and
              spec.execution_level == "direct" and check_auth):
            diagnosed = diagnose_agent({"id": spec.id, "executable": row["executable"]})
            for key in ("installed", "authenticated", "version_verified", "ready",
                        "executable", "status", "failure_code", "version", "detail"):
                row[key] = diagnosed[key]
        elif spec.execution_level == "handoff":
            row["ready"] = True
            row["detail"] = "已检测；通过 IntDog MCP 或任务包交接"
        else:
            row["detail"] = "已检测；等待公开登录状态检查"
    return rows
