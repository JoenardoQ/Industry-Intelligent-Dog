from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.services import agent_registry
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
