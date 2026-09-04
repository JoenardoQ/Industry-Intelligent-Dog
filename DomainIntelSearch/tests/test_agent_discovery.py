from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.services import agent_registry
from src.services.provider_readiness import provider_readiness
from src.services import agent_connection
from src.services.agent_connection import probe_agent_connection
from src.services.agent_sessions import AgentSessionError
from src.services.capability_manifest import AgentCapability
from src.services.claude_cli_service import ClaudeCLIError, ClaudeCLIService


def _executable(directory: Path, name: str, body: str) -> Path:
    if os.name == "nt":
        pytest.skip("synthetic shebang executables are POSIX-only")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    target.chmod(0o755)
    return target


def test_discovery_checks_only_supplied_path_and_user_selected_files(tmp_path, monkeypatch):
    path_dir = tmp_path / "public-bin"
    codex = _executable(path_dir, "codex", "print('codex-cli 1.2.3')\n")
    selected_dir = tmp_path / "Program Files" / "Claude"
    claude = _executable(selected_dir, "claude", "print('Claude Code 2.0.0')\n")
    private_dir = tmp_path / "Documents" / "private"
    _executable(private_dir, "workbuddy", "raise SystemExit('must not run')\n")

    def forbidden_walk(*_args, **_kwargs):
        raise AssertionError("discovery must not traverse user directories")

    monkeypatch.setattr(os, "walk", forbidden_walk)
    rows = agent_registry.discover_local_agents(
        path=str(path_dir), selected_executables=[str(claude)])
    by_id = {row["id"]: row for row in rows}
    assert by_id["codex"]["executable"] == str(codex)
    assert by_id["claude"]["executable"] == str(claude)
    assert by_id["codex"]["execution_level"] == "direct"
    assert by_id["codex"]["ready"] is False
    assert by_id["workbuddy"]["installed"] is False


def test_user_selected_windows_command_shim_is_recognized_as_known_agent(tmp_path):
    shim = tmp_path / "codex.cmd"
    shim.write_text("@echo off\r\n", encoding="utf-8")

    rows = agent_registry.discover_local_agents(
        path="", selected_executables=[str(shim.resolve())])

    codex = next(row for row in rows if row["id"] == "codex")
    assert codex["installed"] is True
    assert codex["executable"] == str(shim.resolve())
    assert not any(row["id"].startswith("selected-") for row in rows)


def test_default_search_path_adds_only_known_same_os_install_locations(tmp_path):
    appdata = tmp_path / "AppData" / "Roaming"
    local = tmp_path / "AppData" / "Local"
    environment = {
        "PATH": r"C:\\Windows\\System32",
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(local),
        "USERPROFILE": str(tmp_path),
    }

    value = agent_registry.default_agent_search_path(environment, platform="win32")
    parts = value.split(";")

    assert parts[0] == environment["PATH"]
    assert str(appdata / "npm") in parts
    assert str(tmp_path / ".local" / "bin") not in parts


