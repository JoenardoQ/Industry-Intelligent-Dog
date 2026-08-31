from pathlib import Path

from DomainIntelWeb.api.commands import search_command, search_cwd


def test_source_command_uses_current_python(monkeypatch):
    monkeypatch.delenv("INTDOG_SEARCH_EXECUTABLE", raising=False)
    command = search_command(["crawl-daily", "--folder", "AI"])
    assert command[1:4] == ["-u", "-m", "src.main"]
    assert command[-3:] == ["crawl-daily", "--folder", "AI"]


def test_packaged_command_reuses_sidecar(monkeypatch):
    monkeypatch.setenv("INTDOG_SEARCH_EXECUTABLE", "/app/backend/intdog-runtime")
    assert search_command(["run-lab", "--folder", "AI"]) == [
        "/app/backend/intdog-runtime", "cli", "run-lab", "--folder", "AI"]


def test_packaged_search_root_controls_working_directory(monkeypatch):
    monkeypatch.setenv("INTDOG_SEARCH_ROOT", "/app/intdog/DomainIntelSearch")
    assert search_cwd(Path("/source/search")) == Path("/app/intdog/DomainIntelSearch")
