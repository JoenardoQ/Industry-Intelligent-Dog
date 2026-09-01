# SP5 B Tasks 3–5 Freeze Report

Date: 2026-09-02

## Outcome

- All architecture-sensitive paths trigger Windows, macOS, and Linux jobs from an
  explicit shared revision. Each job checks out and reads back that revision.
- The reusable workflow runs Python/Web/Desktop gates, frozen CLI/API/Worker smoke,
  renderer/native lifecycle smoke, and emits test logs, lifecycle state, one
  platform-scoped artifact, SHA-256, and revision evidence.
- Windows, macOS, and Linux remain separate packages and Pre-releases. Formal
  Windows signing and macOS signing/notarization are credential-gated. Release
  updates are idempotent (`view`, `upload --clobber`, `edit`; create only if absent).
- English and Chinese user documentation now aligns platform installation,
  checksum verification, first run, no-model versus task-package behavior,
  Agent/API setup, background permission/revocation, credential transfer, data
  locations, uninstall retention, Beta warnings, and current external gaps.
- The obsolete thread Worker and plaintext OpenAI configuration scripts were
  removed after the four-evidence audit. Source/WSL launchers remain developer-only
  because active launch scripts and tests still depend on them; they are excluded
  from release resources.

## Coverage ledger

| ID | Risk and oracle | Focused evidence | Remaining gap |
| --- | --- | --- | --- |
| WF-01 | Shared changes trigger three jobs at one revision | workflow contract: pass | Hosted runners not dispatched |
| WF-02 | Worker/renderer, reports, SHA-256, per-platform output | workflow contract: pass | Native artifacts not built locally |
| WF-03 | Beta/formal signing and idempotent release | workflow contract: pass | Signing credentials external |
| DOC-01 | Bilingual user and operator contract | release-doc tests: pass | Human usability study not run |
| RET-01 | Four-evidence deletion and tested replacements | retired-surface tests/audit: pass | Developer launchers intentionally retained |
| RET-02 | Release manifest excludes mutable/secret/generated debris | synthetic path partitions + staged manifest check: pass | Final installer inventory requires native build |

## Verification

- Workflow contract: 3 passed.
- Release-doc and retired-surface focused suite: 7 passed.
- Packaged-command lifecycle focused suite: passed.
- Workflow YAML parse, Python compile, repository structural check, and scoped
  `git diff --check`: passed.

No full repository suite, network access, CI dispatch, native service mutation,
user-data operation, commit, push, Issue update, or Release write was performed.
`NOM-01`, native installer/service/uninstall lifecycle, signing, and real logged-in
Agent validation remain external gaps.