def test_provider_readiness_uses_saved_verified_executable_binding(tmp_path, monkeypatch):
    executable = _executable(
        tmp_path / "tools", "codex",
        "import sys\n"
        "print('codex-cli 1.2.3' if '--version' in sys.argv else 'Logged in')\n",
    )
    settings = tmp_path / "_settings"
    settings.mkdir()
    (settings / "agent_profiles.json").write_text(
        '[{"id":"binding-codex","name":"Codex CLI","command":"codex",'
        f'"args":[],"executable_path":"{executable}","capability_id":"codex"}}]',
        encoding="utf-8",
    )
    monkeypatch.setenv("DOMAIN_INTEL_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    result = provider_readiness("codex", tmp_path / "AI")

    assert result["ready"] is True
    assert result["resolved_executable"] == str(executable.resolve())


def test_connection_probe_requires_a_real_noninteractive_agent_response(tmp_path):
    executable = _executable(
        tmp_path / "tools", "claude",
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('Claude Code 2.1.4')\n"
        "elif sys.argv[1:3] == ['auth', 'status']:\n"
        "    print('authenticated')\n"
        "else:\n"
        "    sys.stdin.read()\n"
        "    print('INTDOG_CONNECTION_OK')\n",
    )

    result = probe_agent_connection(
        {"id": "claude", "executable": str(executable)}, tmp_path,
        timeout_seconds=5)

    assert result["ready"] is True
    assert result["status"] == "ready"
    assert result["detail"] == "真实最小调用成功"


def test_connection_probe_rejects_a_response_that_only_echoes_the_marker(tmp_path):
    executable = _executable(
        tmp_path / "tools", "claude",
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('Claude Code 2.1.4')\n"
        "elif sys.argv[1:3] == ['auth', 'status']:\n"
        "    print('authenticated')\n"
        "else:\n"
        "    sys.stdin.read()\n"
        "    print('The requested marker was INTDOG_CONNECTION_OK')\n",
    )

    result = probe_agent_connection(
        {"id": "claude", "executable": str(executable)}, tmp_path,
        timeout_seconds=5)

    assert result["ready"] is False
    assert result["status"] == "unexpected_response"


def test_codex_probe_prefers_app_server_and_reports_effective_protocol(
        tmp_path, monkeypatch):
    class NativeCodex:
        def __init__(self, executable, workspace, timeout):
            self.closed = False

        def start(self):
            return None

        def start_thread(self):
            return "thread-probe"

        def start_turn(self, thread_id, prompt):
            return {"events": [{
                "method": "item/agentMessage/delta",
                "params": {"delta": "INTDOG_CONNECTION_OK"},
            }]}

        def close(self):
            self.closed = True

    monkeypatch.setattr(agent_connection, "diagnose_agent", lambda *_args, **_kwargs: {
        "id": "codex", "ready": True, "resolved_executable": "/tools/codex",
    })
    monkeypatch.setattr(agent_connection, "CodexAppServerSession", NativeCodex,
                        raising=False)

    result = probe_agent_connection(
        {"id": "codex", "executable": "/tools/codex"}, tmp_path,
        timeout_seconds=5)

    assert result["ready"] is True
    assert result["connection"] == "codex_app_server"
    assert result["detail"] == "Codex App Server 真实最小调用成功"


def test_codex_probe_falls_back_to_same_cli_when_app_server_fails(
        tmp_path, monkeypatch):
    class BrokenNativeCodex:
        def __init__(self, executable, workspace, timeout):
            pass

        def start(self):
            raise AgentSessionError("handshake failed")

        def close(self):
            return None

    class CliCodex:
        def __init__(self, config, workspace, executable_binding):
            pass

        def complete(self, prompt):
            return type("Result", (), {"text": "INTDOG_CONNECTION_OK"})()

    monkeypatch.setattr(agent_connection, "diagnose_agent", lambda *_args, **_kwargs: {
        "id": "codex", "ready": True, "resolved_executable": "/tools/codex",
    })
    monkeypatch.setattr(agent_connection, "CodexAppServerSession",
                        BrokenNativeCodex, raising=False)
    monkeypatch.setattr(
        "src.services.codex_cli_service.CodexCLIService", CliCodex)

    result = probe_agent_connection(
        {"id": "codex", "executable": "/tools/codex"}, tmp_path,
        timeout_seconds=5)

    assert result["ready"] is True
    assert result["connection"] == "cli_fallback"
    assert result["detail"] == (
        "Codex App Server 不可用，已通过同一 Codex CLI 完成真实调用")


def test_missing_native_executable_is_not_ready(tmp_path):
    result = agent_registry.diagnose_agent(
        {"id": "codex", "command": "codex", "executable": ""},
        timeout_seconds=1,
    )
    assert result["installed"] is False
    assert result["ready"] is False
    assert result["status"] == "missing"


def test_fake_version_output_cannot_unlock_direct_execution(tmp_path):
    executable = _executable(
        tmp_path, "codex",
        "import sys\nprint('Definitely Not Codex 9.9')\n",
    )
    result = agent_registry.diagnose_agent(
        {"id": "codex", "executable": str(executable)}, timeout_seconds=1)
    assert result["installed"] is True
    assert result["version_verified"] is False
    assert result["ready"] is False
    assert result["status"] == "incompatible"


def test_legacy_setup_discovery_cannot_bypass_the_version_gate(tmp_path, monkeypatch):
    executable = _executable(
        tmp_path, "codex", "print('Definitely Not Codex 9.9')\n")
    monkeypatch.setenv("PATH", str(tmp_path))
    rows = {row["id"]: row for row in agent_registry.discover_agents(check_auth=True)}
    assert rows["codex"]["installed"] is True
    assert rows["codex"]["ready"] is False
    assert rows["codex"]["status"] == "incompatible"


def test_legacy_discovery_diagnoses_manifest_direct_native_without_id_allowlist(
        tmp_path, monkeypatch):
    executable = _executable(tmp_path, "future-cli", "print('Future CLI 1.0')\n")
    spec = AgentCapability(
        "future_cli", "Future CLI", "agent", "international", "native_cli", "direct",
        "https://example.test", "synthetic manifest adapter", ("future-cli",),
        version_pattern=r"Future CLI 1\.0", auth_args=("auth", "status"),
    )
    seen = []
    monkeypatch.setattr(agent_registry, "AGENT_SPECS", (spec,))
    monkeypatch.setattr(agent_registry, "capability_or_unknown", lambda _item_id: spec)
    monkeypatch.setattr(agent_registry, "diagnose_agent", lambda profile: (
        seen.append(profile["id"]) or {
            "installed": True, "authenticated": True, "version_verified": True,
            "ready": True, "executable": str(executable), "status": "ready",
            "failure_code": None, "version": "Future CLI 1.0", "detail": "ready",
        }))
    monkeypatch.setenv("PATH", str(tmp_path))
    rows = agent_registry.discover_agents(check_auth=True)
    assert seen == ["future_cli"]
    assert rows[0]["ready"] is True


def test_native_cli_diagnosis_accepts_selected_path_with_spaces_and_known_version(tmp_path):
    executable = _executable(
        tmp_path / "Applications With Spaces", "claude",
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('Claude Code 2.1.4')\n"
        "else:\n"
        "    print('authenticated')\n",
    )
    result = agent_registry.diagnose_agent(
        {"id": "claude", "executable": str(executable)}, timeout_seconds=1)
    assert result["installed"] is True
    assert result["version_verified"] is True
    assert result["authenticated"] is True
    assert result["ready"] is True
    assert result["execution_level"] == "direct"
    assert result["resolved_executable"] == str(executable.resolve())
    assert result["executable_fingerprint"]["sha256"]


def test_executable_binding_rejects_symlink_exchange_and_file_replacement(tmp_path):
    first = _executable(
        tmp_path / "versions", "claude-v1",
        "import sys\nprint('Claude Code 2.1.4' if '--version' in sys.argv else 'ok')\n",
    )
    second = _executable(
        tmp_path / "versions", "claude-v2",
        "import sys\nprint('Claude Code 2.1.4' if '--version' in sys.argv else 'other')\n",
    )
    selected = tmp_path / "claude"
    selected.symlink_to(first)
    diagnosis = agent_registry.diagnose_agent(
        {"id": "claude", "executable": str(selected)}, timeout_seconds=1)
    assert diagnosis["ready"] is True
    service = ClaudeCLIService({}, tmp_path, executable_binding=diagnosis)
    selected.unlink()
    selected.symlink_to(second)
    with pytest.raises(agent_registry.ExecutableBindingError):
        agent_registry.validate_executable_binding(diagnosis)
    with pytest.raises(ClaudeCLIError, match="re-diagnose"):
        service.complete("must not execute")

    selected.unlink()
    selected.symlink_to(first)
    diagnosis = agent_registry.diagnose_agent(
        {"id": "claude", "executable": str(selected)}, timeout_seconds=1)
    service = ClaudeCLIService({}, tmp_path, executable_binding=diagnosis)
    first.write_text("#!/usr/bin/env python3\nprint('replaced')\n", encoding="utf-8")
    first.chmod(0o755)
    with pytest.raises(agent_registry.ExecutableBindingError):
        agent_registry.validate_executable_binding(diagnosis)
    with pytest.raises(ClaudeCLIError, match="re-diagnose"):
        service.complete("must not execute")


def test_fingerprint_accepts_large_regular_cli_binaries(tmp_path):
    executable = tmp_path / "codex"
    with executable.open("wb") as handle:
        handle.truncate(64 * 1024 * 1024 + 1)
    executable.chmod(0o755)
    result = agent_registry.executable_fingerprint(
        str(executable), deadline=time.monotonic() + 5)
    assert result["size"] == 64 * 1024 * 1024 + 1
    assert len(result["sha256"]) == 64


def test_fingerprint_deadline_is_checked_before_and_during_read(tmp_path, monkeypatch):
    executable = _executable(tmp_path, "codex", "print('codex-cli 1.2.3')\n")
    with pytest.raises(agent_registry.ExecutableFingerprintError) as caught:
        agent_registry.executable_fingerprint(
            str(executable), deadline=time.monotonic() - 0.001)
    assert caught.value.code == "fingerprint_timeout"
    ticks = iter((0.0, 0.0, 0.0, 2.0))
    monkeypatch.setattr(agent_registry.time, "monotonic", lambda: next(ticks, 2.0))
    with pytest.raises(agent_registry.ExecutableFingerprintError) as caught:
        agent_registry.executable_fingerprint(str(executable), deadline=1.0)
    assert caught.value.code == "fingerprint_timeout"


@pytest.mark.skipif(os.name == "nt", reason="FIFO regression is POSIX-specific")
def test_four_large_or_blocking_files_release_slots_for_normal_diagnosis(tmp_path):
    selected = []
    for index in range(2):
        executable = tmp_path / f"large-{index}" / "codex"
        executable.parent.mkdir()
        with executable.open("wb") as handle:
            handle.truncate(512 * 1024 * 1024 + 1)
        executable.chmod(0o755)
        selected.append(executable)
    for index in range(2):
        executable = tmp_path / f"fifo-{index}" / "codex"
        executable.parent.mkdir()
        os.mkfifo(executable)
        selected.append(executable)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda path: agent_registry.diagnose_agent(
            {"id": "codex", "executable": str(path)}, timeout_seconds=0.2), selected))
    assert {item["failure_code"] for item in results} == {
        "executable_too_large", "executable_not_regular"}

    normal = _executable(
        tmp_path / "normal", "codex",
        "import sys\nprint('codex-cli 1.2.3' if '--version' in sys.argv else 'ok')\n",
    )
    result = agent_registry.diagnose_agent(
        {"id": "codex", "executable": str(normal)}, timeout_seconds=1)
    assert result["ready"] is True


