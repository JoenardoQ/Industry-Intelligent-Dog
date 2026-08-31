# 子项目 1：权威契约与 Agent 证据闭环实施计划

> **执行要求：** 使用 `superpowers:subagent-driven-development` 按任务执行；每项先规格审查，再代码质量审查。所有步骤使用复选框跟踪。

**目标：** 建立强类型 Agent Bridge、断言级复核与不可越级的事实提升路径。
**架构：** 原始 JSON 作为不可变产物，SQLite 作为查询与状态权威；`claims.status=accepted` 代表 Fact 投影。
**技术栈：** Python 3.12、SQLite、FastAPI/Pydantic、React/TypeScript、Vitest。
**规格：** `docs/superpowers/specs/2026-09-01-subproject-1-agent-evidence.zh-CN.md`

## 全局约束

- 不删除或改写现有 Agent 结果文件；迁移必须幂等。
- 不把 Agent 自报 tier 当作来源身份。
- 每个响应必须进入 OpenAPI；前端不得新增手写平行 DTO。
- 当前不授权 commit、push、真实付费调用或发布；计划中的检查点不创建提交。

---

### 任务 1：持久化 Agent 结果与断言状态机

**文件：**
- Create: `DomainIntelSearch/intdog_core/evidence_repository.py`
- Modify: `DomainIntelSearch/intdog_core/repository.py`
- Test: `DomainIntelSearch/tests/test_agent_evidence.py`

**接口：**

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

- [ ] **Step 1: 写 RED 状态机与迁移测试**

覆盖 Schema 13→14、重复迁移、重复导入保留复核、`draft→accepted` 被拒绝、opinion 不改变知识统计、accepted 才创建/提升 claim。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_agent_evidence.py -q`
Expected: 因 `EvidenceRepositoryMixin` 或 Schema 14 不存在而失败。

- [ ] **Step 3: 最小实现 Schema 14 与 mixin**

新增 `agent_results`、`agent_assertions`、`agent_citations`、`agent_result_reviews`；在同一事务内索引结果、断言与引用。允许动作仅为：

```python
ALLOWED = {
    "draft_review_required": {"rejected", "opinion", "submitted_for_verification"},
    "submitted_for_verification": {"candidate", "disputed", "accepted", "rejected"},
}
```

- [ ] **Step 4: 运行 GREEN 与迁移回归**

Run: `python -m pytest DomainIntelSearch/tests/test_agent_evidence.py DomainIntelSearch/tests/test_intdog_core.py -q`

- [ ] **Step 5: 审查检查点**

确认没有修改生产数据、旧迁移顺序和现有 claim/evidence 语义。

### 任务 2：建立强类型 Agent Bridge

**文件：**
- Modify: `DomainIntelWeb/api/schemas.py`
- Modify: `DomainIntelWeb/api/routers/agent_bridge.py`
- Modify: `DomainIntelWeb/api/main.py`
- Test: `DomainIntelWeb/tests/test_api.py`

**产生类型：** `AgentProfilePage`、`AgentTaskPage`、`AgentTaskExport`、`AgentResultState`、`AgentResultPage`、`AgentReviewRequest`、`AgentVerificationState`。

- [ ] **Step 1: 写 RED API 合同测试**

断言所有十个端点具有具体响应 Schema；列表限制、Profile 100 条/256 KiB、结果 500 KiB、损坏文件、未知任务、无引用、重复导入和路径攻击均有确定状态码。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelWeb/tests/test_api.py -q`
Expected: result detail/review 未出现在 OpenAPI，响应模型缺失。

- [ ] **Step 3: 用 repository 替换文件扫描状态权威**

原始文件仍由 `_atomic_json()` 写入；随后调用 `service.repo.index_agent_result(...)`。重复导入从 SQLite 返回当前状态，不从输入重建状态。

- [ ] **Step 4: 为所有路由声明 response_model 并运行 GREEN**

Run: `python -m pytest DomainIntelWeb/tests/test_api.py DomainIntelSearch/tests/test_agent_evidence.py -q`

### 任务 3：实现断言核验与事实提升门槛

**文件：**
- Create: `DomainIntelSearch/src/agent_evidence.py`
- Modify: `DomainIntelSearch/intdog_core/source_trust.py`
- Modify: `DomainIntelWeb/api/routers/agent_bridge.py`
- Test: `DomainIntelSearch/tests/test_agent_evidence.py`

**接口：**

