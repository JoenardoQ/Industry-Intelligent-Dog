# Round 3 deletion ledger

The user requested deletion, but the host safety reviewer requires confirmation of these exact paths.

## Historical knowledge reset

- `DomainIntelData/AI/`
- `DomainIntelData/_archive/`
- `DomainIntelData/_jobs/`
- `DomainIntelData/_trash/` if present
- `DomainIntelData/intdog.sqlite3`, `intdog.sqlite3-wal`, `intdog.sqlite3-shm`

Preserve `DomainIntelData/README.md` and `DomainIntelData/skill/`.

## Proven obsolete development artifacts

- `docs/superpowers/` (superseded plans for the deleted Tk UI)
- `docs/iteration-evidence/2026-08-30-task-6/` and `task-6-report.md` (paused old-UI smoke)
- `.intdog-runtime/venv-linux/` and `.intdog-runtime/environment-linux.json`
  (old pre-platform-fingerprint runtime; preserve `venv-linux-py312`)
- `.pytest_cache/`, `DomainIntelSearch/.pytest_cache/`, and generated `__pycache__/` directories
  below `DomainIntelSearch`, `DomainIntelApp`, and `DomainIntelWeb`.

The source tree, current runtime, configuration, docs outside the obsolete list, credentials and Git
metadata are not deletion targets.