def test_diagnosis_timeout_is_bounded_and_cannot_report_ready(tmp_path):
    executable = _executable(
        tmp_path, "codex",
        "import time\ntime.sleep(2)\nprint('codex-cli 1.2.3')\n",
    )
    result = agent_registry.diagnose_agent(
        {"id": "codex", "executable": str(executable)}, timeout_seconds=0.05)
    assert result["ready"] is False
    assert result["status"] == "timeout"
    assert result["failure_code"] == "probe_timeout"


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group regression")
def test_timeout_kills_descendant_holding_pipes_and_reclaims_threads_and_fds(tmp_path):
    executable = _executable(
        tmp_path, "codex",
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(2)'])\n"
        "time.sleep(2)\n",
    )
    before_threads = threading.active_count()
    fd_root = Path("/proc/self/fd")
    before_fds = len(list(fd_root.iterdir())) if fd_root.is_dir() else 0
    started = time.monotonic()
    for _ in range(3):
        result = agent_registry.diagnose_agent(
            {"id": "codex", "executable": str(executable)}, timeout_seconds=0.03)
        assert result["failure_code"] == "probe_timeout"
    elapsed = time.monotonic() - started
    time.sleep(0.05)
    after_fds = len(list(fd_root.iterdir())) if fd_root.is_dir() else 0
    assert elapsed < 1.5
    assert threading.active_count() <= before_threads
    if before_fds:
        assert after_fds <= before_fds + 1


