# Bootstrap workflow recovery and first-use experience

## Outcome

Repair the installed desktop application's first industry research path so a
non-developer can configure a supported provider, start one operation, observe
real progress, and receive either a complete three-stage research draft or a
specific recoverable result.

This is baseline reconciliation before the two authorized optimization rounds.
It does not install the application, access a real user API key, publish a
release, delete user data, or turn model output into accepted facts.

## Product contract

Direct bootstrap is one sequential operation:

```text
provider preflight
  -> source discovery and source gate
  -> value-chain discovery and chain gate
  -> entity discovery and coverage gate
  -> draft knowledge graph and review queue
```

The user does not approve an intermediate task package. Each gate is automatic,
but automatic eligibility is not factual acceptance:

- source candidates remain candidates until source review;
- chain nodes, edges, entities, and claims remain draft or candidate records;
- only existing evidence-review rules may promote records to accepted facts;
- a valid URL is not sufficient evidence for a claim.

A completed bootstrap means all three stages produced parseable, persisted
drafts and their gates ran. A failed gate produces `partial`, names the failed
checks and retained checkpoint, and never appears as `completed`.

Task-package mode remains available and must say that it created a task package,
not completed industry research. Credential-free public bootstrap remains a
separate model-free path.

## Provider configuration and diagnostics

The API form uses the manifest model as its editable initial value rather than
only a placeholder. It rejects an empty model and obvious provider labels such
as `OpenAI` in the model field while continuing to allow provider-specific model
identifiers.

A configured API is always editable. The user can:

- replace the model, API base, authentication type, or key;
- clear the stored API configuration;
- run an explicit real connection test before research;
- see whether the test checked authentication only or model/tool execution.

The real OpenAI probe uses the configured Responses endpoint and verifies the
configured model. Bootstrap also requires web search; the probe therefore
checks the required web-search tool instead of declaring a key usable from
string presence alone. The UI warns that this explicit probe may consume a
small amount of API quota.

Provider errors are normalized at the adapter boundary. A displayed error may
contain HTTP status, provider error type/code, safe parameter name, message, and
request ID. It must not contain request headers, the API key, or the complete
request body. Unsupported model, unsupported tool, authentication, quota, rate
limit, timeout, and transport failures have distinct categories and recovery
instructions. IntDog does not silently remove web search and continue with a
weaker research contract.

## Stage execution and gates

### 1. Sources

The provider receives the source-discovery prompt. IntDog parses the JSON,
normalizes publisher and URL fields, performs bounded reachability checks, and
runs the existing source-structure audit. Sources that are useful but not
automatically reachable remain manual-reading candidates.

The source gate evaluates the candidate batch for category, publisher, region,
primary-source, URL, and reachability coverage. Passing makes the batch eligible
as input to this bootstrap run; it does not activate the sources globally. A
failed gate stops downstream model calls and returns `partial` with exact gaps.

### 2. Value chain

The value-chain prompt includes a bounded, normalized representation of the
eligible source batch. IntDog parses nodes and explicit directed edges, then
runs the chain audit. Nodes require inputs, outputs, order, and references;
edges keep their own evidence rather than borrowing node citations. A failed
gate stops entity discovery and returns `partial`.

### 3. Entities

The entity prompt includes the eligible sources and normalized chain. The
coverage gate checks cited entities across every chain stage and applicable
China/global and entity-type dimensions. An honest coverage gap is retained as
a gap and does not cause fabricated filler. Successful output is persisted as a
review-required draft graph.

Stage payloads are bounded before inclusion in subsequent prompts. Oversized or
malformed provider output fails with a typed error rather than being truncated
into apparently valid JSON.

## State, idempotency, and retry

Each bootstrap has one canonical task run. Its checkpoint records the workflow
version, provider/model fingerprint, prompt version, completed stages, stage
artifact references, gate results, and active candidate campaign ID. Credentials
are never checkpointed.

Stage artifacts are written to run-scoped temporary files and atomically
published after parsing and gate evaluation. Source campaigns are created only
after a successful source response and are reused by the same run. Failure
before that point creates no campaign or research artifact.

