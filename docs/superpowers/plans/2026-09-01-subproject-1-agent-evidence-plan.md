# Subproject 1: Authoritative Contract and Agent Evidence Loop Implementation Plan

> **Execution requirement:** Use `superpowers:subagent-driven-development` to execute tasks; perform a specification review before each item, followed by a code-quality review. Track all steps with checkboxes.

**Objective:** Establish a strongly typed Agent Bridge, assertion-level review, and a fact-promotion path that cannot skip levels.
**Architecture:** Original JSON is an immutable artifact, SQLite is authoritative for queries and state; `claims.status=accepted` represents the Fact projection.
**Tech stack:** Python 3.12, SQLite, FastAPI/Pydantic, React/TypeScript, Vitest.
**Specification:** `docs/superpowers/specs/2026-09-01-subproject-1-agent-evidence.md`

## Global Constraints

- Do not delete or rewrite existing Agent result files; migrations must be idempotent.
- Do not treat an Agent-reported tier as source identity.
- Every response must enter OpenAPI; the frontend must not add handwritten parallel DTOs.
- Commit, push, real paid calls, and publication are not authorized; checkpoints in this plan do not create commits.

---

### Task 1: Persist Agent Results and the Assertion State Machine

**Files:**
- Create: `DomainIntelSearch/intdog_core/evidence_repository.py`
- Modify: `DomainIntelSearch/intdog_core/repository.py`
- Test: `DomainIntelSearch/tests/test_agent_evidence.py`

**Interfaces:**

```python
class EvidenceRepositoryMixin:
    def index_agent_result(self, folder: str, record: dict, raw_path: str) -> dict: ...
    def list_agent_results(self, folder: str, *, limit: int, offset: int) -> dict: ...
    def get_agent_result(self, folder: str, result_id: str) -> dict: ...
    def review_agent_assertion(self, folder: str, assertion_id: str, *,
                               decision: str, actor: str, note: str) -> dict: ...
    def apply_assertion_verification(self, folder: str, assertion_id: str, *,
                                     checks: dict, disposition: str) -> dict: ...
```

- [ ] **Step 1: Write RED state-machine and migration tests**

Cover Schema 13→14, repeated migration, review preservation on repeated import, rejection of `draft→accepted`, opinion not changing knowledge statistics, and creation/promotion of a claim only for accepted results.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_agent_evidence.py -q`
Expected: fail because `EvidenceRepositoryMixin` or Schema 14 does not exist.

- [ ] **Step 3: Minimal implementation of Schema 14 and the mixin**

Add `agent_results`, `agent_assertions`, `agent_citations`, and `agent_result_reviews`; index results, assertions, and citations in the same transaction. Allowed actions are only:

```python
ALLOWED = {
    "draft_review_required": {"rejected", "opinion", "submitted_for_verification"},
    "submitted_for_verification": {"candidate", "disputed", "accepted", "rejected"},
}
```

- [ ] **Step 4: Run GREEN and migration regression**

Run: `python -m pytest DomainIntelSearch/tests/test_agent_evidence.py DomainIntelSearch/tests/test_intdog_core.py -q`

- [ ] **Step 5: Review checkpoint**

Confirm that production data, the order of old migrations, and existing claim/evidence semantics were not modified.

### Task 2: Establish the Strongly Typed Agent Bridge

**Files:**
- Modify: `DomainIntelWeb/api/schemas.py`
- Modify: `DomainIntelWeb/api/routers/agent_bridge.py`
- Modify: `DomainIntelWeb/api/main.py`
- Test: `DomainIntelWeb/tests/test_api.py`

**Generated types:** `AgentProfilePage`, `AgentTaskPage`, `AgentTaskExport`, `AgentResultState`, `AgentResultPage`, `AgentReviewRequest`, `AgentVerificationState`.

- [ ] **Step 1: Write RED API contract tests**

Assert that all ten endpoints have concrete response Schemas; list limits, 100 Profiles/256 KiB, 500 KiB results, corrupted files, unknown tasks, missing citations, repeated imports, and path attacks have deterministic status codes.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelWeb/tests/test_api.py -q`
Expected: result detail/review do not appear in OpenAPI, and response models are missing.

- [ ] **Step 3: Replace file-scan status authority with the repository**

Original files are still written by `_atomic_json()`; then call `service.repo.index_agent_result(...)`. Repeated imports return the current state from SQLite rather than rebuilding state from the input.

- [ ] **Step 4: Declare `response_model` for every route and run GREEN**

Run: `python -m pytest DomainIntelWeb/tests/test_api.py DomainIntelSearch/tests/test_agent_evidence.py -q`

### Task 3: Implement Assertion Verification and Fact-Promotion Gates