def test_diagnosis_capacity_returns_typed_busy_without_starting_probe(monkeypatch):
    class Busy:
        def acquire(self, blocking=False):
            assert blocking is False
            return False

        def release(self):
            raise AssertionError("unacquired slot must not be released")

    monkeypatch.setattr(agent_registry, "_DIAGNOSIS_SLOTS", Busy())
    result = agent_registry.diagnose_agent({"id": "codex"})
    assert result["ready"] is False
    assert result["status"] == "busy"
    assert result["failure_code"] == "diagnosis_busy"


def test_timeout_budget_covers_version_and_authentication_together(tmp_path):
    executable = _executable(
        tmp_path, "claude",
        "import sys, time\n"
        "time.sleep(0.08)\n"
        "print('Claude Code 2.1.4' if '--version' in sys.argv else 'authenticated')\n",
    )
    started = time.monotonic()
    result = agent_registry.diagnose_agent(
        {"id": "claude", "executable": str(executable)}, timeout_seconds=0.12)
    elapsed = time.monotonic() - started
    assert result["ready"] is False
    assert result["status"] == "timeout"
    assert elapsed < 0.18


def test_oversized_probe_output_is_discarded_and_cannot_report_ready(tmp_path):
    executable = _executable(
        tmp_path, "codex",
        "print('codex-cli 1.2.3 ' + 'x' * 100000)\n",
    )
    result = agent_registry.diagnose_agent(
        {"id": "codex", "executable": str(executable)}, timeout_seconds=1)
    assert result["ready"] is False
    assert result["status"] == "output_limit"
    assert result["failure_code"] == "probe_output_limit"
    assert len(str(result)) < 4000


