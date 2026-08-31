"""CLI dispatch for Intelligence Lab commands."""

from __future__ import annotations

from intdog_core import IntDogService
from src.intelligence_lab import IntelligenceLab
from src.lab.artifacts import audit_bundles


COMMANDS = {"compile-evidence", "observe-sources", "simulate-chain",
            "plan-boundaries", "run-lab", "agenda-status",
            "create-research-task", "audit-artifacts"}


def run_lab_command(args, parser, data_root, folder: str) -> int:
    if args.command == "audit-artifacts":
        base = data_root / folder / "one_time" / "intelligence"
        result = audit_bundles(base, repair_latest=args.repair_latest)
        print(f"[完成] 产物审计：有效 {result['valid']}，无效 {result['invalid']}，"
              f"指针异常 {result['invalid_pointers']}，已修复 {result['repaired_pointers']}")
        for error in result["errors"]:
            print(f"  ! {error}")
        unresolved_pointers = result["invalid_pointers"] - result["repaired_pointers"]
        return 3 if result["invalid"] or unresolved_pointers else 0

    if args.command == "create-research-task":
        if not args.agenda_id:
            parser.error("create-research-task 需要 --agenda-id")
        task = IntDogService(data_root).create_research_task(
            folder, args.agenda_id, args.budget)
        print(f"[完成] 研究任务包：{task['id']}\n  → {task['path']}")
        return 0

    if args.command == "agenda-status":
        if not args.agenda_id or not args.status:
            parser.error("agenda-status 需要 --agenda-id 和 --status")
        changed = IntDogService(data_root).update_research_agenda_status(
            folder, args.agenda_id, args.status)
        print("[完成] 研究议程状态已更新" if changed else "[未找到] 研究议程不存在")
        return 0 if changed else 2

    lab = IntelligenceLab(data_root, folder)
    if args.command == "compile-evidence":
        out = lab.compile_evidence()
        print(f"[完成] Evidence Graph：{out['metrics']['claims']} 条主张，"
              f"{out['metrics']['chain_gaps']} 个产业链缺口")
    elif args.command == "observe-sources":
        out = lab.observe_sources(max(1, args.stale_days))
        print(f"[完成] Source Observatory：{out['metrics']['source_links']} 个来源链接，"
              f"{out['metrics']['publisher_clusters']} 个发布者簇")
    elif args.command == "simulate-chain":
        if not args.event:
            parser.error("simulate-chain 需要 --event")
        out = lab.simulate_chain(args.event, args.chain, max(0, args.hops))
        print(f"[完成] 产业链情景：{out['status']}，影响 {len(out['impacts'])} 个节点")
        print(f"  → {out['path']}")
        return 4 if out["status"] == "unresolved" else 0
    elif args.command == "plan-boundaries":
        out = lab.plan_boundaries()
        print(f"[完成] Knowledge Boundary：{len(out['active_items'])} 个可行动议程")
    else:
        out = lab.run_all(event=args.event, chain=args.chain,
                          stale_days=max(1, args.stale_days), max_hops=max(0, args.hops))
        print("[完成] Intelligence Lab")
        print(f"  Evidence Graph → {out['evidence']['path']}")
        print(f"  Source Observatory → {out['sources']['path']}")
        if "scenario" in out:
            print(f"  Chain Scenario → {out['scenario']['path']}")
        print(f"  Research Agenda → {out['agenda']['path']}")
        return 4 if out["status"] == "partial" else 0
    print(f"  → {out['path']}")
    return 0
