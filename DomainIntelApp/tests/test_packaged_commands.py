import importlib.util
import json
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


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_release_resources_are_explicit_hashed_and_exclude_mutable_or_secret_data(tmp_path):
    root = tmp_path / "repo"
    fixtures = {
        "DomainIntelWeb/dist/index.html": "web",
        "DomainIntelSearch/config/settings.yaml": "config",
        "DomainIntelSearch/evaluation/fixtures/ai-v1.json": "{}",
        "DomainIntelSearch/skills/README.md": "skills",
        "DomainIntelDesktop/resources/service-templates/linux.service": "service",
        "DomainIntelData/AI/private.json": "user-data",
        ".venv/secret": "venv",
        "keys/provider.key": "secret",
    }
    for relative, value in fixtures.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")
    module = _load("prepare_resources", Path(__file__).parents[2] /
                   "DomainIntelDesktop/scripts/prepare_resources.py")
    target = tmp_path / "resources" / "intdog"
    target.mkdir(parents=True)
    (target / "stale.txt").write_text("old")
    manifest = module.stage_resources(root, target)
    assert set(manifest["groups"]) == {"web", "config", "evaluation", "skills", "service_templates"}
    assert not (target / "stale.txt").exists()
    paths = {item["path"] for item in manifest["files"]}
    assert "DomainIntelWeb/dist/index.html" in paths
    assert all(item["sha256"] and item["size"] >= 0 for item in manifest["files"])
    assert not any(token in path.lower() for path in paths
                   for token in ("domaininteldata", ".venv", "keys", "provider.key"))
    assert json.loads((target / "resource-manifest.json").read_text())["files"] == manifest["files"]


def test_native_smoke_contract_is_fail_stop_and_records_external_agent_gap(tmp_path):
    module = _load("smoke_desktop", Path(__file__).parents[2] /
                   "DomainIntelDesktop/scripts/smoke_desktop.py")
    assert module.LIFECYCLE_STEPS == (
        "install_or_mount", "first_run", "nom_01", "reference_agent",
        "reference_api", "secure_credential", "service_install", "window_close",
        "background_run", "reopen", "data_persist", "uninstall", "data_retained")
    assert module.NOM01_THRESHOLDS == {
        "publishers": 3, "source_categories": 2, "documents": 6,
        "independent_publishers": 2, "entity_candidates": 5,
        "entity_types": 3, "chain_nodes": 3, "chain_edges": 2,
        "provider_calls": 0}
    state = module.SmokeState(tmp_path / "state.json")
    state.pass_step("install_or_mount", {"artifact": "test"})
    state.fail_step("first_run", "timeout", {"log": "first-run.log"})
    assert state.can_run("nom_01") is False
    state.external_gap("real_agent", "explicit authorization or login unavailable")
    payload = json.loads((tmp_path / "state.json").read_text())
    assert payload["steps"]["first_run"]["status"] == "failed"
    assert payload["external_gaps"][0]["name"] == "real_agent"
    local = module.SmokeState(tmp_path / "local-state.json")
    local.pass_step("install_or_mount")
    local.pass_step("first_run")
    local.gap_step("nom_01", "live network gate not requested")
    assert local.can_run("reference_agent") is True
    assert json.loads((tmp_path / "local-state.json").read_text())["steps"]["nom_01"]["status"] == "external_gap"


def test_nom01_oracle_rejects_seed_only_and_accepts_real_hashed_public_observations():
    module = _load("smoke_desktop_nom", Path(__file__).parents[2] /
                   "DomainIntelDesktop/scripts/smoke_desktop.py")
    assert module.evaluate_nom01({"mode": "taskpack", "provider_calls": 0})["passed"] is False
    publishers = [
        {"name": f"Publisher {index}", "url": f"https://p{index}.example/feed",
         "category": "official" if index < 2 else "news", "reachable": True,
         "identity_verified": True} for index in range(3)
    ]
    documents = [
        {"url": f"https://p{index % 3}.example/doc/{index}",
         "publisher": f"Publisher {index % 3}",
         "collected_at": "2026-09-02T00:00:00Z", "content_sha256": f"{index:064x}"}
        for index in range(6)
    ]
    entities = [
        {"name": f"Entity {index}", "type": ("company", "technology", "person")[index % 3],
         "status": "candidate"} for index in range(5)
    ]
    nodes = [{"id": f"n{index}", "order": index} for index in range(3)]
    edges = [
        {"source": "n0", "target": "n1", "evidence": [documents[0]["url"]]},
        {"source": "n1", "target": "n2", "evidence": [documents[1]["url"]]},
    ]
    unbound = {"mode": "public_credential_free",
                                    "provider_calls": 0, "publishers": publishers,
                                    "documents": documents, "entities": entities,
                                    "chain_nodes": nodes, "chain_edges": edges}
    assert module.evaluate_nom01(unbound)["passed"] is False
    result = module.evaluate_nom01({**unbound, "schema": "intdog-nom01-v1",
                                    "binding": {"data_root": "/isolated/data",
                                                "database_sha256": "a" * 64,
                                                "job_run_id": "run-public-bootstrap",
                                                "provider_ledger_calls": 0}})
    assert result["passed"] is True
    assert result["counts"]["provider_calls"] == 0
    assert all(result["counts"][key] >= threshold
               for key, threshold in module.NOM01_THRESHOLDS.items()
               if key != "provider_calls")


def test_background_smoke_requires_explicit_native_mutation(tmp_path):
    module = _load("smoke_background", Path(__file__).parents[2] /
                   "DomainIntelDesktop/scripts/smoke_background_service.py")
    result = module.exercise(tmp_path / "IntDog", "appimage", tmp_path,
                             allow_native_mutation=False)
    assert result["status"] == "external_gap"
    assert "not explicitly authorized" in result["reason"]


def test_retained_data_snapshot_detects_content_change(tmp_path):
    module = _load("smoke_desktop_retention", Path(__file__).parents[2] /
                   "DomainIntelDesktop/scripts/smoke_desktop.py")
    data = tmp_path / "data"
    data.mkdir()
    database = data / "intdog.sqlite3"
    database.write_bytes(b"before")
    before = module.snapshot_retained_data(data)
    database.write_bytes(b"after")
    result = module.compare_retained_data(before, module.snapshot_retained_data(data))
    assert result["passed"] is False
    assert result["changed"] == ["intdog.sqlite3"]
