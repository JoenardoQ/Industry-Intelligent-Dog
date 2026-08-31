# Agent and First-run Cycle · Round 1 Implementation Contract

[中文](2026-08-31-agent-onboarding-round-1-contract.zh-CN.md)

## Decision and boundary

- The user selected proposals 1, 2, 3, and 4 on 2026-08-31.
- The outcome is a downloadable three-platform product: diagnose first launch, create an industry, run the first task, reopen successfully, and connect or hand off to domestic and international agents.
- This round does not authorize production-data deletion, paid calls, commits, pushes, CI dispatch, or publication.
- MCP remains read-only by default. Agent results enter as review-required drafts and cannot bypass user confirmation into the fact store.

## Authoritative capability model

One backend manifest owns agent and API-provider IDs, labels, regions, connection modes, execution levels, public commands, authentication, Web capability, default model/API base, and documentation links. The factory retains an explicit adapter map and rejects unknown direct providers. API, scheduling, and UI derive from the manifest instead of maintaining secondary lists.

## Agent Bridge loop

1. First-run setup shows copyable Codex, Claude, Work Buddy, and generic MCP configurations.
2. A user can list task packages and export one task as JSON for an industry.
3. Any agent can execute the task offline and produce a result file.
4. Import limits industry, task ID, path, size, schema, and citation fields; it stores `draft_review_required` and an audit entry.
5. Import never overwrites the source task or fact store and rejects absolute paths, traversal, unknown tasks, oversized content, and uncited assertions.
6. A custom CLI profile stores only a command name and public argument template, never a secret, and is never executed through a shell.

## Native product gates

Every Windows, macOS, and Linux native build runs the Python suite, Web DOM tests, production build, OpenAPI drift, repository checks, sidecar smoke, and a desktop renderer workflow. The desktop workflow verifies visible onboarding, first-industry creation, first-task completion, task-center visibility, and industry persistence after reopen. Where secure storage is available, a dummy key verifies encrypted save/clear and non-disclosure.

## Risk coverage model

| ID | Risk | Required evidence |
| --- | --- | --- |
| C1 | Cross-layer capability drift | Manifest→API→scheduler→UI set contract tests |
| C2 | Unready provider is queued | Manual and automatic rejection with no job |
| C3 | Agent config is unusable | Four MCP config structures, arguments, and copy UI tests |
| C4 | Result escapes scope or pollutes facts | Reject traversal, absolute path, unknown task, oversize, bad schema, and missing citations |
| C5 | Valid result partially writes | Atomic write, draft state, audit, and idempotent re-import tests |
| C6 | Custom-command injection | Argv-template validation and shell-metacharacter/path rejection tests |
| C7 | Blank React UI passes packaging | Renderer-DOM first-run and reopen-persistence smoke |
| C8 | Credential leakage | API/DOM/log/artifact scan and secure-store clear test |
| C9 | Docs/release conclusion becomes stale | Aligned bilingual docs and revision/diff-scoped evidence |
| C10 | Existing clients regress | Existing provider IDs, task packages, and read-only MCP regressions |

No local result without Chrome or native runners is represented as a native GUI pass; both remain release blockers.

## Completion criteria

- C1–C10 have automated evidence or an explicit native release-blocking state.
- A new user can select task-pack, signed-in CLI, or secure API mode and create a first industry without editing source.
- An unbundled agent can complete handoff through configuration/task packages; every write-back requires review.
- Current architecture, status, installation, and release documentation align structurally and semantically in Chinese and English.
- The round closes only after reconciliation, tests, and static checks; Superpowers is enabled only afterward for the final round.