**Files:**
- Create: `DomainIntelSearch/src/agent_evidence.py`
- Modify: `DomainIntelSearch/intdog_core/source_trust.py`
- Modify: `DomainIntelWeb/api/routers/agent_bridge.py`
- Test: `DomainIntelSearch/tests/test_agent_evidence.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class VerificationDecision:
    disposition: Literal["candidate", "disputed", "accepted", "rejected"]
    checks: dict[str, dict]
    claim_id: str | None

def verify_agent_assertion(repo, folder: str, assertion_id: str,
                           *, fetch: Callable[[str], Probe]) -> VerificationDecision: ...
```

- [ ] **Step 1: Write RED decision-table tests**

Cover unreachable URLs, unknown publishers, missing publication times, ambiguous entities, conflicts with existing accepted claims, unsupported/partially supported/explicitly contradicted citations, missing locators, changed locator content hashes, inconsistencies in numbers/signs/order of magnitude/units/currencies/periods/statistical definitions, valid conversions, false independence under common ownership, zero/one/two independent clusters for each assertion type, prohibition on automatic promotion of causal/forecast/opinion assertions, and repeated verification.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_agent_evidence.py -q`

- [ ] **Step 3: Implement assertion-level sufficiency checks and atomic promotion**

Each check returns `{status, reason, evidence_ids, locators}`; add atomization, semantic support, evidence location, numeric consistency, and assertion-type corroboration strategies. Any `failed/partial/unknown` result prohibits `accepted`, and conflicts enter `disputed`. Verification must not directly trust the Agent’s source description or allow the same generation call to be the sole semantic judge.

- [ ] **Step 4: Run GREEN and knowledge-statistics regression**

Run: `python -m pytest DomainIntelSearch/tests/test_agent_evidence.py DomainIntelSearch/tests/test_intdog_core.py -q`

### Task 4: Complete the Readable Review UI and Generated Contract

**Files:**
- Create: `DomainIntelWeb/src/features/research/AgentReviewPanel.tsx`
- Modify: `DomainIntelWeb/src/features/ResearchPage.tsx`
- Modify: `DomainIntelWeb/src/api.ts`
- Modify: `DomainIntelWeb/src/styles.css`
- Modify: `DomainIntelWeb/src/test/workflows.test.tsx`
- Generate: `DomainIntelWeb/openapi.json`
- Generate: `DomainIntelWeb/src/generated/openapi.ts`

- [ ] **Step 1: Write RED DOM tests**

Assert that assertion text, citation links, review explanation, three actions, itemized verification results, and failure reasons are visible; clicking submit sends the correct action.

- [ ] **Step 2: Run RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: Implement the component and remove handwritten Agent Bridge DTOs**

Derive component props from generated Schemas; use a secure external-opening policy for links, disable buttons during requests, and retain error states.

- [ ] **Step 4: Generate and verify the contract**

Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`

- [ ] **Step 5: Subproject gate**

Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### Task 5: Complete the Agent Capability Catalog, Secure Discovery, and Tiered Adapters

**Files:**
- Modify: `DomainIntelSearch/src/services/capability_manifest.py`
- Modify: `DomainIntelSearch/src/services/agent_registry.py`
- Modify: `DomainIntelSearch/src/services/provider_readiness.py`
- Modify: `DomainIntelSearch/src/services/provider_factory.py`
- Modify: `DomainIntelWeb/api/routers/agent_bridge.py`
- Test: `DomainIntelSearch/tests/test_provider_interfaces.py`
- Create: `DomainIntelSearch/tests/test_agent_discovery.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class AgentCapability:
    id: str
    connection: Literal["native_cli", "api", "mcp", "taskpack", "restricted_cli"]
    execution_level: Literal["direct", "handoff", "import_only"]
    auth: str
    web_access: bool | None
    structured_output: bool
    schedulable: bool

def discover_local_agents(*, path: str, selected_executables: list[str]) -> list[dict]: ...
def diagnose_agent(profile: dict, *, timeout_seconds: int = 10) -> dict: ...
```

- [ ] **Step 1: Write RED capability and malicious-configuration tests**

Cover Codex/Claude native CLIs, OpenAI/Anthropic/DeepSeek/Qwen and generic compatible APIs, MCP, task packages, WorkBuddy/other restricted CLIs, unknown Agents, missing executables, fake version output, paths with spaces, timeouts, oversized output, shell metacharacters, and credential non-disclosure.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_provider_interfaces.py DomainIntelSearch/tests/test_agent_discovery.py DomainIntelWeb/tests/test_api.py -q`

- [ ] **Step 3: Implement declarative Manifest, conservative discovery, and strongly typed diagnostic API**

The native direct allowlist contains only existing stable adapters whose CLIs pass diagnosis; compatible APIs use explicit base URL/authentication-type configuration; all others default to handoff/import-only. Discovery checks only PATH, known application identifiers, and user-selected paths; it does not scan user documents or read credential contents.

- [ ] **Step 4: Run GREEN and the complete subproject gate**

Run: `python -m pytest DomainIntelSearch/tests/test_provider_interfaces.py DomainIntelSearch/tests/test_agent_discovery.py DomainIntelSearch/tests/test_agent_evidence.py DomainIntelWeb/tests/test_api.py -q`
Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`
