# Subproject 5: Three-Platform Productization and Beta Gate Implementation Plan

> **Execution requirement:** Use `superpowers:subagent-driven-development`; Windows, macOS, and Linux native tasks may be validated in parallel after the shared local gates pass.

**Objective:** Generate three installable Beta packages from the same source version and verify the complete first-run flow, background tasks, secure credentials, and data retention.
**Architecture:** One PyInstaller sidecar provides API/CLI/Worker; Electron packages minimal explicit resources; reuse native workflows for unified gates.
**Tech stack:** PyInstaller, Electron 44, electron-builder, GitHub Actions native runners.
**Specification:** `docs/superpowers/specs/2026-09-01-subproject-5-native-product.md`

## Global Constraints

- All three platforms must come from the same Git SHA; old packages do not count as evidence.
- Unsigned Windows/macOS builds may only be Pre-release; the stable release requires signing, and macOS requires notarization.
- The uninstaller must not delete user industry data.
- This round’s “Complete Delivery” approval satisfies the external-action gate for ordinary commits, push to `origin/main`, the existing three-platform CI, idempotent Issue update or missing-only creation, and Pre-releases after all gates pass. Force push, history rewriting, signing/notarization, metered API calls, and deletion of user production data remain out of scope.

---

### Task 1: Freeze Complete API/CLI/Worker Resources

**Files:**
- Modify: `DomainIntelApp/packaging/entry.py`
- Modify: `DomainIntelApp/packaging/build_sidecar.py`
- Modify: `DomainIntelDesktop/scripts/prepare_resources.py`
- Modify: `DomainIntelDesktop/electron-builder.yml`
- Test: `DomainIntelApp/tests/test_packaged_commands.py`
- Test: `DomainIntelDesktop/test/runtime.test.cjs`

- [ ] **Step 1: Write RED resource-manifest tests**

Assert that the frozen entry supports serve/cli/worker, service templates and Web/config/evaluation/skills all enter explicit resources, and installers contain no DomainIntelData, development venv, or keys.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelApp/tests/test_packaged_commands.py -q && npm test --prefix DomainIntelDesktop`

- [ ] **Step 3: Implement the entry point and deterministic resource manifest**

`prepare_resources.py` assembles resources in a temporary directory first and atomically replaces build/resources after generating `resource-manifest.json`.

- [ ] **Step 4: Build and smoke-test the sidecar**

Run: `python DomainIntelDesktop/scripts/prepare_resources.py`
Run: `python DomainIntelApp/packaging/build_sidecar.py`
Run: `python DomainIntelDesktop/scripts/smoke_sidecar.py --executable DomainIntelDesktop/build/backend/intdog-runtime`

### Task 2: Extend Real Installer-Lifecycle Smoke Tests

**Files:**
- Modify: `DomainIntelDesktop/scripts/smoke_desktop.py`
- Create: `DomainIntelDesktop/scripts/smoke_background_service.py`
- Modify: `DomainIntelDesktop/src/main.cjs`
- Test: `DomainIntelDesktop/test/runtime.test.cjs`

- [ ] **Step 1: Write RED lifecycle contract**

The marker file must prove install/mount, first run, the `NOM-01` real public credential-free collection oracle, the reference Agent/API contract, secure credential, service installation, window close, background run, reopen, data persistence, and app uninstall/data retained.

- [ ] **Step 2: Run RED unit contract**

Run: `npm test --prefix DomainIntelDesktop`

- [ ] **Step 3: Implement the native smoke state machine**

Every step has a timeout and diagnostic artifact; failures must not continue to later steps or treat leftover processes as a pass.

- [ ] **Step 4: Run the corresponding platform smoke test on an available local host**

Linux local execution is supplemental; authoritative Windows/macOS results come from their respective runners.

- [ ] **Step 5: Run one real Agent deep smoke test in an explicitly authorized, logged-in user environment**

Send only a fixed small public test task with no user data; record Agent type, capabilities, exit status, structured-result import, and the assertion remaining in review, without recording credentials from the prompt or the raw environment. If the login is invalid or authorization is absent, record an external-acceptance gap and do not use a mock as a substitute.

### Task 3: Strengthen Three-Platform CI and Artifact Evidence

**Files:**
- Modify: `.github/workflows/platform-gates.yml`
- Modify: `.github/workflows/_native-package.yml`
- Modify: `.github/workflows/release-windows.yml`
- Modify: `.github/workflows/release-macos.yml`
- Modify: `.github/workflows/release-linux.yml`

- [ ] **Step 1: Write static workflow RED tests**

Create: `DomainIntelDesktop/test/workflow_contract.test.cjs`, parse YAML text, and assert complete path filters, Worker smoke, renderer smoke, SHA-256, test reports, same-SHA gate, and signing conditions.

- [ ] **Step 2: Run RED**

Run: `npm test --prefix DomainIntelDesktop`

- [ ] **Step 3: Update workflows**

Platform gates must cover `DomainIntelSearch/pyproject.toml`, the Web package/config, and all launcher/packaging/Worker files. Each platform uploads the installer, `.sha256`, and test report.

- [ ] **Step 4: Run GREEN and YAML/repository checks**

Run: `npm test --prefix DomainIntelDesktop && python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### Task 4: Reconcile Bilingual Installation, Onboarding, and Release Status

