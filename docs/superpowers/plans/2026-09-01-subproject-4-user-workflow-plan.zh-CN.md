# 子项目 4：完整用户工作流实施计划

> **执行要求：** 使用 `superpowers:subagent-driven-development`；每个页面任务在规格审查后再做视觉与可访问性审查。

**目标：** 把所有已实现核心能力组织成用户可完成、可理解、可恢复的现代研究工作台。
**架构：** 页面按功能目录拆分；只消费生成 OpenAPI 类型；共享状态组件统一 loading/empty/partial/stale/error/ready。
**技术栈：** React 19、TypeScript、Vite、React Testing Library、Vitest、react-markdown。
**规格：** `docs/superpowers/specs/2026-09-01-subproject-4-user-workflow.zh-CN.md`

## 全局约束

- 不做新的视觉辅助流程；依据已批准的现代、低饱和度、易读方向实现。
- 正文 ≥16px、辅助文字 ≥14px、长文本行高 ≥1.6、支持 200% 缩放。
- 页面不手写 Provider、Agent 或 API 响应清单。
- UI 不得掩盖未知、部分和失败状态。

---

### 任务 1：生成类型成为唯一前端合同

**文件：**
- Create: `DomainIntelWeb/src/api/client.ts`
- Create: `DomainIntelWeb/src/api/runtime.ts`
- Modify: `DomainIntelWeb/src/api.ts`
- Modify: `DomainIntelWeb/src/generated/openapi.ts`
- Test: `DomainIntelWeb/tests/test_frontend_contract.py`

- [ ] **Step 1: 写 RED 合同测试**

禁止 `api.ts` 重复定义生成 Schema；所有 feature API 路径必须属于 `ApiPath`；Markdown/Artifact 请求使用会话客户端。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelWeb/tests/test_frontend_contract.py -q`

- [ ] **Step 3: 拆分客户端与最小运行时守卫**

`api<TPath extends ApiPath>()` 统一会话头、错误 envelope、取消与 JSON 解析；特性文件从生成类型导入。

- [ ] **Step 4: 运行 GREEN 与构建**

Run: `python -m pytest DomainIntelWeb/tests/test_frontend_contract.py -q && npm run build --prefix DomainIntelWeb`

### 任务 2：首次引导与行业概览闭环

**文件：**
- Create: `DomainIntelWeb/src/features/setup/DiagnosticsStep.tsx`
- Create: `DomainIntelWeb/src/features/setup/ConnectionStep.tsx`
- Create: `DomainIntelWeb/src/features/setup/IndustryStep.tsx`
- Create: `DomainIntelWeb/src/features/setup/BootstrapStep.tsx`
- Modify: `DomainIntelWeb/src/features/SetupWizard.tsx`
- Modify: `DomainIntelWeb/src/features/OverviewPage.tsx`
- Modify: `DomainIntelWeb/src/features/shared.tsx`
- Test: `DomainIntelWeb/src/test/onboarding.test.tsx`

- [ ] **Step 1: 写 RED 首次流程测试**

覆盖无模型、CLI、API、MCP；诊断失败；来源→产业链→实体门槛；取消/恢复；重开；行业创建/切换/重命名/导入/导出/回收站恢复；概览计数链接和持久有向边。

- [ ] **Step 2: 运行 RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: 实现四步向导与链接指标**

首次任务在页面内显示阶段和失败行动，不立即把用户抛到无上下文任务列表。

- [ ] **Step 4: 运行 GREEN**

Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`

### 任务 3：每日、知识、来源与产物工作区

**文件：**
- Modify: `DomainIntelWeb/src/features/DailyPage.tsx`
- Create: `DomainIntelWeb/src/features/KnowledgePage.tsx`
- Modify: `DomainIntelWeb/src/features/SourcesPage.tsx`
- Modify: `DomainIntelWeb/src/features/ProductsPage.tsx`
- Create: `DomainIntelWeb/src/features/artifacts/ArtifactReader.tsx`
- Modify: `DomainIntelWeb/src/App.tsx`
- Modify: `DomainIntelWeb/package.json`
- Modify: `DomainIntelWeb/package-lock.json`
- Test: `DomainIntelWeb/src/test/content-workflows.test.tsx`

- [ ] **Step 1: 写 RED 行为测试**

