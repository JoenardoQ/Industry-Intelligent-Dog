from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
VALIDATOR = ROOT / "DomainIntelDesktop" / "scripts" / "validate_release_assets.py"


def test_product_version_has_one_authority_and_a_valid_python_projection():
    product_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert product_version == "4.1.0-test.4"
    for package in ("DomainIntelWeb", "DomainIntelDesktop"):
        manifest = json.loads((ROOT / package / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / package / "package-lock.json").read_text(encoding="utf-8"))
        assert manifest["version"] == product_version
        assert lock["version"] == product_version
        assert lock["packages"][""]["version"] == product_version

    server = (ROOT / "DomainIntelSearch/src/mcp_server.py").read_text(encoding="utf-8")
    assert re.search(rf'^SERVER_VERSION = "{re.escape(product_version)}"$', server, re.M)
    python_version = tomllib.loads(
        (ROOT / "DomainIntelSearch/pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    assert python_version == "4.1.0.dev3"

    assert _workflow("release-test.yml")["on"]["workflow_dispatch"]["inputs"]["version"]["default"] == product_version
    assert _workflow("_native-package.yml")["on"]["workflow_call"]["inputs"]["version"]["default"] == product_version


def test_release_dispatch_rejects_a_version_different_from_repository_version():
    validate = _workflow("release-test.yml")["jobs"]["validate"]
    assert any(step.get("uses", "").startswith("actions/checkout@")
               for step in validate["steps"])
    assert 'test "$VERSION" = "$(tr -d \'\\r\\n\' < VERSION)"' in _run_scripts(validate)


def _workflow(name: str) -> dict:
    return yaml.load((WORKFLOWS / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _run_scripts(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job.get("steps", []))


def test_one_dispatch_builds_all_native_candidates_before_publication():
    """Catches split entry points or publication that can run after only one platform."""
    release = _workflow("release-test.yml")
    assert "workflow_dispatch" in release["on"]

    build = release["jobs"]["build"]
    assert build["uses"] == "./.github/workflows/_native-package.yml"
    platforms = {item["platform"] for item in build["strategy"]["matrix"]["include"]}
    assert platforms == {"windows", "macos", "linux"}
    assert build["with"]["revision"] == "${{ github.sha }}"
    assert build["with"]["version"] == "${{ inputs.version }}"
    assert build["with"]["release_candidate"] == "true"

    publish = release["jobs"]["publish"]
    assert publish["needs"] == "build"
    assert publish["if"] == "${{ needs.build.result == 'success' }}"


def test_publisher_uses_tested_bundles_and_cannot_rebuild_installers():
    """Catches a second package build or publishing before all expected assets exist."""
    publish = _workflow("release-test.yml")["jobs"]["publish"]
    uses = [step.get("uses", "") for step in publish["steps"]]
    assert any(value.startswith("actions/download-artifact@") for value in uses)

    scripts = _run_scripts(publish)
    for forbidden in ("npm run dist:", "build_sidecar.py", "smoke_desktop.py"):
        assert forbidden not in scripts
    assert "validate_release_assets.py" in scripts
    assert "--revision \"${revision}\"" in scripts

    draft = scripts.index("--draft")
    public = scripts.index("--draft=false --prerelease")
    assert draft < public


def test_native_reusable_only_builds_and_uploads_platform_artifacts():
    """Catches hidden Release or Issue mutation inside one platform build."""
    reusable = _workflow("_native-package.yml")
    assert "release_candidate" in reusable["on"]["workflow_call"]["inputs"]
    scripts = _run_scripts(reusable["jobs"]["package"])
    assert "gh release" not in scripts
    assert "gh issue" not in scripts
    assert "gh run list" not in scripts
    assert "linux-x86_64.AppImage" in scripts
    assert any(
        step.get("uses", "").startswith("actions/upload-artifact@")
        for step in reusable["jobs"]["package"]["steps"]
    )


def test_split_manual_release_entry_points_are_removed_but_push_gate_remains():
    """Catches reintroduction of release batches that can drift by platform."""
    for platform in ("windows", "macos", "linux"):
        assert not (WORKFLOWS / f"release-{platform}.yml").exists()

    gate = _workflow("platform-gates.yml")
    assert set(gate["jobs"]) == {"windows", "macos", "linux"}
    assert "pull_request" in gate["on"]
    assert "push" in gate["on"]


def _write_release_bundle(root: Path, version: str, revision: str = "abc123") -> None:
    names = {
        "windows": f"IntDog-{version}-windows-x64.exe",
        "macos": f"IntDog-{version}-macos-arm64.dmg",
        "linux": f"IntDog-{version}-linux-x86_64.AppImage",
    }
    for platform, name in names.items():
        platform_root = root / platform
        platform_root.mkdir()
        payload = f"synthetic-{platform}-installer".encode()
        (platform_root / name).write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        (platform_root / f"{platform}-artifact-evidence.sha256").write_text(
            f"{digest}  {name}\n", encoding="utf-8"
        )
        (platform_root / f"{platform}-artifact-evidence.json").write_text(
            json.dumps({
                "schema": "intdog-native-evidence-v1",
                "platform": platform,
                "revision": revision,
                "artifacts": [{"name": name, "size": len(payload), "sha256": digest}],
            }),
            encoding="utf-8",
        )


def test_asset_validator_accepts_one_complete_same_hash_batch(tmp_path):
    """Catches a publisher that cannot recognize the intended complete bundle."""
    _write_release_bundle(tmp_path, "4.2.0-test.1")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--root", str(tmp_path),
         "--version", "4.2.0-test.1", "--revision", "abc123"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "validated 3 native installers" in result.stdout


def test_asset_validator_rejects_a_missing_or_corrupt_platform(tmp_path):
    """Catches public drafts created from an incomplete or substituted batch."""
    _write_release_bundle(tmp_path, "4.2.0-test.1")
    (tmp_path / "macos" / "IntDog-4.2.0-test.1-macos-arm64.dmg").write_bytes(b"changed")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--root", str(tmp_path),
         "--version", "4.2.0-test.1", "--revision", "abc123"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr


def test_asset_validator_rejects_duplicate_installers(tmp_path):
    """Catches ambiguous glob selection that could publish an untested installer."""
    _write_release_bundle(tmp_path, "4.2.0-test.1")
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    duplicate.joinpath("IntDog-4.2.0-test.1-windows-x64.exe").write_bytes(
        b"synthetic-windows-installer"
    )
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--root", str(tmp_path),
         "--version", "4.2.0-test.1", "--revision", "abc123"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "expected exactly one windows installer" in result.stderr
