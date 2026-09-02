# IntDog Installation and First Run

[中文](onboarding-and-installation.zh-CN.md)

This guide is for desktop-package users. IntDog stores industry data locally, but an installer does not include a model account, API quota, or paid third-party data. The current build is an unsigned test release. Download it only from the project Release and verify the accompanying SHA-256.

## Supported platforms

| Platform | Current architecture | Package |
| --- | --- | --- |
| Windows 10/11 | x64 | `IntDog-<version>-windows-x64.exe` |
| macOS | Apple Silicon arm64 | `IntDog-<version>-macos-arm64.dmg` |
| Linux | x64 | `IntDog-<version>-linux-x86_64.AppImage` |

Intel Macs and other CPU architectures are outside the current test boundary. The three packages are independent and are not interchangeable.

## Install

### Windows 10/11 x64

1. Download the Windows `.exe` and matching `.sha256`. Do not download GitHub's generated Source code archive.
2. In PowerShell, run:

   ```powershell
   Get-FileHash .\IntDog-<version>-windows-x64.exe -Algorithm SHA256
   ```

3. If the digest matches, run the installer and start IntDog from the Start menu or desktop shortcut.
4. An unsigned test build may trigger SmartScreen. Verify the release source and digest before deciding whether to continue.

Logs are under `%APPDATA%\intdog-desktop\logs`; local data is under `%APPDATA%\intdog-desktop\data`.

### macOS Apple Silicon

1. Download the DMG and run `shasum -a 256 IntDog-<version>-macos-arm64.dmg`.
2. Open the DMG and drag IntDog into Applications.
3. Gatekeeper may block an unsigned test build. After verifying the digest, decide whether to allow it in Privacy & Security.

Logs and data are under `~/Library/Application Support/intdog-desktop/logs` and `~/Library/Application Support/intdog-desktop/data`.

### Linux x64

```bash
chmod +x IntDog-<version>-linux-x86_64.AppImage
sha256sum IntDog-<version>-linux-x86_64.AppImage
./IntDog-<version>-linux-x86_64.AppImage
```

Logs and data default to `~/.config/intdog-desktop/logs` and `~/.config/intdog-desktop/data`. They follow `XDG_CONFIG_HOME` when it is set.

## First run

The first launch prepares the local backend and data directory, then opens four steps: Diagnostics, Research connection, Industry, and First result.

### 1. Diagnostics

Confirm that the local runtime and data directory are ready. This is IntDog's own status; it does not mean a model is connected.

### 2. Choose a research connection

Three modes are available:

- **Local Agent:** the Agent CLI must be installed and signed in under the same operating system and user account as IntDog. Discovery checks `PATH` and a bounded set of conventional locations. If that fails, select the CLI command file manually. IntDog does not take over an open Agent GUI and does not bridge Windows and WSL by default.
- **API:** select a provider and enter an exact model ID, API key, optional HTTPS API base, and authentication mode. `OpenAI` is a provider name, not a model ID.
- **Task package:** no model or key is required. It creates a handoff package for a compatible Agent, not completed research.

The desktop main process protects the API key with operating-system credential encryption. The browser UI, logs, URLs, and API responses never return it. If secure storage is unavailable, IntDog refuses a plaintext downgrade.

After an API is configured, you can still:

- edit the model, API base, or authentication mode; leaving the key blank preserves the existing key for the same provider;
- change providers, which requires a new key;
- run **Test API connection** as a real minimal request; or
- clear the API configuration without deleting industry data.

The probe checks authentication and model access and, when bootstrap requires it, the web-search tool. It may consume a small amount of API quota. Success proves only that this minimal request worked, not the quality of later research.

### 3. Create an industry

Enter a display name and local data-folder name. Submission starts initialization directly; there is no second task-package confirmation. Mutating jobs for the same industry run in submission order, while different industries can run independently.

### 4. First result

Direct initialization executes this sequence:

1. source discovery, reachability checks, and the source gate;
2. value-chain nodes, directed edges, citations, and the chain gate;
3. cited entities plus China/global and chain-stage coverage gates; and
4. publication of a review-required knowledge draft.

The UI shows three fixed stage rows and real milestones. While waiting for a provider, it shows the current stage and elapsed time without inventing internal progress.

- `Completed`: all three gates passed and a review-required draft was published. Model output is still not accepted fact.
- `Partial`: a gate did not pass. Completed checkpoints and candidates remain, and downstream work is not misreported as successful.
- `Failed`: provider, configuration, transport, or parsing failed. Task Center shows the redacted concrete cause.
- `Queued`: another mutating job owns this industry. It can be cancelled before launch.
- `Task package created`: a handoff file exists, but industry research has not run.

**Resume and retry** probes the provider again. It reuses a passed stage only when industry, model, workflow, and input fingerprints still match; otherwise it restarts at the first invalid stage.

## Agent connection boundary

IntDog currently executes diagnosed Codex CLI and Claude Code adapters directly. Other registered Agents use ACP, MCP, APIs, or task packages according to the actual adapter. See [Agent connectivity](agent-connectivity.md) for the complete matrix, handshakes, and maturity levels.

“Detected,” “installed,” “signed in,” and “directly executable” are different states. Selecting the ChatGPT GUI `chatgpt.exe` is not a substitute for Codex CLI. Unknown or GUI-only Agents are never presented as callable models.

## Background work, data, and uninstall

Background work is off by default and requires permission. It can be revoked in System Status. Revocation removes the system scheduler entry but does not delete schedules, industry data, or credentials.

Uninstall removes application binaries and shortcuts while user data is retained. A compatible reinstall reuses it. To migrate or back up IntDog, copy the complete platform data directory rather than only the SQLite file.

## Troubleshooting

- **No application window:** inspect `backend.log` in the platform log directory. Remove personal paths, tokens, and keys before sharing it.
- **Agent not found:** confirm that a supported CLI is installed, run its version and login-status commands in the same system, then re-detect or select its command file.
- **401 / authentication:** sign in under the same operating system and user account, or replace the API key.
- **invalid_model:** copy the exact model ID from the provider console; do not enter a provider name.
- **unsupported_tool:** the model or endpoint lacks the web-search tool required by bootstrap. Select a model or provider that explicitly supports it.
- **quota / rate_limit:** check quota and throttling, wait if necessary, then use safe retry.
- **Partial:** inspect the failed gate. This represents a research-coverage gap, not a formatting error.

Synthetic local tests do not prove that a real paid account is available. A public test release still requires native install, first-launch, shutdown, and reopen gates on Windows, macOS, and Linux.
