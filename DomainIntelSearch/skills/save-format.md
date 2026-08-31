# 能力：保存格式契约

写入前阅读 `DomainIntelData/README.md` 和 `DomainIntelData/skill/spec.md`。二者是人类可读契约，
可执行真值由 `intdog_core` Schema、application service 和测试共同约束，不得只修改
spec 就假定程序会自动适配。

## 当前目录

```text
DomainIntelData/
├── intdog.sqlite3
├── _jobs/
├── _trash/
└── <Industry>/
    ├── sources.json
    ├── one_time/{knowledge,research,reports,tasks}/
    └── periodic/{daily,weekly,monthly,quarterly}/
```

SQLite 是规范事实源；来源、每日条目、实体和产业链 JSON 是可对账重建的兼容视图。
业务写入必须经过 `IntDogService`/`IndustryStore`，不直接同时改 SQLite 和 JSON。

## 最低证据契约

- 文档必须有 `title`、有效 `url`、`source`、发布/发现时间和 `category`。
- 结论使用 `references[]`；数值带 `as_of/currency/unit/definition`。
- 区分 `evidence_status` 和 `review_status`；模型文本默认 `draft_review_required`。
- 全文 UTF-8，内部相对路径使用 POSIX 形式，禁止越出行业根目录。
