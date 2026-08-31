# Subproject 5: Three-Platform Productization and Beta Gate Specification

Status: Approved, awaiting implementation verification
Dependency: All shared local gates passed for Subprojects 1–4

## Objective

Generate Windows x64, macOS arm64, and Linux x64 installers from the same Git revision, and prove that the installed real UI, frozen sidecar, secure storage, background service, and data lifecycle run correctly.

## Installers

- Windows: NSIS `.exe`, desktop and Start Menu entries, with an optional installation directory.
- macOS: arm64 `.dmg`, which may be unsigned for Beta; the stable release must be signed and notarized.
- Linux: x64 AppImage with desktop metadata and an icon.
- Publish an installer, SHA-256, build manifest, and test report separately for each platform; do not require users to provide a runtime or development source code.

## Native Lifecycle

On the corresponding native runner, each platform must install or mount, launch for the first time, complete the no-model first task, verify the connection contract through a local reference Agent/compatible API harness, configure virtual secure credentials, install the background service, close the window, trigger one background task, reopen and verify persistent data, and finally uninstall the application while retaining the user’s industry data. The no-model first task passes only when, in an isolated data directory and `public_credential_free` collection mode, it actually obtains all of the following: at least 3 reachable publishers with verified identities (from at least 2 source categories), 6 non-duplicate documents (from at least 2 independent publishers), 5 entity candidates (from at least 3 object types), 3 ordered value-chain nodes, and 2 directed edges with document/assertion evidence. The result must record real URLs, collection times, and content hashes, with zero Provider/API calls; generating only a taskpack, built-in seed list, or local reference harness does not satisfy this oracle. Network failure or insufficient public sources must produce an explicit partial/gap and block this acceptance gate.

At least one user-controlled native environment must also complete one bounded deep workflow with a logged-in, explicitly authorized real Agent CLI; when that authorization or login is unavailable, it must be separately marked as an external acceptance gap.

## Build and Security

- The PyInstaller sidecar contains API, CLI, and Worker entry points.
- electron-builder includes only explicit resources; generate OpenAPI types before building and check for drift.
- Scan installers and logs for plaintext virtual keys, development paths, test data, and production data.
- The Release workflow accepts only successful three-platform shared-gate results from the same revision.
- Unsigned builds may be labeled only as public Pre-release and must display a platform warning.

## Retirement of the Old Architecture

Before deleting the old Worker, Tk/WSL launchers, plaintext API-configuration scripts, expired fixtures, or tests, all of the following must hold simultaneously: no production imports or calls, no documentation or installation-flow dependency, the replacement path has passed regression, and user data is not in scope. Tests that still provide regression value must be migrated or rewritten, not deleted to reduce repository size. If a development-only entry point is retained, it must be clearly marked and excluded from installers.

## Documentation and Onboarding

Chinese and English READMEs and installation guides separately provide system requirements, installation, first use, Agent/API connection, no-model mode, background permissions, troubleshooting, uninstall, and data location. In-app first-run onboarding and documentation use the same terminology and steps.

## Acceptance

- Complete Python, Web, Desktop, OpenAPI, repository-check, sidecar, Worker, and renderer lifecycle checks pass on all three platforms.
- The reference Agent harness export/execution/import contract passes, and at least one bounded deep workflow with a real logged-in Agent CLI has a redacted record; mocks cannot replace the latter.
- The `NOM-01` no-model oracle’s source, document, entity, value-chain, and zero-Provider-call assertions all pass; the reference harness verifies only deterministic contracts and cannot replace real public collection.
- Installers come from the same SHA, and filenames, versions, checksums, and release notes are consistent.
- The old `4.0.0-test.1` or any other historical package is not used as current evidence.
- The release path contains no retired entry points, development venv, historical builds, old test data, or plaintext configuration scripts; the deletion list has reviewable reference and replacement evidence.
- This round’s “Complete Delivery” approval covers ordinary commits after a blocker-free audit, push to `origin/main`, the existing three-platform CI, idempotent reuse/update of platform Issues (creating only missing ones), and public Pre-releases after the gates pass. It excludes force push, history rewriting, signing/notarization, metered API calls, and deletion of user production data.
