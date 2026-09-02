# IntDog Test-Release Gates

[中文](release-readiness.zh-CN.md)

This document defines release rules; it does not claim that the current working tree has passed them. Every candidate revision must produce fresh evidence.

## Artifacts

| Platform | Architecture | File |
| --- | --- | --- |
| Windows | x64 | `IntDog-<version>-windows-x64.exe` |
| macOS | Apple Silicon arm64 | `IntDog-<version>-macos-arm64.dmg` |
| Linux | x64 | `IntDog-<version>-linux-x64.AppImage` |

Each package contains only its platform’s Electron shell and matching PyInstaller sidecar. A WSL or source shortcut is not a Windows installer. The business implementation is shared; changes to Electron, API, schema, Python runtime, or Web UI invalidate and rerun all three platform jobs.

## Test and stable releases

- A test build uses a prerelease version and GitHub Pre-release. It may be unsigned, but its release notes disclose SmartScreen/Gatekeeper risk and publish SHA-256.
- A stable Windows build must be signed. A stable macOS build must be signed and notarized.
- Without signing credentials, a test artifact must not be labeled stable.
- Existing Windows, macOS, and Linux tracking Issues are updated idempotently; create one only when it does not exist.

## Required gates

1. The same revision passes Python tests, Web tests/build, Desktop tests, type/OpenAPI contracts, repository hygiene, and secret scanning.
2. Each native platform completes install or mount, first launch, backend readiness, close, process/port release, and relaunch.
3. With an isolated temporary data root, test industry creation, automatic Agent discovery and explicit command-file selection, version/sign-in diagnosis, first job, all eight primary pages, cancel/retry, delete/restore, and safe shutdown. Windows must cover a `.cmd` shim; macOS/Linux must cover desktop launch without terminal-profile PATH entries.
4. The no-model flow must produce a deterministic useful minimum; creating only a task package is not research success.
5. A real signed-in Agent first passes the UI fixed-marker minimal call and then completes a deep job without credential leakage. Static MCP configuration is not sufficient evidence. Unavailable hosts or external-network gates remain explicitly unverified.
6. A direct research job that does not publish its required artifact ends `partial` or `failed`, never `completed`.

## Security and data boundary

- The API listens only on `127.0.0.1` and validates session, Host, and Origin.
- Desktop keys use OS credential storage and a one-shot anonymous pipe into the sidecar; they do not enter logs, command lines, or child-process environments.
- Tests use a temporary data root. Industry data, live collection output, logs, and personal paths do not enter release commits.
- Background scheduling is installed only after explicit user action, permissions are revocable, and uninstall retains user data by default.

## Decision rule

Only a candidate that passes all P0 gates on all three platforms may be labeled `READY_FOR_PUBLIC_TESTING`. If any native platform, real-agent, or external-collection evidence is missing, the result remains `NOT_READY` or explicitly partial. Evidence from an older revision cannot prove a newer one.
