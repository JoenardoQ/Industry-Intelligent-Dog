# SP5 A Tasks 1–2 Freeze Report

Date: 2026-09-02

## Implemented

- The frozen sidecar explicitly supports `serve`, `cli`, and `worker --once`.
- Release resources are limited to the Web build, Search config, evaluation,
  skills, and platform service templates. Assembly writes a SHA-256 manifest in a
  temporary directory and atomically replaces the target.
- Staging and electron-builder exclude `DomainIntelData`, virtual environments,
  keys, and common private-key formats.
- Sidecar smoke verifies resource digests and executes CLI, Worker, and local API
  startup/shutdown.
- Native smoke has a 13-step atomic fail-stop state record with bounded diagnostic
  output for every process.
- `NOM-01` rejects task packages and seeds. It requires real URLs, verified and
  reachable publisher identity, collection timestamps, content hashes, entity
  types, ordered value-chain nodes, evidence-bearing edges, and zero Provider calls.
- Native service mutation requires an explicit flag and uses isolated app data;
  cleanup removes the service in a `finally` path.
- Reference Agent/API checks cover deterministic contracts only. A real logged-in
  Agent deep smoke was not authorized and remains an external gap.

## Local evidence

- Packaged-command focused tests: 7 passed; Desktop runtime focused: 1 passed.
- Python compile, five resource groups/40 files, and scoped diff check passed.
- A newly built Linux frozen sidecar passed CLI/Worker/API smoke.

## External gaps

Live `NOM-01` collection, native Windows/macOS/Linux installer lifecycle,
background scheduler installation, uninstall/data retention, and a real logged-in
Agent were not run. They remain external gaps; the native Beta lifecycle must not
be reported as passed.
