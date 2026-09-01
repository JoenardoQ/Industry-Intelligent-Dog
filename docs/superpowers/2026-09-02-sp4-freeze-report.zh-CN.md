# SP4 用户工作流冻结报告

日期：2026-09-02

## 冻结范围

- 行业概览、每日情报、知识结构、来源审核、研究助手、研究产物、任务中心与系统状态。
- 研究/Lab/行业报告/周期产物直接生成、统一安全阅读、有向产业链、后台任务状态与恢复。
- 确定性成品质量门与无需 IntDog 后端的便携单文件 HTML。

## SP4 C 结果

质量门独立保存 `fact_state` 与 `artifact_status`。它检查：正文长度、占位/空泛/重复段落、结构化结论证据、每个二级重点条目的摘要/日期/来源、Markdown 协议与内部锚点、可视化 sidecar。失败写入稳定的机器可读 `code`，产物状态降为 `partial`，不会修改事实审核状态。

周期、行业、深度与影响报告共同生成：

- Markdown 正文；
- `.manifest.json` 内容/证据清单；
- `.quality.json` 成品检查结果；
- `.portable.html` 离线单文件。

离线 HTML 内嵌转义后的 manifest、固定脚本和样式，无 `fetch`、CDN 或外部脚本，并设置禁止连接的 CSP。它支持搜索、来源/状态/产业链筛选、本地收藏、打印/PDF、证据链接与审核状态。Daily 可直接导出；Products 和研究阅读器可直接打开或下载。

## 需求—测试追踪

| 需求 | 判定 oracle | 测试 |
|---|---|---|
| 质量门与事实状态分离 | `fact_state` 保持输入值；失败仅令 `artifact_status=partial` | `test_artifact_quality.py` |
| 缺口产生机器码 | 指定失败集合包含长度、占位、重复、链接、锚点、证据缺失 | `test_artifact_quality.py` |
| 单文件离线 | 无外部脚本/CDN/fetch；脚本终止标签被转义；具有筛选、收藏、打印 | `test_artifact_quality.py` |
| 报告生成链接入 | 报告元数据包含 quality、portable 路径且文件存在 | `test_report_generation.py` |
| Daily API 导出 | typed API 返回受管路径，输出满足离线合同 | `test_api.py::test_daily_portable_export_is_offline_and_typed` |
| App 阅读入口 | 离线链接和机器质量码可读 | `content-workflows.test.tsx` |

## 冻结门禁

- Python focused：10/10 通过。
- Web DOM/axe focused：33/33 通过。
- Web production build：通过。
- Desktop focused：3/3 通过。
- `node --check`（browser smoke、Electron main）：通过。
- `git diff --check`：通过。

未执行真实 Playwright browser smoke：本机没有 Playwright/Chromium，且本任务禁止联网安装。现有 smoke 脚本为无截图 DOM 检查；运行时验证仍是发行前外部条件。未运行全仓测试、联网、视觉辅助、提交或推送。
