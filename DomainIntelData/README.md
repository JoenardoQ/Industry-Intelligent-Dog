# DomainIntelData —— 数据层

> **只负责存储**：按行业分目录保存领域情报（文本 + 图片）+ 格式契约 `skill/spec.md`。
> 这里**不放任何代码**。

## 它是数据的「家」
- DomainIntelSearch 把所有抓到的内容写到这里。
- DomainIntelApp 从这里读取、展示、删除。
- 整个文件夹可直接拷贝到任何电脑 / U盘 / 网盘，数据不丢。

## 目录结构（按行业分目录）
```
DomainIntelData/
├── skill/spec.md              # ★ 唯一契约：抓哪些领域 + 保存成什么格式
│
├── Chips/                     # 一个行业一个文件夹（例：芯片）
│   ├── control.json           #   定期更新开关 + 调度记录
│   ├── sources.json           #   信息源（博客/平台/自媒体/新闻/期刊/财报/金融）
│   ├── one_time/              #   一次性深度爬取
│   │   ├── knowledge/         #     三层知识：行业→产业链→实体
│   │   │   ├── industry.json
│   │   │   ├── chains.json
│   │   │   └── entities.json  #     实体含 企业/高校研究组
│   │   └── reports/           #     行业报告（5年趋势/2年流行/半年技术）+ tasks.json
│   └── periodic/              #   定期监控（与一次性分开）
│       ├── daily/<日期>/      #     每天：news/github/funding/hiring/ceo/papers.json
│       ├── weekly/            #     每周行业总结
│       ├── monthly/           #     每月产业分析
│       └── quarterly/         #     每季财报分析
│
├── AI/                        # 另一个行业（例：人工智能），结构同上
├── _archive/                  # 旧版扁平归档（daily/weekly 等旧命令写入处）
└── _trash/                    # 删除的定期产物回收站（可恢复）
```

## 每条定期情报长这样（JSON）
```json
{
  "title": "标题",
  "abstract": "摘要",
  "url": "原文链接（可溯源）",
  "source": "来源（如 36氪 / GitHub / arXiv）",
  "date": "YYYY-MM-DD",
  "category": "news|github|funding|hiring|ceo|papers"
}
```

## skill/spec.md —— 你只需要关心这个文件
它是 Search 与 App 之间的**唯一契约**：规定抓哪些领域、保存成什么格式。
该文件定义数据契约，但不是可执行 DSL。修改字段后必须同步更新 Search 写入器、App 读取器和测试。

## 跨平台与备份
- 文本一律 UTF-8；文件名只用 ASCII 安全字符。
- 每个行业自成一体（Chips/、AI/…），可单独拷贝某个行业。

## 边界
- 本目录**不联网、不跑代码**。
- 写入由 DomainIntelSearch 负责；读取/删除由 DomainIntelApp 负责。
