# IntDog Installation, First-run, and Agent Connection Contract

[中文](onboarding-and-installation.zh-CN.md)

## User outcome

A first-time desktop user must be able to do the following without reading the source:

1. see a clear first-run guide;
2. inspect the real local backend, data-directory, and model-provider state;
3. choose a detected local agent, explicit API, or model-free task-package mode;
4. create the first industry and run one observable initialization job; and
5. use the task center to understand success, failure, and the next action.

The installer contains the IntDog desktop shell, Web workbench, and local Python
sidecar. It does not include a ChatGPT account, Codex CLI login, or OpenAI API
quota. The UI must not present “IntDog started” as “agent connected.”

## Supported boundary

| Platform | Test architecture | Artifact | Model prerequisite |
| --- | --- | --- | --- |
| Windows 10/11 | x64 | NSIS `.exe` | Codex/Claude CLI, explicit API, or task package |
| macOS | Apple Silicon arm64 | `.dmg` | Codex/Claude CLI, explicit API, or task package |
| Linux | x64 | `.AppImage` | Codex/Claude CLI, explicit API, or task package |

Test packages are unsigned. Windows SmartScreen or macOS Gatekeeper may require
manual approval; that is not a reason to bypass security checks. Intel macOS is
outside the current test boundary.

## Install and remove

### Windows 10/11 x64

1. Download `IntDog-<version>-windows-x64.exe` and its `.sha256` from the Windows Pre-release; do not download the source archive.
2. Verify it with `Get-FileHash .\IntDog-<version>-windows-x64.exe -Algorithm SHA256` in PowerShell.
3. Run the NSIS installer and launch IntDog from the Start menu or desktop shortcut.
4. Logs and data are under `%APPDATA%\intdog-desktop\logs` and `%APPDATA%\intdog-desktop\data`; the install directory contains no user database.

### macOS Apple Silicon

1. Download `IntDog-<version>-macos-arm64.dmg` and run `shasum -a 256 IntDog-<version>-macos-arm64.dmg`.
2. Mount the DMG and drag IntDog into Applications. This Beta is unsigned; inspect the checksum and release source before using the Finder **Open** exception.
3. Logs and data are under `~/Library/Application Support/intdog-desktop/logs` and `~/Library/Application Support/intdog-desktop/data`.

### Linux x64

1. Download the AppImage and run `chmod +x IntDog-<version>-linux-x64.AppImage`.
2. Verify it with `sha256sum IntDog-<version>-linux-x64.AppImage`, then launch it.
3. Logs and data are under `~/.config/intdog-desktop/logs` and `~/.config/intdog-desktop/data` unless `XDG_CONFIG_HOME` is overridden.

Before uninstalling, disable background scheduling in System Status and confirm it is disabled. App uninstall removes binaries and shortcuts but retains the user-data directory. Back up or remove that directory separately; a compatible reinstall reuses it.

## Provider state machine

```text
unchecked → not installed / signed out / connected / check failed
                               ↓
                   create industry → first job → logs and artifact
```

- **Codex subscription:** IntDog must find an executable Codex CLI under the same
  operating system and user account and confirm its sign-in state. When automatic
  discovery fails, the user can select `codex.exe` or `codex.cmd` with the native
  file picker. Windows/WSL bridging is not a default product path.
- **OpenAI API:** the user supplies an API key and model. The desktop app stores the
  key with Electron `safeStorage`, backed by the operating-system encryption
  facility; the backend receives the decrypted value through an anonymous one-shot
  pipe and clears the in-memory transfer object after use.
  The key must never enter the repository, logs, URL, localStorage, or API response.
- **Task package:** no model or secret is required. It creates a structured prompt,
  not a completed research report.

### Agent interface matrix

| Interface | Direct generation | Discovery | Connection boundary |
| --- | --- | --- | --- |
| Codex CLI | yes | CLI and public login status | Same OS as IntDog; automatic discovery or explicit command-file selection |
| Claude Code | yes | CLI and `auth status` | Official `-p` mode with plan permissions |
| DeepSeek Harness | no (experimental discovery) | `dsh` | Developer preview; use MCP/task-package handoff without claiming a stable direct CLI |
| Work Buddy | no | executable | A workflow layer over Claude Code; use MCP/task packages |
| Qwen Code, CodeBuddy Code, Kimi CLI | no | executable | MCP/task-package bridges for Chinese agents |
| Gemini CLI, OpenCode | no | executable | MCP/task-package bridges for international/neutral agents |
| Custom CLI | no | validated UI profile or `INTDOG_CUSTOM_AGENT_COMMAND` | Public argv only; handoff by default |
| OpenAI, DeepSeek, Qwen, Azure OpenAI API | yes | environment or desktop secure storage | Keys never enter the browser, repository, logs, or API response |

