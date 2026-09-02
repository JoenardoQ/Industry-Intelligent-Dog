# Single-pass native test release

## Goal

Publish the Windows, macOS, and Linux test releases from the exact artifacts
that passed their platform-native checks. A release invocation must build each
platform once; it must not run a separate architecture gate and then rebuild
the installers for publication.

## Workflow

One manually dispatched workflow accepts a prerelease SemVer and the three
optional existing platform Issue numbers.

1. A matrix runs on Windows x64, macOS arm64, and Linux x64.
2. Each matrix job checks out the same immutable revision, applies the requested
   package version, installs locked dependencies, checks generated contracts,
   and runs the complete Python, Web, and Desktop test suites.
3. The job stages resources, builds and smoke-tests the native sidecar, builds
   the native installer, exercises install or mount, launch, close, and reopen,
   then writes revision-bound SHA-256 evidence.
4. Each job uploads one platform artifact bundle for the publish job. Build
   jobs do not create Releases or mutate Issues.
5. A publish job runs only after every matrix job succeeds. It downloads all
   three bundles, verifies the expected installer and checksum filenames, then
   creates or refreshes three draft Releases.
6. After all assets are present, the publish job converts all three drafts to
   public Pre-releases and idempotently updates the existing platform Issues.

## Failure and retry behavior

- A build or native lifecycle failure prevents the publish job from running.
- Release tags are `v<version>-windows`, `v<version>-macos`, and
  `v<version>-linux`.
- A retry reuses the tags and platform Issues, replaces matching assets, and
  does not create duplicates.
- GitHub cannot provide a transaction spanning three Releases. Draft-first
  publication prevents incomplete assets from becoming public during normal
  failures; an interruption while converting drafts can still expose a partial
  set. A retry completes the same set idempotently.
- Test releases remain unsigned and are explicitly marked as such.

## Existing workflows

- `platform-gates.yml` remains the PR and main-push verification workflow.
- The release workflow does not depend on a prior gate run because its matrix
  performs the complete gate against the same artifacts it publishes.
- The three platform-specific manual release entry points are removed so users
  cannot accidentally produce a split release batch.
- Shared build behavior remains in the reusable native workflow; publication
  is owned only by the unified release workflow.

## Acceptance

Static workflow tests must prove:

1. one dispatch owns all three platform builds;
2. publication depends on all three build results;
3. the publish job downloads, rather than rebuilds, installers;
4. no build job publishes a Release;
5. all three expected installers and checksum files are validated before any
   draft is made public;
6. retries reuse existing tags and Issues;
7. ordinary PR and main-push platform gates remain available.
