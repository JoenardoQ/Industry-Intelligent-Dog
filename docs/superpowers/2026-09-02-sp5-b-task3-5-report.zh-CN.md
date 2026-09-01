# SP5 B 任务 3–5 冻结报告

日期：2026-09-02

## 结果

- 所有架构敏感路径会从显式相同 revision 触发 Windows、macOS、Linux；每个任务 checkout 后回读 revision。
- 复用 workflow 执行 Python/Web/Desktop、冻结 CLI/API/Worker、renderer/原生生命周期门禁，并输出测试日志、生命周期状态、单平台制品、SHA-256 与 revision 证据。
- 三个平台保持独立安装包和 Pre-release。Windows 正式签名、macOS 签名/公证受凭据门槛保护。Release 更新幂等：先 `view`，存在则 `upload --clobber` 与 `edit`，不存在才创建。
- 中英文用户文档已对齐三平台安装、摘要校验、首次启动、无模型与任务包区别、Agent/API、后台权限/撤销、凭据传递、数据位置、卸载保留、Beta 警告和当前外部缺口。
- 旧线程 Worker 与明文 OpenAI 配置脚本在四证审计后删除。源码/WSL 启动器仍有有效脚本和测试依赖，因此保留为 developer-only，并排除出发行资源。

## 覆盖台账

| ID | 风险与 oracle | focused 证据 | 剩余缺口 |
| --- | --- | --- | --- |
| WF-01 | 共享变更以同 revision 触发三平台 | workflow 合同通过 | 未触发托管 runner |
| WF-02 | Worker/renderer、报告、SHA-256、单平台输出 | workflow 合同通过 | 本地未构建原生安装包 |
| WF-03 | Beta/正式签名与幂等 Release | workflow 合同通过 | 签名凭据属于外部条件 |
| DOC-01 | 双语用户/运维合同 | release-doc 测试通过 | 未做人类可用性研究 |
| RET-01 | 四证删除与经过测试的替代 | retired-surface 测试与审计通过 | 开发启动器有意保留 |
| RET-02 | manifest 排除可变/敏感/生成垃圾 | 合成路径分区与 staged manifest 检查通过 | 最终安装器库存需原生构建 |

## 验证

- Workflow 合同：3 passed。
- Release-doc 与 retired-surface focused：7 passed。
- Packaged-command 生命周期 focused：通过。
- Workflow YAML 解析、Python compile、仓库结构检查与 scoped `git diff --check`：通过。

未运行全仓、联网、CI、原生服务变更、用户数据操作、commit、push、Issue 或 Release 写入。
`NOM-01`、原生安装器/服务/卸载、签名与真实已登录 Agent 仍是外部缺口。