def test_shell_metacharacters_are_rejected_without_execution(tmp_path):
    marker = tmp_path / "must-not-exist"
    profile = {
        "id": "codex",
        "command": f"codex;touch {marker}",
        "executable": f"codex;touch {marker}",
    }
    result = agent_registry.diagnose_agent(profile, timeout_seconds=1)
    assert result["ready"] is False
    assert result["status"] == "invalid_configuration"
    assert not marker.exists()


def test_diagnostic_subprocess_does_not_receive_or_disclose_credentials(
    tmp_path, monkeypatch):
    canary = "intdog-secret-canary-93841"
    # The name is deliberately not credential-shaped: diagnosis must use an
    # environment allowlist rather than trusting a denylist of common names.
    monkeypatch.setenv("CUSTOM_SESSION_MATERIAL", canary)
    executable = _executable(
        tmp_path, "codex",
        "import os, sys\n"
        "if '--version' in sys.argv:\n"
        "    print('codex-cli 1.2.3')\n"
        "elif os.environ.get('CUSTOM_SESSION_MATERIAL'):\n"
        "    print(os.environ['CUSTOM_SESSION_MATERIAL'])\n"
        "    raise SystemExit(23)\n"
        "else:\n"
        "    print('logged in')\n",
    )
    result = agent_registry.diagnose_agent(
        {"id": "codex", "executable": str(executable)}, timeout_seconds=1)
    assert result["ready"] is True
    assert canary not in str(result)


def test_unknown_and_restricted_agents_never_become_direct(tmp_path):
    executable = _executable(
        tmp_path, "workbuddy", "print('WorkBuddy 1.0.0')\n")
    restricted = agent_registry.diagnose_agent(
        {"id": "workbuddy", "executable": str(executable)}, timeout_seconds=1)
    unknown = agent_registry.diagnose_agent(
        {"id": "mystery", "executable": str(executable)}, timeout_seconds=1)
    assert restricted["execution_level"] == "handoff"
    assert restricted["ready"] is True
    assert unknown["execution_level"] == "import_only"
    assert unknown["ready"] is False


def test_direct_capability_rejects_spoofing_executable_outside_command_allowlist(tmp_path):
    executable = _executable(
        tmp_path, "eviltool",
        "import sys\n"
        "print('OpenAI Codex v9.9.9' if '--version' in sys.argv else 'Logged in')\n",
    )
    result = agent_registry.diagnose_agent({
        "id": "custom-profile", "capability_id": "codex",
        "command": "eviltool", "executable": str(executable),
    }, timeout_seconds=1)
    assert result["ready"] is False
    assert result["execution_level"] == "import_only"
    assert result["status"] == "invalid_configuration"
    assert result["failure_code"] == "capability_command_mismatch"


def test_api_mcp_and_taskpack_diagnostics_preserve_tier_without_running_a_command():
    api = agent_registry.diagnose_agent({
        "id": "compatible_api",
        "api_base": "https://models.example/v1",
        "auth_type": "bearer",
        "model": "example-model",
        "credential_configured": True,
    })
    mcp = agent_registry.diagnose_agent({"id": "mcp"})
    taskpack = agent_registry.diagnose_agent({"id": "taskpack"})
    assert api["ready"] is True and api["execution_level"] == "direct"
    assert mcp["ready"] is True and mcp["execution_level"] == "handoff"
    assert taskpack["ready"] is True and taskpack["execution_level"] == "import_only"
