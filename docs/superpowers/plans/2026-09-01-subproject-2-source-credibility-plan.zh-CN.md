# 子项目 2：数据可信度与来源覆盖引擎实施计划

> **执行要求：** 使用 `superpowers:subagent-driven-development` 按任务执行并双阶段审查。

**目标：** 建立持久化的两轮来源发现、候选选择、人工审查、周期复核、去重与开放世界覆盖。
**架构：** 来源活动与候选使用独立 repository mixin；现有来源表继续保存激活目录；prompt 只产生候选，不控制状态机。
**技术栈：** Python、SQLite、FastAPI、React、确定性评分与可注入检索适配器。
**规格：** `docs/superpowers/specs/2026-09-01-subproject-2-source-credibility.zh-CN.md`

## 全局约束

- 每类目标 8–10，但质量门槛优先；不足必须显式。
- 官方一手来源只有身份/所有权/URL 全部通过才可自动激活。
- 网络、限流和预算错误只能暂停，不能记为收敛。
- 不删除历史文档或证据；不运行生产爬取或付费模型。

---

### 任务 1：持久化来源活动、查询、候选与审查

**文件：**
- Create: `DomainIntelSearch/intdog_core/source_repository.py`
- Modify: `DomainIntelSearch/intdog_core/repository.py`
- Test: `DomainIntelSearch/tests/test_source_campaigns.py`

**接口：**

```python
class SourceRepositoryMixin:
    def create_source_campaign(self, folder: str, targets: list[str], budget: int) -> dict: ...
    def record_source_query(self, campaign_id: str, *, round_no: int,
                            language: str, family: str, dimensions: dict,
                            query: str, outcome: dict) -> dict: ...
    def upsert_source_candidate(self, campaign_id: str, item: dict) -> dict: ...
    def review_source_candidate(self, folder: str, candidate_id: str, *,
                                decision: str, actor: str, reason: str) -> dict: ...
```

- [ ] **Step 1: 写 Schema 15 RED 测试**

覆盖迁移幂等、规范 URL 唯一性、同候选多查询溯源、同一 Publisher 跨行业复用但保持行业独立状态、审查历史不可覆盖、活动状态合法转换。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_source_campaigns.py -q`

- [ ] **Step 3: 实现 Schema 15 和 repository mixin**

状态：`planned→running→paused/converged/failed`；候选：`candidate→manual_review/active/reserve/rejected`。

- [ ] **Step 4: 运行 GREEN 与旧来源回归**

Run: `python -m pytest DomainIntelSearch/tests/test_source_campaigns.py DomainIntelSearch/tests/test_intdog_core.py DomainIntelSearch/tests/test_dedup_governance.py -q`

### 任务 2：实现双语查询族与两轮活动状态机

**文件：**
- Create: `DomainIntelSearch/src/source_campaign.py`
- Modify: `DomainIntelSearch/src/source_discovery.py`
- Modify: `DomainIntelSearch/src/coverage_execution.py`
- Modify: `DomainIntelSearch/src/research_bootstrap.py`
- Test: `DomainIntelSearch/tests/test_source_campaigns.py`

**接口：**

```python
@dataclass(frozen=True)
class CampaignOutcome:
    status: Literal["paused", "converged", "running"]
    qualified_by_category: dict[str, int]
    candidate_total: int
    stopping_reason: str

def plan_query_families(industry: dict, gaps: list[dict]) -> list[dict]: ...
def run_campaign_round(repo, campaign_id: str, *, search: SearchAdapter) -> CampaignOutcome: ...
```

- [ ] **Step 1: 写 RED 状态与边界测试**

验证中文/英文查询、九类别、第一轮权威基线、第二轮缺口扩展、候选池大于入选目标、连续两轮零新增才收敛，以及超时/403/429/预算不足为 paused。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_source_campaigns.py DomainIntelSearch/tests/test_coverage_planning.py -q`

- [ ] **Step 3: 实现纯状态机并让 prompt 只返回候选**

删除“可访问即 active”的行为；`execute_coverage()` 只写 candidate 与查询结果。

- [ ] **Step 4: 运行 GREEN 与 bootstrap 回归**

Run: `python -m pytest DomainIntelSearch/tests/test_source_campaigns.py DomainIntelSearch/tests/test_coverage_planning.py DomainIntelSearch/tests/test_core.py -q`

### 任务 3：实现身份、代表性、组合与周期复核

**文件：**
- Modify: `DomainIntelSearch/intdog_core/source_trust.py`
- Modify: `DomainIntelSearch/src/source_governance.py`
- Create: `DomainIntelSearch/src/source_review.py`
- Test: `DomainIntelSearch/tests/test_dedup_governance.py`

- [ ] **Step 1: 写 RED 决策表**

覆盖官方自动激活、媒体/自媒体必须人工、同所有者重复、来源换所有者、内容农场、长期零边际收益、手动添加、各类 7/8/10/11 个边界和中国缺口优先。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_dedup_governance.py -q`

- [ ] **Step 3: 实现可解释评分与审查结果**

每个结果必须输出 `score_components`、`decision`、`reason`、`review_due_at`；硬编码域只是身份提示，不是唯一验证途径。

- [ ] **Step 4: 运行 GREEN**

Run: `python -m pytest DomainIntelSearch/tests/test_dedup_governance.py DomainIntelSearch/tests/test_source_campaigns.py -q`

### 任务 4：补全 Document/Assertion 去重和冲突门槛

**文件：**
- Modify: `DomainIntelSearch/src/deduplication.py`
- Modify: `DomainIntelSearch/src/verification.py`
- Modify: `DomainIntelSearch/intdog_core/evidence_repository.py`
- Test: `DomainIntelSearch/tests/test_dedup_governance.py`
- Test: `DomainIntelSearch/tests/test_agent_evidence.py`

- [ ] **Step 1: 写 RED 属性与变形测试**

同 URL 跟踪参数、同内容不同 URL、转载、跨语言相同事件、同所有者多站点和独立发布者必须得到不同且稳定的归并结果；输入顺序改变不影响输出。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_dedup_governance.py DomainIntelSearch/tests/test_agent_evidence.py -q`

