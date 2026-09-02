#!/usr/bin/env python3
"""DomainIntelSearch - 命令行入口（抓取 / 研究，写入 DomainIntelData）.

本程序是"数据抓取层"，只负责从 AI 与网络抓取领域信息，并按
DomainIntelData/skill/spec.md 规定的格式写入 DomainIntelData。
它不绑定任何 agent 平台：可用 Codex / WorkBuddy / Claude Code / 自写脚本驱动，
也可自带联网 LLM（见 config/settings.yaml 的 llm.provider）。

用法：
  python -m src.main daily              # 运行每日情报采集
  python -m src.main weekly             # 运行每周金融政策简报
  python -m src.main timeline           # 生成近一年发展轨迹
  python -m src.main brief              # 生成一次性研究任务简报（模型无关任务包）
  python -m src.main collect --days 3   # 仅抓取原始数据（JSON）
  python -m src.main query --kw 芯片    # 查询 DomainIntelData（SQLite）
  python -m src.main serve              # 启动只读局域网服务，分享 DomainIntelData

IIOS 多 Agent 命令（规格见 IIOS_SPEC.md）：
  python -m src.main plan --industry 半导体 --level beginner --region global
                                        # Planner：生成任务 DAG + 全部研究任务包
  python -m src.main agent --name company --industry 半导体
                                        # 运行单个 Agent 产出任务包
  python -m src.main kg --build         # 构建知识图谱（entities/edges/events 入库）
  python -m src.main kg --entity 台积电 # 查询实体邻居子图

模块化与行业档案（src/modules/ + config/industries/）：
  python -m src.main modules            # 查看全部功能模块（含依赖关系）
  python -m src.main daily --industry 半导体
                                        # 用行业档案运行每日监控（可换 芯片/ai/机器人…）

按行业分目录 + 三层知识 + 定期监控（新版，数据存 DomainIntelData/<行业>/）：
  python -m src.main init-industry --industry 芯片      # 初始化行业（信息源+知识骨架+报告任务）
  python -m src.main discover-sources --industry 芯片   # 查看/扩充信息源
  python -m src.main report-tasks --industry 芯片       # 生成 5年/2年/半年 行业报告任务包
  python -m src.main crawl-daily --industry 芯片        # 每日抓取（新闻/论文/GitHub/融资/招聘/CEO）
  python -m src.main crawl-weekly --industry 芯片       # 每周行业总结
  python -m src.main crawl-monthly --industry 芯片      # 每月产业分析
  python -m src.main crawl-quarterly --industry 芯片    # 每季财报分析
  python -m src.main knowledge --industry 芯片          # 查看三层知识结构
  python -m src.main knowledge --industry 芯片 --name 英伟达 --etype company --chain 设计验证 --country 美国
  python -m src.main industries                         # 列出全部行业数据文件夹
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import BASE_DIR, load_config


COMMANDS = ["daily", "weekly", "timeline", "brief", "collect",
                 "archive", "query", "serve", "plan", "agent", "execute-tasks", "kg",
                 "modules",
                 "init-industry", "bootstrap-industry", "resume-bootstrap", "refresh-sources",
                 "public-bootstrap",
                 "discover-sources", "enrich-sources", "report-tasks",
                 "crawl-daily", "crawl-weekly", "crawl-monthly", "crawl-quarterly",
                 "generate-period", "generate-report", "generate-deep-report",
                 "generate-impact",
                 "execute-coverage", "run-source-campaign",
                 "backfill-history",
                 "knowledge", "industries", "migrate-data", "reconcile-data",
                 "verify", "doctor", "landscape", "impact", "deep-reports", "mcp-serve",
                 "compile-evidence", "observe-sources", "simulate-chain",
                 "plan-boundaries", "run-lab", "agenda-status",
                 "create-research-task", "audit-artifacts", "evaluate-quality"]

COMMAND_HELP = {
    "compile-evidence": "编译可追溯证据图",
    "observe-sources": "审计来源覆盖、活跃度和集中度",
    "simulate-chain": "执行产业链启发式情景传播",
    "plan-boundaries": "生成知识边界研究议程",
    "run-lab": "依次运行全部离线分析",
    "agenda-status": "更新研究议程状态",
    "create-research-task": "从议程创建受预算约束的研究任务包",
    "audit-artifacts": "校验版本化分析产物及 latest 指针",
    "evaluate-quality": "运行版本化 AI/Chips 质量评测门禁",
}


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=None, help="配置文件路径")
    common.add_argument("--folder", default="", help="数据文件夹名（默认取行业档案 data_folder）")
    common.add_argument("--days", type=int, default=1, help="抓取天数窗口")
    common.add_argument("--provider", default=None,
                        help="执行 provider（由 capability manifest 定义）")
    common.add_argument("--execution-mode", choices=["taskpack", "direct"], default=None,
                        help="显式执行模式；direct 必须同时提供 --provider")
    common.add_argument("--resume-task", default="",
                        help="仅用于安全重试初始化的父任务 ID")
    common.add_argument("--kw", default="", help="查询关键词（query 命令）")
    common.add_argument("--category", default="", help="查询类别（query 命令）")
    common.add_argument("--port", type=int, default=8765, help="服务端口（serve 命令）")
    common.add_argument("--host", default="127.0.0.1",
                        help="serve 监听地址（默认仅本机；局域网需显式设为 0.0.0.0）")
    # ---- IIOS 统一输入（IIOS_SPEC.md §2） ----
    common.add_argument("--industry", default="", help="行业名（覆盖配置 domain.name）")
    common.add_argument("--level", default="", choices=["", "beginner", "intermediate", "expert"],
                        help="用户水平")
    common.add_argument("--region", default="", choices=["", "global", "china", "us", "europe"],
                        help="区域视角")
    common.add_argument("--lang", default="", choices=["", "zh", "en", "both"], help="输出语言")
    common.add_argument("--name", default="", help="Agent 名（agent 命令）")
    common.add_argument("--build", action="store_true", help="构建图谱（kg 命令）")
    common.add_argument("--entity", default="", help="查询实体（kg 命令）")
    common.add_argument("--depth", type=int, default=1, help="子图深度（kg 命令）")
    # ---- knowledge 命令参数 ----
    common.add_argument("--etype", default="company", choices=["company", "research_group"],
                        help="实体类型（knowledge 命令）")
    common.add_argument("--chain", default="", help="所属产业链层级（knowledge 命令）")
    common.add_argument("--country", default="", help="国家/地区（knowledge 命令）")
    common.add_argument("--url", default="", help="链接（knowledge 命令）")
    common.add_argument("--desc", default="", help="描述（knowledge 命令）")
    # ---- 研究助手命令参数 ----
    common.add_argument("--event", default="", help="事件描述（impact 命令，如 '美国限制GPU出口'）")
    common.add_argument("--rtype", default="", help="深度报告类型（deep-reports 命令）")
    common.add_argument("--kind", default="", help="生成类型（周期或行业报告 ID）")
    common.add_argument("--task-file", default="", help="任务包 JSON（execute-tasks 命令）")
    common.add_argument("--hops", type=int, default=3,
                        help="产业链情景最大传播跳数（simulate-chain）")
    common.add_argument("--stale-days", type=int, default=30,
                        help="来源超过多少天未观察视为陈旧（observe-sources）")
    common.add_argument("--agenda-id", default="", help="研究议程 ID（agenda-status）")
    common.add_argument("--budget", type=int, default=20,
                        help="研究任务最多读取文档数（create-research-task）")
    common.add_argument("--target", type=int, default=0,
                        help="历史回填目标数；0 使用周期默认值")
    common.add_argument("--max-buckets", type=int, default=0,
                        help="本次最多处理的历史时间桶；0 处理全部，可用于分批续跑")
    common.add_argument("--campaign-id", default="",
                        help="要执行或恢复的来源检索活动 ID")
    common.add_argument("--coverage-round-id", default="",
                        help="要执行或恢复的实体/关系覆盖轮次 ID")
    common.add_argument("--repair-latest", action="store_true",
                        help="校验产物时重建 latest 指针")
    common.add_argument("--status", default="",
                        choices=["", "open", "in_progress", "done", "dismissed",
                                 "resolved_candidate"], help="研究议程状态")
    parser = argparse.ArgumentParser(description="Domain Intelligence System")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for command in COMMANDS:
        subparsers.add_parser(command, parents=[common], help=COMMAND_HELP.get(command, ""))
    return parser


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)

    # ---- 行业档案：--industry 对监控类命令同样生效（覆盖配置中的领域） ----
    PROFILE_CMDS = {"daily", "weekly", "timeline", "brief", "collect",
                    "plan", "agent", "execute-tasks", "kg"}
    if args.industry and args.command in PROFILE_CMDS:
        from src.profiles import find_profile, apply_profile, make_custom_profile
        profile = find_profile(args.industry)
        if profile is None and args.command in {"daily", "weekly", "timeline", "brief", "collect"}:
            from src.profiles import list_industries
            names = "、".join(f"{p['name']}({p['id']})" for p in list_industries())
            print(f"[错误] 未找到行业档案: {args.industry!r}。可选: {names}")
            sys.exit(1)
        if profile is None and args.command in {"plan", "agent", "execute-tasks", "kg"}:
            profile = make_custom_profile(args.industry)
        if profile is not None:
            cfg = apply_profile(cfg, profile)
            print(f"[行业] 已切换到档案：{profile['name']} ({profile['id']})")

    # Orchestrator 初始化会向 stdout 打印 spec 摘要；协议型命令（mcp-serve）必须保持
    # stdout 纯净，故按需懒构造——只有旧版监控/查询/serve/kg 命令真正用到 orch。
    NEEDS_ORCH = {"daily", "weekly", "timeline", "brief", "collect",
                  "archive", "serve"}
    if args.command in NEEDS_ORCH:
        from src.orchestrator import Orchestrator
        orch = Orchestrator(config=cfg)
    else:
        orch = None

    if args.command == "daily":
        r = orch.run_daily(since_days=args.days)
        print(f"[完成] 每日情报：新闻 {r['news_count']} | 学术 {r['academic_count']} "
              f"| 金融 {r['finance_count']} | 政策 {r['policy_count']}")
        print(f"  报告: {r['html_path']}")

    elif args.command == "weekly":
        r = orch.run_weekly(since_days=args.days)
        print(f"[完成] 每周简报：金融 {r['finance_count']} | 政策 {r['policy_count']} "
              f"| 市场 {r['market_count']}")
        print(f"  报告: {r['html_path']}")

    elif args.command == "timeline":
        r = orch.run_timeline(since_days=args.days)
        print(f"[完成] 发展轨迹：共 {r['count']} 条")
        print(f"  报告: {r['html_path']}")

    elif args.command == "brief":
        try:
            r = orch.analyze_domain(provider=args.provider)
        except Exception as exc:
            print(f"[错误] 研究任务执行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
            sys.exit(2)
        if r.get("mode") == "api":
            print(f"[完成] API 研究报告：{r['path']}")
            print(f"  provider={r['provider']} model={r['model']} metadata={r['metadata']}")
        elif "path" in r:
            print(f"[完成] 研究简报已生成: {r['path']}")
            print("  把该 brief 交给任何 agent/模型执行分析（Codex/WorkBuddy/Claude Code…），"
                  "回写结果到 DomainIntelData。")

    elif args.command == "collect":
        r = orch.collect_raw(since_days=args.days)
        out = Path(cfg.get("output", {}).get("data_dir", "./data")) / "raw_collect.json"
        from src.utils import save_json
        save_json(r, out)
        print(f"[完成] 抓取：新闻 {len(r['news'])} | 学术 {len(r['academic'])}")
        print(f"  数据: {out}")

    elif args.command == "archive":
        project_dir = BASE_DIR
        moved = orch.archive.migrate_existing(project_dir)
        st = orch.archive.stats()
        print(f"[完成] 历史迁移：报告 {moved.get('reports', 0)} 份 | 原始数据 {moved.get('raw', 0)} 条")
        print(f"[数据层统计] 共 {st['total']} 条 | 分类 {st['by_category']} | 位置 {st['root']}")

    elif args.command == "query":
        from intdog_core import IntDogService
        from src.profiles import find_profile, profile_folder
        from src.utils import data_root as canonical_data_root
        service = IntDogService(canonical_data_root(cfg))
        profile = find_profile(args.industry) if args.industry else None
        folders = ([args.folder] if args.folder else
                   ([profile_folder(profile)] if profile else
                    [row["folder"] for row in service.repo.list_industries()]))
        rows = []
        for folder in folders:
            for item in service.repo.search_documents(folder, args.kw or "*", limit=20):
                item["folder"] = folder; rows.append(item)
        if args.category:
            rows = [row for row in rows if row["category"] == args.category]
        rows = sorted(rows, key=lambda row: (row["observed_date"], -row["rank"]),
                      reverse=True)[:20]
        print(f"[查询] 关键词={args.kw!r} 类别={args.category!r} -> {len(rows)} 条")
        for row in rows:
            print(f"  [{row['folder']}|{row['observed_date']}|{row['category']}] "
                  f"{row['title'][:60]}")
            print(f"    {row['url']}")

    elif args.command in {"migrate-data", "reconcile-data"}:
        import json
        from intdog_core import IntDogService
        from src.utils import data_root as canonical_data_root
        service = IntDogService(canonical_data_root(cfg))
        folders = [args.folder] if args.folder else None
        if args.command == "migrate-data":
            stats = service.migrate_legacy(folders)
            print("[完成] 兼容数据已幂等导入 IntDog 结构化内核")
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        repaired = service.reconcile_compat(folders)
        print("[对账] SQLite → 兼容 JSON")
        print(json.dumps(repaired, ensure_ascii=False, indent=2))

    elif args.command == "evaluate-quality":
        import json
        from src.evaluation import evaluate_file
        fixtures = BASE_DIR / "evaluation" / "fixtures"
        paths = [Path(args.task_file)] if args.task_file else sorted(fixtures.glob("*-v*.json"))
        results = [evaluate_file(path) for path in paths]
        print(json.dumps(results, ensure_ascii=False, indent=2))
        if not all(result["passed"] for result in results):
            raise SystemExit(3)

    elif args.command == "plan":
        from src.agents import PlannerAgent
        from src.agents.base import AgentContext
        ctx = AgentContext.from_config(cfg,
                                       industry="" if cfg.get("_profile") else args.industry,
                                       level=args.level, region=args.region,
                                       lang=args.lang)
        records = PlannerAgent(ctx).run()
        tasks = [r for r in records if r.type == "task"]
        print(f"[完成] IIOS 研究计划: 行业={ctx.industry} 水平={ctx.level} 区域={ctx.region}")
        print(f"  知识库目录: {ctx.industry_dir}")
        print(f"  任务包: {len(tasks)-1} 个 Agent 任务（tasks/*.json）+ DAG (plan.mmd)")
        summary = records[-1]
        for step in summary.extra.get("next_steps", []):
            print(f"  {step}")

    elif args.command == "agent":
        from src.agents import AGENT_REGISTRY
        from src.agents.base import AgentContext
        if args.name not in AGENT_REGISTRY:
            print(f"[错误] 未知 Agent: {args.name!r}，可选: {', '.join(AGENT_REGISTRY)}")
            sys.exit(1)
        ctx = AgentContext.from_config(cfg,
                                       industry="" if cfg.get("_profile") else args.industry,
                                       level=args.level, region=args.region,
                                       lang=args.lang)
        agent = AGENT_REGISTRY[args.name](ctx)
        records = agent.run()
        tasks = [r for r in records if r.type == "task"]
        if tasks:
            bundle = agent.save_tasks(tasks, args.name)
            print(f"[完成] {args.name} 产出 {len(tasks)} 个任务包: {bundle}")
        for r in records:
            if r.type != "task":
                print(f"  [{r.type}] {r.title}: {r.summary[:80]}")

    elif args.command == "execute-tasks":
        if not args.task_file:
            parser.error("execute-tasks 必须提供 --task-file")
        from src.agents.base import AgentContext
        from src.services.task_executor import execute_bundle
        ctx = AgentContext.from_config(
            cfg, industry="" if cfg.get("_profile") else args.industry,
            level=args.level, region=args.region, lang=args.lang)
        try:
            result = execute_bundle(cfg, ctx, args.task_file, provider=args.provider)
        except Exception as exc:
            print(f"[错误] 任务包执行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
            sys.exit(2)
        print(f"[完成] 执行 {len(result['results'])} 个任务；产物均标记为 draft")
        print(f"  运行清单: {result['manifest']}")
        for item in result["results"]:
            print(f"  - {item.get('title', item['index'])}: {item['status']} "
                  f"{item.get('output_file', item.get('reason', ''))}")

    elif args.command == "kg":
        from src.agents.kg import KnowledgeGraphAgent
        from src.agents.base import AgentContext
        ctx = AgentContext.from_config(
            cfg, industry="" if cfg.get("_profile") else args.industry)
        kg_agent = KnowledgeGraphAgent(ctx)
        if args.entity:
            g = kg_agent.repo.graph_neighbors(kg_agent.folder, args.entity, depth=args.depth)
            print(f"[图谱] {args.entity!r} 邻居: {len(g['nodes'])} 实体 / {len(g['edges'])} 边")
            name_of = {n["id"]: n["canonical_name"] for n in g["nodes"]}
            for e in g["edges"][:20]:
                print(f"  {name_of.get(e['src_entity_id'], '?')} --{e['predicate']}--> "
                      f"{name_of.get(e['dst_entity_id'], '?')}")
        else:
            records = kg_agent.run()
            print(f"[完成] {records[0].title}")
            print(f"  {records[0].summary}")
            print(f"  图谱总量: {records[0].extra.get('knowledge_totals')}")

    elif args.command == "modules":
        from src.modules import list_modules
        from src.modules.runner import resolve_selection
        cat_label = {"collect": "数据采集", "report": "报告生成",
                     "research": "深度研究(LLM任务包)", "graph": "知识图谱"}
        grouped = {}
        for s in list_modules():
            grouped.setdefault(s.category, []).append(s)
        for cat, specs in grouped.items():
            print(f"\n【{cat_label.get(cat, cat)}】")
            for s in specs:
                req = f"  (依赖: {','.join(s.requires)})" if s.requires else ""
                net = "联网" if s.network else ("LLM任务包" if s.kind == "llm_task" else "代码")
                print(f"  {s.id:<26} {s.name:<10} [{net}]{req}")
                print(f"  {'':<26} {s.description}")
        # 展示一次依赖展开示例
        demo = resolve_selection(["daily_report"])
        print(f"\n[示例] 勾选 daily_report 实际执行顺序: {' → '.join(demo)}")

    # ==================================================================
    # 新版：按行业分目录 + 三层知识 + 定期监控
    # ==================================================================
    elif args.command in ("init-industry", "bootstrap-industry", "resume-bootstrap", "refresh-sources",
                          "public-bootstrap",
                          "discover-sources", "enrich-sources", "report-tasks",
                          "crawl-daily", "crawl-weekly", "crawl-monthly",
                          "crawl-quarterly", "generate-period", "generate-report",
                          "generate-deep-report", "generate-impact", "execute-coverage",
                          "run-source-campaign",
                          "backfill-history",
                          "knowledge", "industries",
                          "verify", "doctor", "landscape", "impact", "deep-reports",
                          "compile-evidence", "observe-sources", "simulate-chain",
                          "plan-boundaries", "run-lab", "agenda-status",
                          "create-research-task", "audit-artifacts"):
        from src.industry_store import IndustryStore, list_industries as list_data_industries
        from src.profiles import (find_profile, apply_profile, profile_folder,
                                  make_custom_profile)

        # 按行业分目录的数据层根（与旧扁平 archive.root 解耦）
        from src.utils import data_root as canonical_data_root
        data_root = canonical_data_root(cfg)

        # industries：仅列出数据文件夹，不需要行业档案
        if args.command == "industries":
            rows = list_data_industries(data_root)
            if not rows:
                print("[提示] DomainIntelData 下还没有行业文件夹，先运行 init-industry")
            for r in rows:
                flag = "🟢定期开" if r["periodic_enabled"] else "⚪定期关"
                print(f"  {r['folder']:<16} {flag}")
            return

        # 其余命令都需要定位行业
        profile = find_profile(args.industry) if args.industry else None
        if profile is None and args.industry:
            profile = make_custom_profile(args.industry)
        if profile is None and not args.folder:
            print("[错误] 请用 --industry 指定行业（如 芯片 / ai）或 --folder 指定数据文件夹")
            sys.exit(1)
        folder = args.folder or profile_folder(profile)
        pcfg = apply_profile(cfg, profile) if profile else cfg
        store = IndustryStore(data_root, folder,
                              name=(profile or {}).get("name", folder))
        if profile is None:
            metadata = store._read_json(store.knowledge / "industry.json", {})
            store.name = str(metadata.get("name") or folder)

        direct_commands = {"generate-period", "generate-report", "generate-deep-report",
                           "generate-impact", "execute-coverage", "run-source-campaign"}
        taskpack_commands = {"report-tasks", "impact", "deep-reports"}
        if args.command in direct_commands:
            if args.execution_mode != "direct" or not args.provider:
                parser.error(f"{args.command} requires --execution-mode direct and --provider")
        if args.command in taskpack_commands and args.execution_mode not in {None, "taskpack"}:
            parser.error(f"{args.command} only supports --execution-mode taskpack")

        if args.command == "public-bootstrap":
            if args.execution_mode != "direct" or args.provider != "public_sources":
                parser.error("public-bootstrap requires --execution-mode direct --provider public_sources")
            from src.public_bootstrap import ReviewedFeedAdapter, collect_public_bootstrap
            result = collect_public_bootstrap(
                ReviewedFeedAdapter(store), industry=store.name,
                output_dir=store.one_time / "research" / "bootstrap", store=store)
            print(__import__("json").dumps(result, ensure_ascii=False))
            if result["status"] != "completed":
                sys.exit(4)

        elif args.command == "init-industry":
            from src.source_discovery import (seed_sources, build_discovery_task,
                                              merge_sources)
            from src.report_tasks import build_report_tasks
            from src.knowledge_model import KnowledgeModel
            # 1) 种子信息源 + 发现任务包
            seed = seed_sources(store.name, (profile or {}).get("name_en", ""), profile)
            existing_sources = store.get_sources()
            if existing_sources:
                seed = merge_sources(existing_sources, seed)
                seed["industry"] = store.name
            store.save_sources(seed)
            task = build_discovery_task(store.name, (profile or {}).get("name_en", ""))
            task_path = store.save_task("source_discovery", task)
            # 2) 三层知识骨架
            km = KnowledgeModel(store.knowledge)
            existing_industry = km.get_industry()
            km.set_industry(
                store.name, (profile or {}).get("name_en", ""),
                description=existing_industry.get("description", ""),
                references=existing_industry.get("references", []))
            from src.agents.research import VALUE_CHAIN_TEMPLATES
            template_key = (profile or {}).get("value_chain_template", "")
            template_tiers = VALUE_CHAIN_TEMPLATES.get(template_key, [])
            for order, tier in enumerate(template_tiers, 1):
                km.add_chain(tier, description="内置产业链候选；需通过研究任务核验",
                             order=order)
            # 3) 三份行业报告任务包
            reports = build_report_tasks(store, store.name,
                                         (profile or {}).get("name_en", ""))
            print(f"[完成] 初始化行业：{store.name} → {store.root}")
            print(f"  信息源 sources.json：{sum(len(v) for k,v in seed.items() if isinstance(v,list))} 个源")
            print(f"  信息源发现任务包：{task_path}")
            print(f"  三层知识骨架：one_time/knowledge/（{len(template_tiers)} 个候选环节）")
            print(f"  行业报告任务包：{len(reports)} 份（5年趋势/2年流行/半年技术）→ one_time/reports/tasks.json")

        elif args.command == "bootstrap-industry":
            from src.research_bootstrap import prepare_bootstrap, run_bootstrap
            try:
                if args.execution_mode == "direct":
                    if not args.provider:
                        parser.error("bootstrap-industry direct mode requires --provider")
                    status = run_bootstrap(pcfg, store, (profile or {}).get("name_en", ""),
                                           profile, provider=args.provider,
                                           resume_task_id=args.resume_task)
                elif args.execution_mode == "taskpack":
                    status = prepare_bootstrap(store, (profile or {}).get("name_en", ""), profile)
                else:
                    parser.error("bootstrap-industry requires --execution-mode taskpack|direct")
            except Exception as exc:
                if hasattr(exc, "public"):
                    detail = exc.public()
                    print("INTDOG_EVENT " + __import__("json").dumps({
                        "stage": "provider_failed", "progress": 5,
                        "message": str(detail.get("detail") or exc),
                        "error_category": str(detail.get("category") or "provider_error"),
                        "checkpoint": {"provider_error": {
                            key: detail.get(key) for key in
                            ("status_code", "code", "param", "request_id")}},
                    }, ensure_ascii=False, separators=(",", ":")))
                print(f"[错误] 行业研究初始化失败：{type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(2)
            print(f"[完成] 来源优先初始化：{store.name}")
            print("  顺序：信息源门槛 → 产业链门槛 → 实体覆盖门槛")
            print(f"  状态：{status['state']} · 人工复核={status['review_required']}")
            if args.execution_mode == "direct" and status.get("state") == "partial":
                sys.exit(4)

        elif args.command == "resume-bootstrap":
            from src.research_bootstrap import resume_codex_bootstrap
            try:
                status = resume_codex_bootstrap(store, (profile or {}).get("name_en", ""))
            except Exception as exc:
                print(f"[错误] 恢复 Codex 研究失败：{type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(2)
            print(f"[完成] 已恢复并正规化 Codex 结果：{store.name}")
            print(f"  状态：{status['state']} · 人工复核={status['review_required']}")

        elif args.command == "refresh-sources":
            from src.research_bootstrap import refresh_sources_with_agent
            if not args.provider:
                parser.error("refresh-sources 必须显式提供 --provider codex 或 API provider")
            try:
                status = refresh_sources_with_agent(
                    pcfg, store, (profile or {}).get("name_en", ""), profile,
                    provider=args.provider)
            except Exception as exc:
                print(f"[错误] 刷新来源失败：{type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(2)
            audit = status["stages"]["sources"]["audit"]
            print(f"[完成] {store.name} 来源：中文 {audit['origin_counts']['china']} / "
                  f"外文 {audit['origin_counts']['foreign']}")

        elif args.command == "discover-sources":
            from src.source_discovery import build_discovery_task, SOURCE_CATEGORIES
            src = store.get_sources()
            print(f"[信息源] {store.name} 当前 sources.json：")
            for cat, label in SOURCE_CATEGORIES:
                items = src.get(cat, [])
                print(f"  【{label}】{len(items)} 个")
                for s in items[:5]:
                    print(f"    - {s.get('name')}  {s.get('url')}")
            task = build_discovery_task(store.name)
            task_path = store.save_task("source_discovery", task)
            print(f"\n[任务包] 可用 agent 扩充信息源：{task_path}")

        elif args.command == "enrich-sources":
            from src.research_bootstrap import discover_rss_endpoints
            sources = store.get_sources()
            before = sum(bool(item.get("rss_url") or item.get("feed_url"))
                         for value in sources.values() if isinstance(value, list)
                         for item in value if isinstance(item, dict))
            sources = discover_rss_endpoints(sources)
            store.save_sources(sources)
            after = sum(bool(item.get("rss_url") or item.get("feed_url"))
                        for value in sources.values() if isinstance(value, list)
                        for item in value if isinstance(item, dict))
            print(f"[完成] RSS/Atom 自动发现：原有 {before}，新增 {after-before}，合计 {after}")

        elif args.command == "report-tasks":
            from src.report_tasks import build_report_tasks
            tasks = build_report_tasks(store, store.name,
                                       (profile or {}).get("name_en", ""))
            print(f"[完成] 生成 {len(tasks)} 份行业报告任务包 → {store.reports}/tasks.json")
            for t in tasks:
                print(f"  - {t['title']}  → {t['output_file']}")

        elif args.command == "crawl-daily":
            from src.scheduler import PeriodicScheduler
            sch = PeriodicScheduler(pcfg, store)
            print(f"[抓取] {store.name} 每日六类（新闻/论文/GitHub/融资/招聘/CEO）…")
            r = sch.run_daily(since_days=args.days)
            for k, v in r.items():
                print(f"  {k}: {v}")
            print(f"  → {store.periodic}/daily/")
            if r["status"] == "partial":
                sys.exit(4)
            if r["status"] == "failed":
                sys.exit(3)

        elif args.command in ("crawl-weekly", "crawl-monthly", "crawl-quarterly"):
            from src.scheduler import PeriodicScheduler
            sch = PeriodicScheduler(pcfg, store)
            kind = args.command.split("-")[1]
            fn = {"weekly": sch.run_weekly, "monthly": sch.run_monthly,
                  "quarterly": sch.run_quarterly}[kind]
            r = fn()
            for k, v in r.items():
                print(f"  {k}: {v}")

        elif args.command == "generate-period":
            from src.report_generation import generate_periodic
            kind = args.kind or "weekly"
            try:
                result = generate_periodic(pcfg, store, kind, args.provider)
            except Exception as exc:
                print(f"[错误] 周期报告生成失败：{type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(2)
            print(f"[完成] {kind} 文字报告：{result['path']}")
            print(f"  可视化元数据：{result['metadata']}")

        elif args.command == "generate-report":
            from src.report_generation import generate_industry_report
            kind = args.kind or "tech_6m"
            try:
                result = generate_industry_report(
                    pcfg, store, kind, args.provider,
                    (profile or {}).get("name_en", ""))
            except Exception as exc:
                print(f"[错误] 行业报告生成失败：{type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(2)
            print(f"[完成] 行业报告：{result['path']}")

        elif args.command == "generate-deep-report":
            from src.report_generation import generate_deep_report
            kind = args.rtype or args.kind or "quarterly"
            try:
                result = generate_deep_report(
                    pcfg, store, kind, args.provider,
                    (profile or {}).get("name_en", ""))
            except Exception as exc:
                print(f"[错误] 深度报告生成失败：{type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(2)
            print(f"[完成] 深度研究报告：{result['path']}")

        elif args.command == "generate-impact":
            from src.report_generation import generate_impact_report
            if not args.event:
                parser.error("generate-impact 需要 --event")
            try:
                result = generate_impact_report(
                    pcfg, store, pcfg, args.event, args.provider)
            except Exception as exc:
                print(f"[错误] 事件影响报告生成失败：{type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(2)
            print(f"[完成] 事件影响报告：{result['path']}")

        elif args.command == "execute-coverage":
            from src.coverage_execution import (execute_coverage,
                                                execute_persisted_coverage_round)
            try:
                if args.coverage_round_id:
                    print(f"[覆盖] 恢复持久轮次 {args.coverage_round_id}")
                    result = execute_persisted_coverage_round(
                        pcfg, store, args.coverage_round_id,
                        provider=args.provider)
                else:
                    result = execute_coverage(
                        pcfg, store, provider=args.provider, budget=args.budget)
            except Exception as exc:
                print(f"[错误] 覆盖搜索执行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(2)
            print(f"[完成] 覆盖执行：{result}")

        elif args.command == "run-source-campaign":
            if not args.campaign_id:
                parser.error("run-source-campaign 需要 --campaign-id")
            from src.services.provider_factory import create_provider
            from src.source_campaign import ProviderSearchAdapter, run_campaign_round
            try:
                print(f"[来源活动] 执行或恢复 {args.campaign_id}")
                client = create_provider(
                    pcfg, args.provider, store.root)
                outcome = run_campaign_round(
                    store.service.repo, args.campaign_id,
                    search=ProviderSearchAdapter(client))
            except Exception as exc:
                print(f"[错误] 来源活动失败：{type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(2)
            print(f"[完成] 状态={outcome.status} 候选={outcome.candidate_total} "
                  f"合格={sum(outcome.qualified_by_category.values())} "
                  f"原因={outcome.stopping_reason}")

        elif args.command == "backfill-history":
            from src.history_backfill import POLICIES, backfill_history
            horizon = args.kind or "monthly"
            if horizon not in POLICIES:
                parser.error("backfill-history --kind 必须是 " + ", ".join(POLICIES))
            result = backfill_history(
                pcfg, store, horizon, target=args.target or None,
                max_buckets=args.max_buckets or None)
            print(f"[完成] 历史回填：{result}")

        elif args.command == "knowledge":
            from src.knowledge_model import KnowledgeModel
            km = KnowledgeModel(store.knowledge)
            if args.name:  # 新增实体
                if not args.chain:
                    print("[错误] 新增实体需 --chain 指定产业链层级")
                    sys.exit(1)
                e = km.add_entity(args.name, args.etype, args.chain,
                                  country=args.country, url=args.url,
                                  description=args.desc)
                print(f"[完成] 新增实体：{e['name']}（{e['type']}）→ 产业链[{e['chain']}]")
            else:  # 展示三层树
                tree = km.tree()
                ind = tree["industry"]
                print(f"行业：{ind.get('name', store.name)}")
                for c in tree["chains"]:
                    ents = c.get("entities", [])
                    print(f"  ├─ 产业链：{c['name']}（{len(ents)} 实体）")
                    for e in ents:
                        tag = "企业" if e["type"] == "company" else "高校/研究组"
                        print(f"  │    └─ [{tag}] {e['name']} {e.get('country','')}")

        elif args.command == "verify":
            from src import verification
            # verify 默认跨 3 天归并（单日验证覆盖太低）；--days 可显式指定更大窗口
            v_days = args.days if args.days > 1 else 3
            stats = verification.verify_store_daily(store, days=v_days)
            print(f"[完成] {store.name} 多源交叉验证（跨 {stats.get('days',1)} 天）："
                  f"归并 {stats['stories']} 个故事")
            print(f"  被 >=2 独立来源印证：{stats['verified_items']} 条")
            print(f"  可信度分布：高 {stats['high']} / 中 {stats['medium']} / 低 {stats['low']}")
            print(f"  → 已回写 credibility / source_count / references[] 到 periodic/daily/")

        elif args.command == "doctor":
            import json
            from src.quality import audit_store
            freshness = args.days if args.days > 1 else 3
            report = audit_store(store, freshness_days=freshness)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if report["warnings"]:
                print("\n[需要处理]")
                for warning in report["warnings"]:
                    print(f"  - {warning}")
            else:
                print("\n[通过] 未发现明显的数据质量问题")

        elif args.command == "landscape":
            from src.landscape import build_landscape
            out = build_landscape(store, pcfg)
            print(f"[完成] {store.name} 竞争格局 → {out['path']}")
            for tier in ("leader", "challenger", "emerging", "declining", "watchlist"):
                names = "、".join(e["name"] for e in out["tiers"][tier]) or "（无）"
                print(f"  {out['labels'][tier]}: {names}")

        elif args.command == "impact":
            from src.impact_engine import analyze_event, detect_events
            if args.event:
                out = analyze_event(store, pcfg, args.event)
                print(f"[完成] 事件影响分析：{out['event']}")
                print(f"  受影响公司：{'、'.join(out['affected_companies']) or '（未命中知识库实体）'}")
                print(f"  关联产业链：{'、'.join(out['affected_chains']) or '（无）'}")
                print(f"  关联论文 {len(out['related_papers'])} 条 / 政策 {len(out['related_policies'])} 条")
                print(f"  分析报告任务包 → {out['path']}")
            else:
                evts = detect_events(store)
                print(f"[检测] {store.name} 高可信事件（可用 --event 深挖某条）：")
                for e in evts:
                    print(f"  [{e['credibility_label']}|源{e['source_count']}] {e['title']}")

        elif args.command == "deep-reports":
            from src.deep_reports import build_deep_reports
            tasks = build_deep_reports(store, store.name,
                                       (profile or {}).get("name_en", ""),
                                       rtype=args.rtype or None)
            print(f"[完成] 生成 {len(tasks)} 份深度研究报告任务包 → {store.reports}/deep_tasks.json")
            for t in tasks:
                print(f"  - {t['title']}  → {t['output_file']}")

        elif args.command in ("compile-evidence", "observe-sources", "simulate-chain",
                              "plan-boundaries", "run-lab", "agenda-status",
                              "create-research-task", "audit-artifacts"):
            from src.commands.lab import run_lab_command
            code = run_lab_command(args, parser, data_root, folder)
            if code:
                sys.exit(code)

    elif args.command == "mcp-serve":
        from src.mcp_server import serve_stdio
        from src.utils import data_root as canonical_data_root
        data_root = canonical_data_root(cfg)
        serve_stdio(data_root)

    elif args.command == "serve":
        from src.commands.serve import serve_archive
        serve_archive(orch.archive.root, args.host, args.port)


if __name__ == "__main__":
    main()
