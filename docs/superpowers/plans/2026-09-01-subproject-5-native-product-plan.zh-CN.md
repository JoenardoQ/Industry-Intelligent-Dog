# 子项目 5：三平台产品化与 Beta 门禁实施计划

> **执行要求：** 使用 `superpowers:subagent-driven-development`；Windows、macOS、Linux 原生任务可在共享本地门禁通过后并行验证。

**目标：** 为同一源码版本生成三个可安装 Beta 包，并验证完整首次流程、后台任务、安全凭据和数据保留。
**架构：** 一个 PyInstaller sidecar 提供 API/CLI/Worker；Electron 打包最小显式资源；复用原生 workflow 统一门禁。
**技术栈：** PyInstaller、Electron 44、electron-builder、GitHub Actions 原生 runner。
**规格：** `docs/superpowers/specs/2026-09-01-subproject-5-native-product.zh-CN.md`

## 全局约束

- 三个平台必须来自同一 Git SHA；旧包不计入证据。
- 未签名 Windows/macOS 只能 Pre-release；稳定版需要签名，macOS 需要公证。
- 卸载程序不得删除用户行业数据。
- 本轮已通过“完整交付”批准满足普通 commit、push 到 `origin/main`、已有三平台 CI、幂等 Issue 更新/缺失时创建及门禁成功后 Pre-release 的外部动作授权点；force push、历史改写、签名/公证、API 计费和用户生产数据删除仍不在授权范围内。

---

### 任务 1：冻结完整 API/CLI/Worker 资源

**文件：**
- Modify: `DomainIntelApp/packaging/entry.py`
- Modify: `DomainIntelApp/packaging/build_sidecar.py`
- Modify: `DomainIntelDesktop/scripts/prepare_resources.py`
- Modify: `DomainIntelDesktop/electron-builder.yml`
- Test: `DomainIntelApp/tests/test_packaged_commands.py`
- Test: `DomainIntelDesktop/test/runtime.test.cjs`

- [ ] **Step 1: 写 RED 资源清单测试**

断言冻结入口支持 serve/cli/worker，服务模板与 Web/config/evaluation/skills 均进入显式资源，安装包不包含 DomainIntelData、开发 venv 或密钥。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelApp/tests/test_packaged_commands.py -q && npm test --prefix DomainIntelDesktop`

- [ ] **Step 3: 实现入口与确定性资源清单**

`prepare_resources.py` 先在临时目录组装并生成 `resource-manifest.json`，再原子替换 build/resources。

- [ ] **Step 4: 构建并烟雾 sidecar**

Run: `python DomainIntelDesktop/scripts/prepare_resources.py`
Run: `python DomainIntelApp/packaging/build_sidecar.py`
Run: `python DomainIntelDesktop/scripts/smoke_sidecar.py --executable DomainIntelDesktop/build/backend/intdog-runtime`

### 任务 2：扩展真实安装包生命周期烟雾

**文件：**
- Modify: `DomainIntelDesktop/scripts/smoke_desktop.py`
- Create: `DomainIntelDesktop/scripts/smoke_background_service.py`
- Modify: `DomainIntelDesktop/src/main.cjs`
- Test: `DomainIntelDesktop/test/runtime.test.cjs`

- [ ] **Step 1: 写 RED 生命周期合同**

标记文件必须证明 install/mount、first-run、`NOM-01` 真实公开免凭据采集 oracle、reference Agent/API contract、secure credential、service install、window close、background run、reopen、data persistence 和 app uninstall/data retained；另定义真实已登录 Agent CLI 的有界、脱敏、非 mock 验收记录。

- [ ] **Step 2: 运行 RED 单元合同**

Run: `npm test --prefix DomainIntelDesktop`

- [ ] **Step 3: 实现原生 smoke 状态机**

每一步有超时和诊断产物；失败不得继续后续步骤或把残留进程当作通过。

- [ ] **Step 4: 在可用本地主机运行对应平台烟雾**

Linux 本地只作为补充；Windows/macOS 的权威结果来自各自 runner。

- [ ] **Step 5: 在明确授权且已登录的用户环境运行一次真实 Agent 深度烟雾**

只发送固定的小型公开测试任务，不包含用户数据；记录 Agent 类型、能力、退出状态、结构化结果导入和断言停留在待复核状态，不记录 prompt 凭据或原始环境。登录无效或未授权时记为外部验收缺口，不用 mock 冒充。

### 任务 3：强化三平台 CI 与制品证明

**文件：**
- Modify: `.github/workflows/platform-gates.yml`
- Modify: `.github/workflows/_native-package.yml`
- Modify: `.github/workflows/release-windows.yml`
- Modify: `.github/workflows/release-macos.yml`
- Modify: `.github/workflows/release-linux.yml`

- [ ] **Step 1: 写静态 workflow RED 测试**

Create: `DomainIntelDesktop/test/workflow_contract.test.cjs`，解析 YAML 文本并断言完整 path filters、Worker smoke、renderer smoke、SHA-256、测试报告、同 SHA gate 和签名条件。

- [ ] **Step 2: 运行 RED**

Run: `npm test --prefix DomainIntelDesktop`

- [ ] **Step 3: 更新 workflow**

平台 gate 必须覆盖 `DomainIntelSearch/pyproject.toml`、Web package/config、所有 launcher/packaging/worker 文件。每个平台上传安装包、`.sha256` 和测试报告。

- [ ] **Step 4: 运行 GREEN 与 YAML/仓库检查**

Run: `npm test --prefix DomainIntelDesktop && python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### 任务 4：双语安装、引导与发行状态对账

