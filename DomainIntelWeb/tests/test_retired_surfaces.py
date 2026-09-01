import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_check_repo():
    path = ROOT / "DomainIntelSearch/scripts/check_repo.py"
    spec = importlib.util.spec_from_file_location("check_repo_release", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_release_manifest_rejects_mutable_sensitive_and_generated_paths():
    module = _load_check_repo()
    unsafe = [
        "DomainIntelData/AI/intdog.sqlite3", ".venv/bin/python", "keys/openai.key",
        "DomainIntelDesktop/dist/old.exe", "test-results/results.xml",
        "DomainIntelWeb/node_modules/react/index.js", "src/__pycache__/x.pyc",
    ]
    assert module.release_manifest_violations(unsafe) == unsafe
    assert module.release_manifest_violations([
        "DomainIntelWeb/dist/index.html", "DomainIntelSearch/config/settings.yaml",
        "DomainIntelDesktop/resources/service-templates/linux.service",
    ]) == []


def test_retired_thread_worker_and_plaintext_key_configurators_are_absent():
    assert not (ROOT / "DomainIntelSearch/src/services/worker.py").exists()
    assert not (ROOT / "DomainIntelApp/configure_openai_api.ps1").exists()
    assert not (ROOT / "DomainIntelApp/configure_openai_api.bat").exists()


def test_retained_developer_launchers_are_excluded_from_native_release_resources():
    manifest = ROOT / "DomainIntelDesktop/build/resources/intdog/resource-manifest.json"
    if not manifest.is_file():
        return
    text = manifest.read_text(encoding="utf-8").casefold()
    assert "launch_intdog.py" not in text
    assert "windows_launcher.ps1" not in text


def test_release_evidence_hashes_only_one_requested_platform_artifact(tmp_path):
    path = ROOT / "DomainIntelDesktop/scripts/release_evidence.py"
    spec = importlib.util.spec_from_file_location("release_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    (tmp_path / "IntDog-4.0.0-linux-x86_64.AppImage").write_bytes(b"appimage")
    (tmp_path / "IntDog-4.0.0-windows-x86_64.exe").write_bytes(b"windows")
    manifest = module.build_manifest(tmp_path, "linux", "abc123")
    assert manifest["revision"] == "abc123"
    assert [item["name"] for item in manifest["artifacts"]] == [
        "IntDog-4.0.0-linux-x86_64.AppImage"]
    assert len(manifest["artifacts"][0]["sha256"]) == 64
