"""Launch a packaged desktop artifact twice and verify graceful lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


LIFECYCLE_STEPS = (
    "install_or_mount", "first_run", "nom_01", "reference_agent",
    "reference_api", "secure_credential", "service_install", "window_close",
    "background_run", "reopen", "data_persist", "uninstall", "data_retained",
)
NOM01_THRESHOLDS = {
    "publishers": 3,
    "source_categories": 2,
    "documents": 6,
    "independent_publishers": 2,
    "entity_candidates": 5,
    "entity_types": 3,
    "chain_nodes": 3,
    "chain_edges": 2,
    "provider_calls": 0,
}


def _public_url(value: object) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def evaluate_nom01(record: dict, *, isolated_root: Path | None = None) -> dict:
    """Apply NOM-01 to live observations; seed/taskpack data can never pass."""
    failures: list[str] = []
    if record.get("mode") != "public_credential_free":
        failures.append("mode_not_public_credential_free")
    binding = record.get("binding") if isinstance(record.get("binding"), dict) else {}
    if record.get("schema") != "intdog-nom01-v1":
        failures.append("schema_not_intdog_nom01_v1")
    if (not binding.get("data_root") or
            len(str(binding.get("database_sha256") or "")) != 64 or
            not binding.get("job_run_id") or binding.get("provider_ledger_calls") != 0):
        failures.append("isolated_install_binding_invalid")
    if isolated_root is not None and binding:
        expected_root = (Path(isolated_root) / "user-data").resolve()
        database = Path(str(binding.get("database") or ""))
        try:
            data_root = Path(str(binding["data_root"])).resolve()
            resolved_database = database.resolve(strict=True)
            if data_root != expected_root or not resolved_database.is_relative_to(expected_root):
                raise ValueError("binding outside isolated data root")
            digest = hashlib.sha256(resolved_database.read_bytes()).hexdigest()
            if digest != binding.get("database_sha256"):
                raise ValueError("database hash mismatch")
            with sqlite3.connect(f"file:{resolved_database}?mode=ro", uri=True) as connection:
                row = connection.execute(
                    "SELECT provider,operation FROM task_runs WHERE id=?",
                    (binding["job_run_id"],)).fetchone()
            if not row or row[0] != "public_sources" or row[1] not in {
                    "bootstrap", "public-bootstrap"}:
                raise ValueError("job ledger mismatch")
        except (OSError, ValueError, KeyError, sqlite3.DatabaseError):
            failures.append("isolated_install_binding_unverifiable")
    publishers = [item for item in record.get("publishers", [])
                  if isinstance(item, dict) and _public_url(item.get("url"))
                  and item.get("reachable") is True
                  and item.get("identity_verified") is True]
    publisher_names = {str(item.get("name") or "").strip().casefold()
                       for item in publishers if str(item.get("name") or "").strip()}
    categories = {str(item.get("category") or "").strip().casefold()
                  for item in publishers if str(item.get("category") or "").strip()}
    documents = [item for item in record.get("documents", [])
                 if isinstance(item, dict) and _public_url(item.get("url"))
                 and bool(item.get("collected_at"))
                 and len(str(item.get("content_sha256") or "")) == 64]
    document_urls = {str(item["url"]) for item in documents}
    document_publishers = {str(item.get("publisher") or "").strip().casefold()
                           for item in documents if str(item.get("publisher") or "").strip()}
    entities = [item for item in record.get("entities", [])
                if isinstance(item, dict) and item.get("status") == "candidate"
                and item.get("name") and item.get("type")]
    entity_types = {str(item["type"]).strip().casefold() for item in entities}
    nodes = [item for item in record.get("chain_nodes", [])
             if isinstance(item, dict) and item.get("id") is not None
             and isinstance(item.get("order"), int)]
    node_ids = {str(item["id"]) for item in nodes}
    ordered = len({item["order"] for item in nodes}) == len(nodes)
    edges = [item for item in record.get("chain_edges", [])
             if isinstance(item, dict)
             and str(item.get("source")) in node_ids
             and str(item.get("target")) in node_ids
             and any(_public_url(value) for value in item.get("evidence", []))]
    provider_calls = record.get("provider_calls")
    counts = {
        "publishers": len(publisher_names),
        "source_categories": len(categories),
        "documents": len(document_urls),
        "independent_publishers": len(document_publishers),
        "entity_candidates": len(entities),
        "entity_types": len(entity_types),
        "chain_nodes": len(nodes) if ordered else 0,
        "chain_edges": len(edges),
        "provider_calls": provider_calls if isinstance(provider_calls, int) else -1,
    }
    for name, threshold in NOM01_THRESHOLDS.items():
        actual = counts[name]
        valid = actual == 0 if name == "provider_calls" else actual >= threshold
        if not valid:
            failures.append(f"threshold:{name}:{actual}:{threshold}")
    return {"passed": not failures, "counts": counts, "failures": failures,
            "mode": record.get("mode") or "unknown"}


def snapshot_retained_data(root: Path) -> dict:
    """Hash the isolated user databases and prove each SQLite file is readable."""
    files, integrity = {}, {}
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or path.name.endswith(("-wal", "-shm")):
            continue
        if path.name != "intdog.sqlite3" and path.suffix not in {".sqlite", ".sqlite3", ".db"}:
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        files[relative] = digest.hexdigest()
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                integrity[relative] = connection.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError:
            integrity[relative] = "not_sqlite"
    return {"files": files, "integrity": integrity}


def compare_retained_data(before: dict, after: dict) -> dict:
    before_files, after_files = before.get("files", {}), after.get("files", {})
    missing = sorted(set(before_files) - set(after_files))
    changed = sorted(path for path in set(before_files) & set(after_files)
                     if before_files[path] != after_files[path])
    invalid = sorted(path for path, result in after.get("integrity", {}).items()
                     if result not in {"ok", "not_sqlite"})
    return {"passed": bool(before_files) and not (missing or changed or invalid),
            "before": before_files, "after": after_files,
            "missing": missing, "changed": changed, "invalid_databases": invalid}


class SmokeState:
    """Atomic, fail-stop record for the native release lifecycle smoke."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.payload = {
            "schema": "intdog-native-smoke-v1",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "steps": {},
            "external_gaps": [],
        }
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def can_run(self, step: str) -> bool:
        if step not in LIFECYCLE_STEPS:
            raise ValueError(f"unknown native smoke step: {step}")
        index = LIFECYCLE_STEPS.index(step)
        return all(self.payload["steps"].get(previous, {}).get("status") in
                   {"passed", "external_gap"}
                   for previous in LIFECYCLE_STEPS[:index])

    def pass_step(self, step: str, diagnostics: dict | None = None) -> None:
        if not self.can_run(step):
            raise RuntimeError(f"native smoke step is blocked by a prior failure: {step}")
        self.payload["steps"][step] = {
            "status": "passed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "diagnostics": diagnostics or {},
        }
        self._write()

    def fail_step(self, step: str, reason: str,
                  diagnostics: dict | None = None) -> None:
        if step not in LIFECYCLE_STEPS:
            raise ValueError(f"unknown native smoke step: {step}")
        self.payload["steps"][step] = {
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "reason": str(reason),
            "diagnostics": diagnostics or {},
        }
        self._write()

    def gap_step(self, step: str, reason: str,
                 diagnostics: dict | None = None) -> None:
        if step not in LIFECYCLE_STEPS:
            raise ValueError(f"unknown native smoke step: {step}")
        self.payload["steps"][step] = {
            "status": "external_gap",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "reason": str(reason),
            "diagnostics": diagnostics or {},
        }
        self._write()

    def external_gap(self, name: str, reason: str) -> None:
        self.payload["external_gaps"].append({
            "name": str(name),
            "reason": str(reason),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
        self._write()


def _launch(application: Path, kind: str, root: Path, attempt: int,
            nom01_record: Path | None = None) -> dict:
        marker = root / f"attempt-{attempt}.json"
        env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "APPDATA": str(root / "appdata"),
            "LOCALAPPDATA": str(root / "localappdata"),
            "DOMAIN_INTEL_DATA_ROOT": str(root / "user-data"),
            "INTDOG_DATA_ROOT": str(root / "user-data"),
            "INTDOG_E2E_MARKER": str(marker),
            "INTDOG_E2E_AUTO_CLOSE_MS": "750",
            "INTDOG_E2E_FULL_WORKFLOW": "1",
        }
        if nom01_record is not None:
            env["INTDOG_NOM01_RECORD"] = str(nom01_record)
        command = [str(application)]
        if kind == "appimage":
            command.append("--appimage-extract-and-run")
        command.extend(["--no-sandbox", "--disable-gpu"])
        try:
            result = subprocess.run(command, env=env, capture_output=True, text=True,
                                    timeout=60, shell=False)
        except subprocess.TimeoutExpired as exc:
            diagnostic = root / f"attempt-{attempt}-timeout.json"
            diagnostic.write_text(json.dumps({"timeout_seconds": 60,
                                                "stdout": str(exc.stdout or "")[-4000:],
                                                "stderr": str(exc.stderr or "")[-4000:]},
                                               ensure_ascii=False, indent=2), encoding="utf-8")
            raise RuntimeError(f"desktop attempt {attempt} timed out; {diagnostic}") from exc
        diagnostic = root / f"attempt-{attempt}-process.json"
        diagnostic.write_text(json.dumps({"returncode": result.returncode,
                                            "stdout": result.stdout[-4000:],
                                            "stderr": result.stderr[-4000:]},
                                           ensure_ascii=False, indent=2), encoding="utf-8")
        if result.returncode:
            raise RuntimeError(
                f"desktop attempt {attempt} failed ({result.returncode})\n"
                f"stdout:\n{result.stdout[-4000:]}\nstderr:\n{result.stderr[-4000:]}")
        state = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        if state.get("state") != "stopped":
            raise RuntimeError(f"desktop attempt {attempt} did not stop cleanly: {state!r}")
        expected_task = "persisted" if attempt == 2 else "completed"
        if (state.get("workflow") != "completed" or
                state.get("firstTask") != expected_task or
                state.get("rendererReady") is not True):
            raise RuntimeError(f"desktop attempt {attempt} did not complete first-run workflow: {state!r}")
        if state.get("credentialLifecycle") not in {"passed", "unavailable"}:
            raise RuntimeError(f"desktop attempt {attempt} did not check credential lifecycle: {state!r}")
        expected_existing = attempt == 2
        if bool(state.get("industryPreexisting")) != expected_existing:
            raise RuntimeError(f"desktop attempt {attempt} persistence check failed: {state!r}")
        return state


def verify_launches(application: Path, kind: str, root: Path) -> list[dict]:
    return [_launch(application, kind, root, attempt) for attempt in (1, 2)]


def _generate_nom01_record(sidecar: Path, root: Path, folder: str = "AI") -> Path:
    """Run the frozen collector against the same isolated data root as the app."""
    env = {**os.environ, "DOMAIN_INTEL_DATA_ROOT": str(root / "user-data"),
           "INTDOG_DATA_ROOT": str(root / "user-data"), "INTDOG_DISABLE_EMAIL": "1"}
    result = subprocess.run(
        [str(sidecar), "cli", "public-bootstrap", "--folder", folder,
         "--execution-mode", "direct", "--provider", "public_sources"],
        env=env, capture_output=True, text=True, timeout=180, shell=False)
    diagnostic = root / "nom01-collection.json"
    diagnostic.write_text(json.dumps({"returncode": result.returncode,
                                      "stdout": result.stdout[-8000:],
                                      "stderr": result.stderr[-8000:]},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
    if result.returncode not in {0, 4}:
        raise RuntimeError(f"public credential-free bootstrap failed; {diagnostic}")
    return root / "user-data" / folder / "one_time" / "research" / "bootstrap" / "nom01-record.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--kind", choices=("appimage", "windows-nsis", "macos-dmg"),
                        required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--nom01-record", type=Path)
    parser.add_argument("--sidecar", type=Path,
                        help="Frozen sidecar used to generate NOM-01 inside isolated app data")
    parser.add_argument("--allow-native-service-mutation", action="store_true")
    parser.add_argument("--allow-external-gaps", action="store_true",
                        help="Run the local renderer smoke and record, but do not close, live gates")
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if not artifact.is_file():
        raise SystemExit(f"desktop artifact missing: {artifact}")
    report = (args.report.resolve() if args.report else
              artifact.with_name(f"{artifact.name}.native-smoke.json"))
    state = SmokeState(report)
    state.external_gap("real_agent",
                       "explicit authorization and a verified logged-in Agent are required")
    with tempfile.TemporaryDirectory(prefix="intdog-desktop-smoke-") as temporary:
        root = Path(temporary)
        cleanup = lambda: None
        retained_before: dict | None = None
        try:
            if args.kind == "windows-nsis":
                install = root / "installed"
                installed = subprocess.run([str(artifact), "/S", f"/D={install}"],
                                           capture_output=True, text=True, timeout=90,
                                           shell=False)
                if installed.returncode:
                    raise RuntimeError(f"NSIS install failed ({installed.returncode})")
                application = install / "IntDog.exe"
                cleanup = lambda: subprocess.run(
                    [str(install / "Uninstall IntDog.exe"), "/S"], timeout=60,
                    capture_output=True, text=True, shell=False)
            elif args.kind == "macos-dmg":
                mount = root / "mount"
                mount.mkdir()
                subprocess.run(["hdiutil", "attach", "-nobrowse", "-mountpoint", str(mount),
                                str(artifact)], check=True, timeout=90, shell=False)
                applications = list(mount.glob("*.app/Contents/MacOS/*"))
                if not applications:
                    raise RuntimeError("DMG does not contain an application executable")
                application = applications[0]
                cleanup = lambda: subprocess.run(
                    ["hdiutil", "detach", str(mount)], timeout=60,
                    capture_output=True, text=True, shell=False)
            else:
                application = root / "installed" / artifact.name
                application.parent.mkdir(parents=True)
                import shutil
                shutil.copy2(artifact, application)
                application.chmod(application.stat().st_mode | 0o111)
                cleanup = lambda: application.unlink(missing_ok=True)
            state.pass_step("install_or_mount", {"kind": args.kind,
                                                  "application": str(application)})
            first = _launch(application, args.kind, root, 1, args.nom01_record)
            state.pass_step("first_run", {"marker_state": first.get("state")})
            nom_record = None
            nom_path = args.nom01_record
            if (nom_path is None or not nom_path.is_file()) and args.sidecar:
                nom_path = _generate_nom01_record(args.sidecar.resolve(), root)
            if nom_path and nom_path.is_file():
                nom_record = json.loads(nom_path.read_text(encoding="utf-8"))
            elif isinstance(first.get("nom01"), dict):
                nom_record = first["nom01"]
            if nom_record is None:
                state.external_gap("nom_01", "live public credential-free evidence was not supplied")
                if args.allow_external_gaps:
                    state.gap_step("nom_01", "live_public_evidence_missing")
                else:
                    state.fail_step("nom_01", "live_public_evidence_missing")
                    raise RuntimeError("NOM-01 requires a live public credential-free evidence record")
            else:
                oracle = evaluate_nom01(nom_record, isolated_root=root)
                if not oracle["passed"]:
                    state.fail_step("nom_01", "oracle_failed", oracle)
                    raise RuntimeError(f"NOM-01 failed: {oracle['failures']}")
                state.pass_step("nom_01", oracle)
            if first.get("referenceAgentContract") is not True:
                state.fail_step("reference_agent", "reference_agent_contract_failed")
                raise RuntimeError("reference Agent contract failed")
            state.pass_step("reference_agent")
            if first.get("referenceApiContract") is not True:
                state.fail_step("reference_api", "reference_api_contract_failed")
                raise RuntimeError("reference API contract failed")
            state.pass_step("reference_api")
            state.pass_step("secure_credential", {"result": first["credentialLifecycle"]})
            from smoke_background_service import exercise
            service = exercise(application, args.kind, root,
                               allow_native_mutation=args.allow_native_service_mutation)
            if service.get("status") != "passed":
                state.external_gap("native_service", str(service.get("reason") or "not run"))
                state.fail_step("service_install", "native_service_not_authorized", service)
                raise RuntimeError("native service lifecycle requires explicit mutation authorization")
            state.pass_step("service_install", service.get("install"))
            state.pass_step("window_close", {"marker_state": first.get("state")})
            state.pass_step("background_run", service.get("background"))
            second = _launch(application, args.kind, root, 2, args.nom01_record)
            state.pass_step("reopen", {"marker_state": second.get("state")})
            state.pass_step("data_persist", {"industry_preexisting": True,
                                             "first_task": second.get("firstTask")})
            retained_before = snapshot_retained_data(root)
        finally:
            result = cleanup()
            if state.can_run("uninstall"):
                returncode = getattr(result, "returncode", 0)
                if returncode:
                    state.fail_step("uninstall", f"cleanup_exit_{returncode}")
                else:
                    state.pass_step("uninstall")
                    retention = compare_retained_data(
                        retained_before or {}, snapshot_retained_data(root))
                    if retention["passed"]:
                        state.pass_step("data_retained", retention)
                    else:
                        state.fail_step("data_retained", "isolated_user_data_changed", retention)