**文件：**
- Modify: `README.md`, `README.zh-CN.md`
- Modify: `DomainIntelApp/README.md`, `DomainIntelApp/README.zh-CN.md`
- Modify: `docs/onboarding-and-installation.md`, `.zh-CN.md`
- Modify: `docs/release-readiness.md`, `.zh-CN.md`
- Modify: `IMPLEMENTATION_STATUS.md`, `.zh-CN.md`
- Modify: `DESIGN.md`, `DESIGN.zh-CN.md`

- [ ] **Step 1: 写 RED 文档合同测试**

Create: `DomainIntelWeb/tests/test_release_docs.py`，验证双语结构、安装命令、无模型流程、Agent/API、后台权限、数据位置、卸载保留、Beta 警告和当前 revision 状态一致。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelWeb/tests/test_release_docs.py -q`

- [ ] **Step 3: 更新全部双语文档并运行 GREEN**

Run: `python -m pytest DomainIntelWeb/tests/test_release_docs.py -q`

### 任务 5：审计并退役旧架构与构建垃圾

**文件：**
- Modify/Delete after audit: `DomainIntelSearch/src/services/worker.py`
- Modify/Delete after audit: `DomainIntelApp/launch_intdog.py`
- Modify/Delete after audit: `DomainIntelApp/windows_launcher.ps1`
- Modify/Delete after audit: `DomainIntelApp/configure_openai_api.ps1`
- Modify/Delete after audit: `DomainIntelApp/configure_openai_api.bat`
- Modify: `DomainIntelSearch/scripts/check_repo.py`
- Create: `DomainIntelWeb/tests/test_retired_surfaces.py`

- [ ] **Step 1: 写 RED 发行面与引用合同**

验证生产源码、README、安装器、package/workflow 不引用已退役 Worker、WSL 专用快捷方式或明文 API 配置；发行清单拒绝 venv、DomainIntelData、历史安装包、测试输出、缓存和密钥。

- [ ] **Step 2: 生成逐项保留/迁移/删除清单**

对候选文件运行 import/reference、文档、安装和替代路径检查。没有四项证据不得删除；仍有回归价值的测试迁移到当前合同，而不是批量清空测试目录。

- [ ] **Step 3: 用可恢复的小批次删除或降级为 dev-only**

只删除已证明无引用且替代门禁通过的文件；开发入口若保留，移动到明确 dev 文档并确保安装包不包含。不得删除用户数据目录或当前有效 fixture。

- [ ] **Step 4: 运行退役与完整回归**

Run: `python -m pytest DomainIntelWeb/tests/test_retired_surfaces.py DomainIntelApp/tests DomainIntelSearch/tests DomainIntelWeb/tests -q`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### 任务 6：发行前门禁与外部动作审批点

- [ ] **Step 1: 运行完整本地门禁**

Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `python -m ruff check DomainIntelSearch DomainIntelApp DomainIntelWeb`
Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb && npm test --prefix DomainIntelDesktop`
Run: `python DomainIntelSearch/scripts/check_repo.py && python -m compileall -q DomainIntelApp DomainIntelSearch DomainIntelWeb && git diff --check`

- [ ] **Step 2: 使用 `$clean-before-commit` 审计候选变更集**

不得在发现密钥、生产数据、构建垃圾、陈旧 fixture、无用依赖或未评估大文件时提交。

- [ ] **Step 3: 读取并记录 commit/push/CI/Pre-release 授权**

本审批包的“批准五个子项目并完整交付”及用户确认已满足普通 commit、push 到 `origin/main`、已有三平台 CI、幂等 Issue 和门禁成功后 Pre-release 的授权点；不包含 force push、历史改写、签名/公证、API 计费或用户数据删除。授权缺失或范围变化时停在本地 `NOT_READY_PENDING_NATIVE_GATES`。

- [ ] **Step 4: 授权后运行同 SHA 三平台门禁**

Windows、macOS、Linux 任一失败则不发布。先按平台标签/标题查找现有 Issue（当前文档记录 #1–#3），存在则更新，不存在才创建；Pre-release 也按 tag/revision 幂等复用或更新，不重复制造 Issue/Release。三个平台成功后才分别生成或更新公开 Beta Pre-release。
