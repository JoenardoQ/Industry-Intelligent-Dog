# SP4 User Workflow Freeze Report

Date: 2026-09-02

## Frozen scope

- Overview, daily intelligence, knowledge, source review, research assistant,
  products, task center, and system status.
- Direct research/Lab/industry/periodic generation, one safe reader, directed
  value chain, background task state, and recovery.
- A deterministic artifact-quality gate and portable single-file HTML that does
  not require the IntDog backend.

## Result

The quality gate stores `fact_state` separately from `artifact_status`. It checks
length, placeholders, vague or duplicate paragraphs, evidence for structured
claims, summary/date/source for key sections, Markdown protocols and anchors, and
chart sidecars. A stable machine-readable failure code changes only the artifact
to `partial`; it never promotes or demotes fact review state.

Periodic, industry, deep, and impact generation emits Markdown, a
`.manifest.json`, a `.quality.json`, and a `.portable.html`. The HTML embeds escaped
data, fixed local CSS/JavaScript, and a no-connect CSP. It supports local search,
source/status/value-chain filters, local favorites, print/PDF, evidence links, and
review state. Daily and Products expose export/open actions.

## Verification

- Python focused: 10/10 passed.
- Web DOM/axe focused: 33/33 passed; production build passed.
- Desktop focused: 3/3 passed.
- Browser-smoke and Electron syntax checks, plus `git diff --check`, passed.

Real Playwright/Chromium smoke was not run because the environment lacked those
dependencies and network installation was out of scope. No full-suite, network,
visual-assistance, commit, or push action was performed.
