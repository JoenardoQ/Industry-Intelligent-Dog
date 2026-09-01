# SP5 B Legacy Surface Retirement Audit

Date: 2026-09-02

Deletion requires four independent checks: no runtime import, no active reference,
no user/install documentation dependency, and a tested replacement.

| Candidate | Import/reference evidence | Docs/installer evidence | Replacement | Decision |
| --- | --- | --- | --- | --- |
| `DomainIntelSearch/src/services/worker.py` | No runtime import or active test reference | Not packaged; only historical/plan mentions | `src/background_worker.py` plus Electron per-user service | Delete |
| `DomainIntelApp/configure_openai_api.ps1` | No runtime or test reference | Not packaged or documented as current | Setup Wizard + OS `safeStorage` + anonymous credential pipe | Delete |
| `DomainIntelApp/configure_openai_api.bat` | Only called the retired PowerShell script | Not packaged or documented as current | Same secure Setup Wizard path | Delete |
| `DomainIntelApp/launch_intdog.py` | Referenced by source launchers and launcher tests | Current developer-source documentation uses it indirectly | Native installer is the user path, but developer replacement is not complete | Retain as developer-only |
| `DomainIntelApp/windows_launcher.ps1` | Referenced by shortcut creation and tests | Current WSL developer compatibility path | Native Windows installer replaces it for users, not for WSL development | Retain as developer-only |

The retained launchers are explicitly excluded from release resources. The release
manifest gate rejects `DomainIntelData`, virtual environments, keys/private-key
formats, old native `dist`, test output, dependency directories, and caches. The
Web production `DomainIntelWeb/dist` is the sole allowed `dist` subtree.

No user-data directory was read, migrated, or deleted during this audit.