```python
@dataclass(frozen=True)
class VerificationDecision:
    disposition: Literal["candidate", "disputed", "accepted", "rejected"]
    checks: dict[str, dict]
    claim_id: str | None

def verify_agent_assertion(repo, folder: str, assertion_id: str,
                           *, fetch: Callable[[str], Probe]) -> VerificationDecision: ...
```

- [ ] **Step 1: 写 RED 决策表测试**

覆盖 URL 不可达、发布者未知、发布时间缺失、实体歧义、现有 accepted claim 冲突、引用不支持/部分支持/明确矛盾、缺少定位器、定位器内容哈希变化、数字/符号/数量级/单位/币种/期间/口径不一致、合法换算、同所有者伪独立、各声明类型的 0/1/2 个独立集群、因果/预测/观点禁止自动提升，以及重复核验。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_agent_evidence.py -q`

- [ ] **Step 3: 实现声明级充分性检查与原子提升**

每道检查返回 `{status, reason, evidence_ids, locators}`；增加原子化、语义支持、证据定位、数值一致性和按声明类型佐证策略。任何 `failed/partial/unknown` 禁止 accepted，冲突进入 disputed。核验不得直接信任 Agent 的来源说明，也不得让同一生成调用成为唯一语义裁判。

- [ ] **Step 4: 运行 GREEN 与知识统计回归**

Run: `python -m pytest DomainIntelSearch/tests/test_agent_evidence.py DomainIntelSearch/tests/test_intdog_core.py -q`

### 任务 4：完成可读复核 UI 与生成契约

**文件：**
- Create: `DomainIntelWeb/src/features/research/AgentReviewPanel.tsx`
- Modify: `DomainIntelWeb/src/features/ResearchPage.tsx`
- Modify: `DomainIntelWeb/src/api.ts`
- Modify: `DomainIntelWeb/src/styles.css`
- Modify: `DomainIntelWeb/src/test/workflows.test.tsx`
- Generate: `DomainIntelWeb/openapi.json`
- Generate: `DomainIntelWeb/src/generated/openapi.ts`

- [ ] **Step 1: 写 RED DOM 测试**

断言文本、引用链接、复核说明、三种动作、逐项核验结果和失败原因可见；点击提交发送正确 action。

- [ ] **Step 2: 运行 RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: 实现组件并删除 Agent Bridge 手写 DTO**

组件从生成 Schema 派生 props；链接使用安全外部打开策略，按钮在请求中禁用并保留错误状态。

- [ ] **Step 4: 生成并核对契约**

Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`

- [ ] **Step 5: 子项目门禁**

Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### 任务 5：完成 Agent 能力目录、安全发现与分级适配

**文件：**
- Modify: `DomainIntelSearch/src/services/capability_manifest.py`
- Modify: `DomainIntelSearch/src/services/agent_registry.py`
- Modify: `DomainIntelSearch/src/services/provider_readiness.py`
- Modify: `DomainIntelSearch/src/services/provider_factory.py`
- Modify: `DomainIntelWeb/api/routers/agent_bridge.py`
- Test: `DomainIntelSearch/tests/test_provider_interfaces.py`
- Create: `DomainIntelSearch/tests/test_agent_discovery.py`

**接口：**

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

- [ ] **Step 1: 写 RED 能力与恶意配置测试**

覆盖 Codex/Claude 原生 CLI、OpenAI/Anthropic/DeepSeek/Qwen 与通用兼容 API、MCP、任务包、WorkBuddy/其他受限 CLI、未知 Agent、缺失 executable、伪版本输出、路径空格、超时、超大输出、shell 元字符和凭据不回显。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_provider_interfaces.py DomainIntelSearch/tests/test_agent_discovery.py DomainIntelWeb/tests/test_api.py -q`

- [ ] **Step 3: 实现声明式 Manifest、保守发现和强类型诊断 API**

原生 direct 白名单只收录已有稳定适配器且通过诊断的 CLI；兼容 API 通过显式 base URL/认证类型配置；其余默认 handoff/import-only。发现只检查 PATH、已知应用标识和用户选择路径，不扫描用户文档或读取凭据正文。

- [ ] **Step 4: 运行 GREEN 与子项目完整门禁**

Run: `python -m pytest DomainIntelSearch/tests/test_provider_interfaces.py DomainIntelSearch/tests/test_agent_discovery.py DomainIntelSearch/tests/test_agent_evidence.py DomainIntelWeb/tests/test_api.py -q`
Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`