Safe retry performs provider preflight first. It reuses a completed stage only
when its industry, workflow version, provider/model, prompt version, and input
fingerprint still match; otherwise it restarts from the first invalid stage.
Retry never creates a second campaign for the same accepted checkpoint.

Only one mutating operation per industry executes at a time. Later operations
remain visibly `queued` in submission order instead of starting and failing on
the industry lock. Users may cancel a queued operation. Read-only browsing and
operations for other industries remain available.

## Progress and error presentation

The CLI emits one canonical machine-readable progress form that the job runtime
maps to the task ledger. Bootstrap has the following determinate milestones:

- provider preflight: 5%;
- source request, validation, and gate: 10%, 25%, 35%;
- chain request, validation, and gate: 40%, 55%, 65%;
- entity request, validation, and gate: 70%, 85%, 95%;
- atomic draft publication: 100%.

While an external request is in flight, the UI shows the current stage and
elapsed time without inventing sub-progress. The log retains representative
stage starts, gate outcomes, retry decisions, and final artifact locations.

The authoritative task error uses the normalized provider or gate failure. A
generic subprocess exit code may be secondary detail but cannot replace the
actual cause.

## Desktop journey

The connection step and the later connection settings use the same component
and visual language. A configured provider shows its provider, model, last probe
result, and actions for Edit, Test, and Clear. Field help distinguishes Provider
from model ID and gives the manifest default as an example.

The bootstrap screen shows three persistent stage rows with `waiting`,
`running`, `passed`, `partial`, `failed`, or `skipped` state, plus the current
message and elapsed time. A terminal result offers only relevant actions:

- configuration failure: Edit connection, then retry;
- gate gap: Review gaps or retry discovery;
- transient provider failure: Retry from checkpoint;
- success: Open sources, value chain, entities, or industry overview.

Submitting one bootstrap disables duplicate submission for that industry. Other
research actions explain that they will queue behind the active operation.

## Compatibility and ownership

- SQLite remains authoritative for task status and checkpoints; compatibility
  JSON files may expose drafts but do not own workflow state.
- Existing `/generate`, `/jobs`, retry, cancel, setup, and workflow-setting APIs
  remain compatible. New probe or stage-detail responses are additive.
- Existing provider adapters keep their public `complete()` contract. Shared
  error normalization is implemented once at the provider boundary.
- No new runtime dependency is introduced unless the implementation proves the
  current Python, FastAPI, React, Electron, and SQLite stack cannot satisfy an
  acceptance criterion.
- README and onboarding documents must describe the implemented behavior in
  complete Chinese and English versions.

## Acceptance criteria

| ID | Observable result |
| --- | --- |
| BW-01 | Entering `OpenAI` as the model is rejected before a task is queued and the manifest default is shown as an editable value. |
| BW-02 | A configured API remains editable, testable, and clearable without deleting industry data. |
| BW-03 | OpenAI 400 fixtures for invalid model and unsupported tool display their safe provider message, code, parameter, and request ID; no secret is persisted or rendered. |
| BW-04 | A successful fake-provider bootstrap executes sources, chain, then entities once, persists a review-required draft, and reports 100%. |
| BW-05 | A failed source or chain gate makes downstream call count zero and returns `partial` with exact gate results. |
| BW-06 | A provider failure before a valid source response creates no source campaign or stage artifact. |
| BW-07 | Retry after a configuration correction resumes from the first invalid checkpoint and does not duplicate an eligible source campaign. |
| BW-08 | Two mutating tasks for one industry execute serially; the second remains queued and can be cancelled. Tasks for different industries may run independently. |
| BW-09 | UI tests cover new user, invalid API configuration, successful probe, three-stage success, partial gate, queued-behind-task, retry, and reopen states using accessible controls. |
| BW-10 | Desktop tests prove credential redaction and the edit/test/clear bridge lifecycle; packaged smoke tests prove first launch, bootstrap UI, close, and reopen on each available native runner. |
| BW-11 | Task-package completion is labelled as a generated task package and never as completed industry research. |
| BW-12 | Existing industry data remains readable and no migration promotes historical candidate content. |

Real paid-provider success cannot be claimed from fixtures. A release may state
that the OpenAI interface is contract-tested only after a redaction-safe,
explicitly authorized live probe also passes; otherwise the limitation remains
visible.
