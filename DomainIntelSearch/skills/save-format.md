# 能力：保存格式契约（save-format）

> 这是**最重要**的一份说明。所有能力产生的数据，都必须按这里的约定
> 写进 DomainIntelData。先读懂它，再去跑别的能力。

## 唯一事实来源
`DomainIntelData/skill/spec.md` 是**唯一契约**。
DomainIntelSearch 启动时用 `src/spec_loader.py` 读取它，决定：
- **抓取哪些领域**（spec 的「抓取领域」清单）
- **保存成什么格式**（spec 的「保存格式」约定）

DomainIntelApp 也按它来展示。**改格式只改 spec.md，不改代码。**

## 目录契约（默认实现）
```
DomainIntelData/
├── skill/spec.md              # 本契约（唯一事实来源）
├── domains/<领域id>/          # 领域文本信息（md/json）
├── images/<领域id>/           # 领域图片
├── data/<年>/<日期>/<类别>.json   # 每日抓取的原始情报
├── reports/<类型>/            # HTML/MD 报告
├── db/intelligence.db         # SQLite 查询库（可选）
├── index/master_index.json    # 总索引（相对路径，可整体拷贝）
└── industry/<领域名>/         # 深度研究产物（任务包 + 回写 + 图谱）
```

## 单条情报必须包含的字段
```json
{
  "title": "标题",
  "url": "原文链接（必须，溯源用）",
  "source": "来源（如 36氪 / arXiv）",
  "published": "YYYY-MM-DD",
  "summary": "摘要",
  "category": "news|academic|finance|policy|startup",
  "references": [ {"title":"...", "url":"...", "source":"...", "date":"..."} ]
}
```

## 引用溯源（硬性要求）
- 每条情报必须有 `url`；每条总结/结论必须用 `[n]` 标注来源并在文末附 `references[]`。
- 没有来源链接的结论视为不合格，应重新生成或标注"来源待补"。

## 跨平台约束
- `index/master_index.json` 内部一律用相对 POSIX 路径 → 整个 DomainIntelData 可拷到任何系统。
- 文件名只用 ASCII 安全字符。
- 文本一律 UTF-8。

## 给 agent 的要点
1. 写数据前，先 `load_spec("DomainIntelData")` 拿到 domains/format，按其写。
2. 用户若在 spec.md「用户待规定」里改了格式，**优先遵守用户**。
3. 拿不准时，宁可多带 `references`，不要少。