覆盖 04:00 窗口、标题/类别/来源/发布时间排序、分页选择、跨页全选、恢复删除、实体筛选/详情、来源复核、六个平行周期按钮，以及统一产物元数据、引用、目录、GFM 表格/代码、搜索、可视化 sidecar 和恶意 HTML/URL 不执行。

- [ ] **Step 2: 运行 RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: 实现聚焦组件**

把列表工具栏、选择模型、实体详情、来源审查卡和 ArtifactReader 拆为各自目录组件；ArtifactReader 使用 `react-markdown`、GFM 与 sanitize 插件，不复制加载/错误逻辑。

- [ ] **Step 4: 运行 GREEN**

Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`

### 任务 4：研究、Lab、任务与系统恢复工作区

**文件：**
- Modify: `DomainIntelWeb/src/features/ResearchPage.tsx`
- Modify: `DomainIntelWeb/src/features/JobsPage.tsx`
- Modify: `DomainIntelWeb/src/features/SystemPage.tsx`
- Create: `DomainIntelWeb/src/features/research/ArtifactWorkbench.tsx`
- Test: `DomainIntelWeb/src/test/research-operations.test.tsx`

- [ ] **Step 1: 写 RED 工作流测试**

覆盖 Agent 复核、来源活动、覆盖计划、长周期门槛、研究/报告/Lab 直接生成、任务阶段日志、暂停/重试/恢复和后台服务状态。

- [ ] **Step 2: 运行 RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: 实现统一操作与状态呈现**

删除 `document.body.innerHTML` 关闭方式；使用可访问确认对话框和 Electron/Local API 生命周期动作。

- [ ] **Step 4: 运行 GREEN**

Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`

### 任务 5：设计系统、可访问性与真实 renderer 烟雾

**文件：**
- Create: `DomainIntelWeb/src/styles/tokens.css`
- Create: `DomainIntelWeb/src/styles/layout.css`
- Create: `DomainIntelWeb/src/styles/components.css`
- Modify: `DomainIntelWeb/src/styles.css`
- Modify: `DomainIntelWeb/src/test/setup.ts`
- Modify: `DomainIntelWeb/scripts/browser_smoke.cjs`
- Modify: `DomainIntelDesktop/src/main.cjs`

- [ ] **Step 1: 写 RED 可访问性覆盖**

为全部路由加入 axe、键盘、焦点恢复、长中英文、空/错误状态、窄屏和 200% 缩放测试；移除未使用测试依赖或实际使用 `vitest-axe`。

- [ ] **Step 2: 运行 RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: 实现 token 与组件样式分层**

状态同时使用文字/图标；选择框、表格、卡片、Markdown 与长日志具有统一间距和换行。

- [ ] **Step 4: 运行子项目门禁**

Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb && npm test --prefix DomainIntelDesktop`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### 任务 6：便携单文件简报与成品质量门

**文件：**
- Create: `DomainIntelSearch/src/artifact_quality.py`
- Create: `DomainIntelSearch/src/portable_briefing.py`
- Modify: `DomainIntelSearch/src/report_tasks.py`
- Modify: `DomainIntelWeb/src/features/DailyPage.tsx`
- Modify: `DomainIntelWeb/src/features/ProductsPage.tsx`
- Test: `DomainIntelSearch/tests/test_artifact_quality.py`
- Test: `DomainIntelWeb/src/test/portable-briefing.test.tsx`

- [ ] **Step 1: 写 RED 成品与离线合同**

覆盖缺证据、空泛/异常短/占位/重复段落、缺日期/来源、损坏 sidecar、坏 Markdown 链接/锚点；单文件 HTML 断言无外部脚本/CDN、后端关闭且禁网时可搜索/筛选/收藏/打印，并与 Markdown 使用同一内容/证据 manifest。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_artifact_quality.py -q && npm test --prefix DomainIntelWeb`

- [ ] **Step 3: 实现确定质量门与自包含导出**

质量门独立于 Fact 状态，失败写入机器可读原因并把产物标记 `partial`。HTML 只内嵌转义后的 JSON、CSS 和固定本地脚本；收藏写浏览器 localStorage，不写回 IntDog 数据库。

- [ ] **Step 4: 运行 GREEN 与离线浏览器烟雾**

Run: `python -m pytest DomainIntelSearch/tests/test_artifact_quality.py -q && npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`