“Detected” proves only that a public command exists. “Connected” additionally
requires the adapter's public authentication check to pass. IntDog does not scan
private account directories belonging to ChatGPT, Claude, or other GUI apps.
Unlisted agents can use the generic MCP configuration shown during setup or export
task JSON from **Research Studio → Agent handoff**. Their result JSON imports into
a review-required area. A direct adapter still requires a fixed public contract for
input, output, authentication, timeout, and failure behavior. Existing task packages
and model-free collection remain available.

### Agent result contract

An import contains `task_id`, `agent_id`, `summary`, and one or more `assertions`; every assertion requires HTTP(S) `citations`. IntDog rejects unknown tasks, uncited or invalid schemas, content over 500 KiB, and path/shell syntax in custom command profiles. Valid output is an audited `draft_review_required` file under `one_time/agent_results/` and never mutates the fact store directly.

When a provider is unavailable, model-generation actions must be rejected before
queueing with an actionable recovery message. Local browsing, industry management,
task packages, and model-free collection remain available.

## First-run journey

1. Show three diagnostics—local runtime, data directory, and agent—instead of an empty workbench.
2. Let the user choose a provider:
   - Codex shows executable discovery, sign-in state, resolved path, and official setup link;
   - API mode accepts provider, key, model, and an optional HTTPS API base, then securely restarts;
   - task package explicitly states that it does not call a model.
3. Finish only when a provider is ready or the user explicitly selects task-package mode.
4. Create an industry, run initialization, and navigate to the task center with stage, log, error, and artifact visibility.
5. After success, show sources, documents, entities, or an explicit waiting-for-collection state.

Task-package mode and the no-model live path are different. A task package is only a handoff. The live `NOM-01` path must collect credential-free public evidence and meet the documented publisher, document, entity, value-chain, content-hash, and zero-Provider-call oracle; partial/offline results remain an external gap.

## Background permission and revocation

Background scheduling is off until the user enables it. IntDog installs a per-user Task Scheduler entry (Windows), LaunchAgent (macOS), or systemd user timer (Linux). The settings page shows installed/enabled/last-run/error state. Use **Revoke background permission** to remove the scheduler entry; revocation does not erase schedules, research, or credentials. Closing the window may leave an authorized schedule active, but it may not bypass provider authorization or secure-storage state.

## Failure and recovery

- No window after EXE launch: show a startup error and the user-data `logs/backend.log` path; never fail silently.
- Codex missing: show the probed path and official setup link; do not install external tools automatically.
- Codex signed out or HTTP 401: instruct the user to sign in under the same operating system and user account, then offer recheck and command-file reselection.
- Invalid API key: do not persist the test response or key; show a redacted provider error.
- Backend exits early: retain logs and never show a connected state.
- Secure storage unavailable: refuse to store a key and offer task-package mode; do not downgrade the desktop app to plaintext or environment transfer.

## P0 acceptance and coverage

| ID | Risk or behavior | States and interactions | Oracle |
| --- | --- | --- | --- |
| O1 | First launch after install | fresh user data, second launch, spaces/Unicode in path | Native package shows backend, UI, and log evidence |
| O2 | Provider diagnosis | no CLI, automatic discovery, manual selection, `.cmd` shim, signed out, signed in | Synthetic executable/status outputs and API decision table |
| O3 | API credentials | empty key, valid shape, restart, no safeStorage | No plaintext key in files, logs, DOM, or API response |
| O4 | Onboarding state | first run, task package, complete, reopen settings | DOM/accessibility state transitions and button gates |
| O5 | First job | ready provider, unavailable provider, job failure | Unavailable does not queue; ready navigates to visible job log |
| O6 | Package completeness | missing sidecar/Web/icon/uninstaller | Installed resource inventory and prelaunch checks |
| O7 | Diagnostics | backend exit, timeout, provider 401 | Actionable log location and no credential disclosure |
| O8 | Agent extensibility | native execution, MCP handoff, experimental and unknown CLIs | Registry never confuses presence with authentication or direct execution |

Synthetic local tests do not prove that a real ChatGPT account or paid API is
available. A public test build may ship only after all three native runners repeat
installation, onboarding, provider diagnosis, shutdown, and reopen checks.
