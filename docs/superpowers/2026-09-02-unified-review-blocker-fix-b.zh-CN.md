# 最终统一审查阻断修复 B

日期：2026-09-02

## 范围

本次冻结只关闭本地产品闭环与发行合同阻断；未联网、未安装原生服务、未触碰用户数据、
未运行 CI、未提交，也未发布。

## 已实现

- 新增可注入的公开免凭据 Feed bootstrap。只有真实抓取且具有发布者身份、时间、内容哈希、
  实体证据和持久关系证据的 Document 才计入 NOM-01；不足时为 `partial`，种子和任务包不能过门。
- 生成 API、CLI、首次引导、产物页和研究工作台显式贯通 `taskpack | direct`。direct 必须指定
  且就绪的 Provider；任务包保持 `waiting_for_agent`；CLI 不再隐式回退 Codex。
- 原生 NOM 记录绑定隔离数据根、数据库哈希、任务账本和零 Provider 调用账本。NOM 外部缺口
  不再跳过无关生命周期步骤；卸载保留验收比较文件哈希与 SQLite integrity。
- 补全架构 path filters，并实现 Issue 查找、复用、缺失时创建与 readback 幂等流程。
- 新增单 SQL Story 动量批量读取、Daily 动量摘要/时间线和 System 七日/三十日质量漂移。
- 半年、两年、五年按钮分别生成 `tech_6m`、`popular_2y`、`trend_5y`；direct 成文前先回填对应周期。
- 报告图只使用持久证据边；无边时显示明确 gap。产物质量门新增悬空编号、Document/Evidence、
  sidecar schema 与 data reference 校验。
- 中英文追踪矩阵已更新到当前实现状态。邮件仅保留不可启用的兼容表面，配置和环境变量均不能开启。

## focused 证据

- Python 产品/发行/观测 focused 门禁：`31 passed`。
- 最终缩短 Python 闭环门禁：`21 passed`。
- 调度器/API 显式执行模式兼容门禁：`7 passed`。
- Web DOM/axe：`33 passed`；renderer 生产构建通过。
- Desktop workflow contract 通过。
- OpenAPI 与生成的 TypeScript 合同已成功重建。

以上只是 focused 证据，不代表全仓回归通过。

## 外部门禁

实时 NOM-01 仍须在三个原生安装包中满足严格 oracle。Windows/macOS/Linux 生命周期和服务变更、
原生凭据存储、真实已登录 Agent、Windows 签名、macOS 签名与公证、下载字节 checksum，以及
GitHub Release/Issue 第二次运行 readback 仍是外部门禁。本报告未把任何外部门禁写成 passed。