**Files:**
- Modify: `README.md`, `README.zh-CN.md`
- Modify: `DomainIntelApp/README.md`, `DomainIntelApp/README.zh-CN.md`
- Modify: `docs/onboarding-and-installation.md`, `.zh-CN.md`
- Modify: `docs/release-readiness.md`, `.zh-CN.md`
- Modify: `IMPLEMENTATION_STATUS.md`, `.zh-CN.md`
- Modify: `DESIGN.md`, `DESIGN.zh-CN.md`

- [ ] **Step 1: Write RED documentation contract tests**

Create: `DomainIntelWeb/tests/test_release_docs.py`, verifying bilingual structure, installation commands, no-model flow, Agent/API, background permissions, data location, uninstall retention, Beta warning, and current revision status consistency.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelWeb/tests/test_release_docs.py -q`

- [ ] **Step 3: Update all bilingual documentation and run GREEN**

Run: `python -m pytest DomainIntelWeb/tests/test_release_docs.py -q`

### Task 5: Audit and Retire Old Architecture and Build Debris

**Files:**
- Modify/Delete after audit: `DomainIntelSearch/src/services/worker.py`
- Modify/Delete after audit: `DomainIntelApp/launch_intdog.py`
- Modify/Delete after audit: `DomainIntelApp/windows_launcher.ps1`
- Modify/Delete after audit: `DomainIntelApp/configure_openai_api.ps1`
- Modify/Delete after audit: `DomainIntelApp/configure_openai_api.bat`
- Modify: `DomainIntelSearch/scripts/check_repo.py`
- Create: `DomainIntelWeb/tests/test_retired_surfaces.py`

- [ ] **Step 1: Write RED release-surface and reference contract**

Verify that production source, README, installers, package, and workflow do not reference retired Worker, WSL-only shortcuts, or plaintext API configuration; the release manifest rejects venv, DomainIntelData, historical packages, test output, caches, and keys.

- [ ] **Step 2: Generate an itemized retain/migrate/delete list**

Run import/reference, documentation, installation, and replacement-path checks for candidate files. No file may be deleted without all four pieces of evidence; tests with regression value migrate to the current contract instead of clearing the test directory in bulk.

- [ ] **Step 3: Delete or downgrade to dev-only in recoverable small batches**

Delete only files proven to have no references and whose replacement gates pass; if a development entry point is retained, move it to explicit development documentation and ensure installers exclude it. Do not delete the user data directory or currently valid fixtures.

- [ ] **Step 4: Run retirement and complete regression**

Run: `python -m pytest DomainIntelWeb/tests/test_retired_surfaces.py DomainIntelApp/tests DomainIntelSearch/tests DomainIntelWeb/tests -q`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### Task 6: Pre-Release Gates and External-Action Approval Points

- [ ] **Step 1: Run the complete local gates**

Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `python -m ruff check DomainIntelSearch DomainIntelApp DomainIntelWeb`
Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb && npm test --prefix DomainIntelDesktop`
Run: `python DomainIntelSearch/scripts/check_repo.py && python -m compileall -q DomainIntelApp DomainIntelSearch DomainIntelWeb && git diff --check`

- [ ] **Step 2: Use `$clean-before-commit` to audit the candidate change set**

Do not commit when keys, production data, build debris, stale fixtures, unused dependencies, or unassessed large files are found.

- [ ] **Step 3: Read and record commit/push/CI/Pre-release authorization**

The approval packet’s “Approve the five subprojects and deliver completely” choice and the user’s confirmation satisfy authorization for ordinary commits, push to `origin/main`, existing three-platform CI, idempotent Issues, and Pre-releases after the gates pass. This excludes force push, history rewriting, signing/notarization, metered API calls, and user-data deletion. If authorization is absent or its scope changes, stop locally at `NOT_READY_PENDING_NATIVE_GATES`.

- [ ] **Step 4: Run same-SHA three-platform gates after authorization**

Do not publish if any of Windows, macOS, or Linux fails. First find the existing Issue by platform label/title (the current documents record #1–#3); update it when present and create it only when missing. Reuse or update Pre-releases idempotently by tag/revision instead of duplicating Issues or Releases. Generate or update the three public Beta Pre-releases only after all three platforms succeed.