- [ ] **Step 3: 实现关系保留与 disputed 状态**

归并 Document 不删除 source/document 关系；相反断言写入冲突组，禁止 accepted 覆盖。

- [ ] **Step 4: 运行 GREEN**

Run: `python -m pytest DomainIntelSearch/tests/test_dedup_governance.py DomainIntelSearch/tests/test_agent_evidence.py -q`

### 任务 5：构建实体与产业链开放世界覆盖循环

**文件：**
- Create: `DomainIntelSearch/src/entity_coverage.py`
- Modify: `DomainIntelSearch/src/knowledge_model.py`
- Modify: `DomainIntelSearch/intdog_core/chain_repository.py`
- Modify: `DomainIntelSearch/src/coverage_execution.py`
- Test: `DomainIntelSearch/tests/test_entity_coverage.py`

**接口：**

```python
@dataclass(frozen=True)
class CoverageFrontier:
    cells: list[dict]
    entity_queries: list[dict]
    relation_queries: list[dict]
    stopping_reason: str | None

def build_coverage_matrix(repo, folder: str) -> dict: ...
def plan_entity_frontier(matrix: dict, *, round_no: int) -> CoverageFrontier: ...
def resolve_entity_candidate(repo, folder: str, candidate: dict) -> dict: ...
```

- [ ] **Step 1: 写 RED 覆盖、消歧和收敛测试**

覆盖十类对象、适用产业链阶段、中国/外国地区、空单元、每单元 2/3/8/10 边界、高中心性端点加深、别名、同名异体、机构更名、并购前后、官网/注册标识冲突、无证据关系和连续两轮零边际收益。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_entity_coverage.py DomainIntelSearch/tests/test_coverage_planning.py -q`

- [ ] **Step 3: 实现覆盖矩阵、扩展前沿与人工合并边界**

适用单元以 3 个合格代表为初始广度门槛，高价值端点以 8–10 个为深度目标；不足保留 gap。关系必须关联 Document/Assertion；身份不确定返回 `manual_review`，不得自动合并。

- [ ] **Step 4: 运行 GREEN 与知识图谱回归**

Run: `python -m pytest DomainIntelSearch/tests/test_entity_coverage.py DomainIntelSearch/tests/test_coverage_planning.py DomainIntelSearch/tests/test_intdog_core.py -q`

### 任务 6：来源、覆盖活动 API 与审查工作台

**文件：**
- Modify: `DomainIntelWeb/api/schemas.py`
- Modify: `DomainIntelWeb/api/routers/sources.py`
- Modify: `DomainIntelWeb/api/routers/intelligence.py`
- Modify: `DomainIntelWeb/src/features/SourcesPage.tsx`
- Create: `DomainIntelWeb/src/features/sources/SourceCampaignPanel.tsx`
- Modify: `DomainIntelWeb/src/test/workflows.test.tsx`

- [ ] **Step 1: 写 RED API/DOM 测试**

覆盖创建活动、分页候选、查询账本、来源缺口、覆盖矩阵、实体扩展前沿、身份复核、重新评估，以及来源不足 8 个或实体单元不足门槛时的完整说明。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelWeb/tests/test_api.py -q && npm test --prefix DomainIntelWeb`

- [ ] **Step 3: 实现强类型 API 与 UI**

UI 状态包括 candidate、active、manual、reserve、rejected、paused、converged；覆盖视图同时显示产业链阶段、实体类别、地区、当前深度、目标、缺口和关系证据。所有动作保留审查说明。

- [ ] **Step 4: 生成契约并运行子项目门禁**

Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### 任务 7：跨日信号动量、自身漂移与列式层触发器

**文件：**
- Create: `DomainIntelSearch/intdog_core/observability_repository.py`
- Create: `DomainIntelSearch/src/signal_momentum.py`
- Create: `DomainIntelSearch/src/quality_drift.py`
- Modify: `DomainIntelWeb/api/routers/intelligence.py`
- Test: `DomainIntelSearch/tests/test_signal_observability.py`

- [ ] **Step 1: 写 RED 时间序列与漂移测试**

覆盖首次出现、连续升温/跟踪/降温、缺日、长期未解决、跨 04:00、排名并列、独立来源增长、重复转载、同输入重跑、算法版本切换、七/三十日窗口、零分母和固定评估集退化；用基准 fixture 检查四个 Parquet/DuckDB 触发条件。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_signal_observability.py -q`

- [ ] **Step 3: 实现不可变观测、确定动量和漂移诊断**

日观测保存 rank/score/独立发布者/证据强度/分类/算法版本；API 返回昨日差异、七日趋势、指标分母/基线/阈值和原始观测链接。只记录列式原型触发状态，不引入 DuckDB/Parquet 依赖或第二写入路径。

- [ ] **Step 4: 运行 GREEN 与性能门禁**

Run: `python -m pytest DomainIntelSearch/tests/test_signal_observability.py DomainIntelWeb/tests/test_api.py -q`
