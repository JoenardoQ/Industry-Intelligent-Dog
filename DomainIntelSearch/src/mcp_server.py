"""MCP Server：把 DomainIntelData 的全部数据源封装为 MCP 工具.

让任意 Agent（WorkBuddy / Claude / Codex / 自研）通过统一的
Model Context Protocol 调用数据，而不是把抓取/读取逻辑耦合在 Agent 内。

传输：stdio（换行分隔的 JSON-RPC 2.0，MCP 标准 stdio transport）
协议：initialize / notifications/initialized / ping / tools/list / tools/call

工具清单（tools/list 可见）：
  list_industries                       列出全部行业文件夹
  get_daily(industry, category?, date?) 读取每日情报（六类，含可信度/引用）
  get_knowledge(industry)               知识兼容视图 + 规范关系图 + 覆盖统计
  get_sources(industry)                 结构化信息源清单（九类）
  get_landscape(industry)               竞争格局（含 Watchlist + 历史快照）
  get_impact_events(industry)           检测到的行业事件清单
  get_impact(industry, slug?)           某事件的影响分析（公司/供应链/论文/政策）
  list_report_tasks(industry)           报告任务包清单（三报告 + 深度报告）
  read_report(industry, relpath)        读取 one_time/ 或 periodic/ 下任意产物
  search_items(industry, keyword)       在最近一天情报里按关键词检索

启动：
  python -m src.main mcp-serve                 # 服务全部行业
  （Claude Desktop / WorkBuddy mcp.json 里配置 command+args 即可）

纯标准库实现，零依赖；日志走 stderr，stdout 只跑协议帧。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SERVER_NAME = "domain-intel"
SERVER_VERSION = "4.1.0-test.4"
PROTOCOL_VERSION = "2024-11-05"   # 兼容主流客户端；initialize 时回显请求版本

PROJECT_ROOT = Path(os.environ.get("INTDOG_PROJECT_ROOT") or
                    Path(__file__).resolve().parents[2]).resolve()
DEFAULT_DATA_ROOT = PROJECT_ROOT / "DomainIntelData"
DATA_ROOT: Path = DEFAULT_DATA_ROOT  # serve_stdio() 启动时覆盖

SKIP_DIRS = {"skill", "domains", "images", "_trash", "__pycache__"}


# ----------------------------------------------------------------------
# 工具实现（全部只读 DomainIntelData）
# ----------------------------------------------------------------------
def _industry_dir(folder: str) -> Path:
    if not folder or Path(folder).name != folder:
        raise ValueError("industry 必须是单个行业文件夹名")
    root = DATA_ROOT.resolve()
    d = (root / folder).resolve()
    if not d.is_relative_to(root):
        raise ValueError("industry 路径越界")
    if not d.exists() or not (d / "control.json").exists():
        raise ValueError(f"行业不存在或未初始化: {folder!r}（先跑 init-industry）")
    return d


def _safe_child(base: Path, relative: str) -> Path:
    candidate = (base.resolve() / relative).resolve()
    if not candidate.is_relative_to(base.resolve()):
        raise ValueError("相对路径越界")
    return candidate


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return default


def _service():
    from intdog_core import IntDogService
    return IntDogService(DATA_ROOT)


def tool_list_industries(_args: dict):
    out = []
    for row in _service().repo.list_industries():
        ctrl = _read_json(DATA_ROOT / row["folder"] / "control.json", {})
        out.append({"folder": row["folder"], "name": row["name"],
                    "periodic_enabled": ctrl.get("periodic_enabled", False)})
    return {"data_root": str(DATA_ROOT), "industries": out}


def tool_get_daily(args: dict):
    folder = args["industry"]
    _industry_dir(folder)
    category = args.get("category") or None
    date = args.get("date") or None
    # 复用 IndustryStore 的读取逻辑
    from .industry_store import IndustryStore
    store = IndustryStore(DATA_ROOT, folder)
    items = store.list_daily(date=date, category=category)
    for it in items:
        it.pop("_file", None)
    return {"industry": folder, "count": len(items), "items": items}


def tool_get_knowledge(args: dict):
    folder = args["industry"]
    base = _industry_dir(folder) / "one_time" / "knowledge"
    service = _service()
    return {
        "industry": _read_json(base / "industry.json", {}),
        "chains": _read_json(base / "chains.json", []),
        "entities": _read_json(base / "entities.json", []),
        "graph": service.repo.graph(folder),
        "coverage": service.repo.knowledge_stats(folder),
    }


def tool_get_sources(args: dict):
    folder = args["industry"]
    _industry_dir(folder)
    grouped = {key: [] for key in ("official", "associations", "blogs", "platforms",
                                   "self_media", "news", "journals", "financials", "finance")}
    for item in _service().repo.list_sources(folder):
        grouped.setdefault(item.pop("category"), []).append(item)
    return {"industry": folder, **grouped}


def tool_get_landscape(args: dict):
    folder = args["industry"]
    ldir = _industry_dir(folder) / "one_time" / "landscape"
    latest = _read_json(ldir / "landscape.json", None)
    history = []
    hdir = ldir / "history"
    if hdir.exists():
        history = [f.stem for f in sorted(hdir.glob("*.json"))]
    return {"landscape": latest, "history_snapshots": history}


def tool_get_impact_events(args: dict):
    folder = args["industry"]
    return _read_json(_industry_dir(folder) / "one_time" / "impact" / "events.json",
                      {"events": [], "note": "尚未运行 impact 检测"})


def tool_get_impact(args: dict):
    folder = args["industry"]
    idir = _industry_dir(folder) / "one_time" / "impact"
    slug = args.get("slug")
    if slug:
        data = _read_json(_safe_child(idir, slug) / "impact.json", None)
        if data is None:
            raise ValueError(f"未找到事件影响分析: {slug!r}")
        return data
    # 未指定 slug：列出全部已分析事件
    out = []
    if idir.exists():
        for d in sorted(idir.iterdir()):
            if d.is_dir() and (d / "impact.json").exists():
                data = _read_json(d / "impact.json", {})
                out.append({"slug": d.name, "event": data.get("event"),
                            "companies": len(data.get("affected_companies", [])),
                            "papers": len(data.get("related_papers", [])),
                            "policies": len(data.get("related_policies", []))})
    return {"analyzed_events": out}


def tool_list_report_tasks(args: dict):
    folder = args["industry"]
    rdir = _industry_dir(folder) / "one_time" / "reports"
    return {
        "standard_tasks": _read_json(rdir / "tasks.json", {}).get("tasks", []),
        "deep_tasks": _read_json(rdir / "deep_tasks.json", {}).get("tasks", []),
    }


def tool_read_report(args: dict):
    folder = args["industry"]
    rel = args["relpath"].replace("\\", "/").lstrip("/")
    base = _industry_dir(folder)
    f = _safe_child(base, rel)
    if not f.exists() or not f.is_file():
        raise ValueError(f"文件不存在: {rel}")
    if f.stat().st_size > 2_000_000:
        raise ValueError("文件超过 2MB 读取上限")
    if f.suffix == ".json":
        return {"path": rel, "json": _read_json(f, None)}
    return {"path": rel, "text": f.read_text(encoding="utf-8", errors="replace")}


def tool_search_items(args: dict):
    folder = args["industry"]
    kw = (args.get("keyword") or "").strip()
    if not kw:
        raise ValueError("keyword 不能为空")
    hits = _service().repo.search_documents(folder, kw, limit=100)
    if args.get("date"):
        hits = [item for item in hits if item["observed_date"] == args["date"]]
    return {"industry": folder, "keyword": kw, "count": len(hits), "items": hits}


def _lab_artifact(folder: str, kind: str) -> dict:
    base = _industry_dir(folder) / "one_time" / "intelligence"
    pointer = _read_json(base / "latest" / f"{kind}.json", {})
    bundle = pointer.get("bundle", "")
    if bundle:
        path = _safe_child(base, bundle) / "artifact.json"
        artifact = _read_json(path, {})
        if artifact:
            return artifact
    compatibility = {"evidence_graph": "evidence_graph.json",
                     "source_observatory": "source_observatory.json",
                     "research_agenda": "research_agenda.json"}
    return _read_json(base / compatibility.get(kind, "missing.json"), {})


def tool_get_evidence_graph(args: dict):
    return _lab_artifact(args["industry"], "evidence_graph")


def tool_get_source_observatory(args: dict):
    return _lab_artifact(args["industry"], "source_observatory")


def tool_list_scenarios(args: dict):
    folder = args["industry"]
    base = _industry_dir(folder) / "one_time" / "intelligence"
    from src.lab.artifacts import list_valid_bundles
    items = list_valid_bundles(base, "chain_scenario")
    for item in items:
        item.pop("_bundle_path", None)
    return {"industry": folder, "count": len(items), "scenarios": items}


def tool_list_research_agenda(args: dict):
    folder = args["industry"]
    _industry_dir(folder)
    include_closed = args.get("include_closed") is True
    return {"industry": folder, "items": _service().repo.list_research_agenda(
        folder, include_closed=include_closed)}


def tool_explain_scenario_path(args: dict):
    artifact_id = args["artifact_id"]
    node_id = args["node_id"]
    scenarios = tool_list_scenarios(args)["scenarios"]
    scenario = next((item for item in scenarios
                     if item.get("artifact_id") == artifact_id), None)
    if not scenario:
        raise ValueError("情景产物不存在")
    impact = next((item for item in scenario.get("impacts", [])
                   if item.get("node_id") == node_id), None)
    if not impact:
        raise ValueError("该节点不在情景传播路径中")
    return {"artifact_id": artifact_id, "event": scenario.get("event"),
            "score_semantics": scenario.get("score_semantics"), "impact": impact}


# ----------------------------------------------------------------------
# 工具注册表（name → schema + 实现）
# ----------------------------------------------------------------------
def _schema(props: dict, required: list[str]):
    return {"type": "object",
            "properties": {k: {"type": v[0], "description": v[1]}
                           for k, v in props.items()},
            "required": required}


TOOLS = {
    "list_industries": {
        "description": "列出 DomainIntelData 下全部行业文件夹及定期开关状态",
        "inputSchema": _schema({}, []),
        "fn": tool_list_industries,
    },
    "get_daily": {
        "description": "读取某行业每日情报（news/github/funding/hiring/ceo/papers），"
                       "每条含 title/abstract/url/credibility/references",
        "inputSchema": _schema({
            "industry": ("string", "行业文件夹名，如 Chips / AI"),
            "category": ("string", "可选，六类之一，缺省全部"),
            "date": ("string", "可选，YYYY-MM-DD，缺省最近一天"),
        }, ["industry"]),
        "fn": tool_get_daily,
    },
    "get_knowledge": {
        "description": "读取行业、产业链兼容视图、规范实体关系图和覆盖统计",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名")}, ["industry"]),
        "fn": tool_get_knowledge,
    },
    "get_sources": {
        "description": "读取某行业九类结构化信息源清单",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名")}, ["industry"]),
        "fn": tool_get_sources,
    },
    "get_landscape": {
        "description": "读取竞争格局：Leader/Challenger/Emerging/Declining/Watchlist + 历史快照",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名")}, ["industry"]),
        "fn": tool_get_landscape,
    },
    "get_impact_events": {
        "description": "读取自动检测到的行业级事件清单（政策信号/多源印证）",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名")}, ["industry"]),
        "fn": tool_get_impact_events,
    },
    "get_impact": {
        "description": "读取某事件的影响分析（受影响公司/供应链/论文/政策）；"
                       "不传 slug 则列出全部已分析事件",
        "inputSchema": _schema({
            "industry": ("string", "行业文件夹名"),
            "slug": ("string", "可选，事件目录名"),
        }, ["industry"]),
        "fn": tool_get_impact,
    },
    "list_report_tasks": {
        "description": "列出报告任务包：三种行业报告 + 深度研究报告（季度/产业链/格局/市场）",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名")}, ["industry"]),
        "fn": tool_list_report_tasks,
    },
    "read_report": {
        "description": "读取行业目录下任意产物文件（json 自动解析，其余按文本）",
        "inputSchema": _schema({
            "industry": ("string", "行业文件夹名"),
            "relpath": ("string", "相对行业目录的路径，如 one_time/reports/deep/quarterly.md"),
        }, ["industry", "relpath"]),
        "fn": tool_read_report,
    },
    "search_items": {
        "description": "在某行业最近一天情报中按关键词检索（标题+摘要）",
        "inputSchema": _schema({
            "industry": ("string", "行业文件夹名"),
            "keyword": ("string", "检索关键词"),
            "date": ("string", "可选，YYYY-MM-DD"),
        }, ["industry", "keyword"]),
        "fn": tool_search_items,
    },
    "get_evidence_graph": {
        "description": "读取最新的、带证据状态和独立发布者统计的 Evidence Graph",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名")}, ["industry"]),
        "fn": tool_get_evidence_graph,
    },
    "get_source_observatory": {
        "description": "读取最新 Source Observatory（来源链接与唯一文档口径分离）",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名")}, ["industry"]),
        "fn": tool_get_source_observatory,
    },
    "list_scenarios": {
        "description": "列出所有校验通过的版本化产业链情景产物",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名")}, ["industry"]),
        "fn": tool_list_scenarios,
    },
    "list_research_agenda": {
        "description": "列出知识边界研究议程；默认不含已关闭条目",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名"),
                                 "include_closed": ("boolean", "是否包含关闭条目")},
                                ["industry"]),
        "fn": tool_list_research_agenda,
    },
    "explain_scenario_path": {
        "description": "解释版本化情景中某节点的逐边传播路径、证据数、效应和滞后",
        "inputSchema": _schema({"industry": ("string", "行业文件夹名"),
                                 "artifact_id": ("string", "情景产物 ID"),
                                 "node_id": ("string", "目标产业链节点 ID")},
                                ["industry", "artifact_id", "node_id"]),
        "fn": tool_explain_scenario_path,
    },
}


# ----------------------------------------------------------------------
# JSON-RPC / MCP 协议循环（stdio，换行分隔）
# ----------------------------------------------------------------------
def _send(obj: dict):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(rid, result):
    _send({"jsonrpc": "2.0", "id": rid, "result": result})


def _error(rid, code: int, message: str):
    _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def _log(msg: str):
    sys.stderr.write(f"[{SERVER_NAME}] {msg}\n")
    sys.stderr.flush()


def _handle(msg: dict):
    method = msg.get("method", "")
    rid = msg.get("id")          # 通知没有 id
    params = msg.get("params") or {}

    if method == "initialize":
        client_ver = (params.get("protocolVersion") or PROTOCOL_VERSION)
        _result(rid, {
            "protocolVersion": client_ver,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    elif method == "notifications/initialized":
        pass  # 纯通知，无需响应
    elif method == "ping":
        if rid is not None:
            _result(rid, {})
    elif method == "tools/list":
        _result(rid, {"tools": [
            {"name": name, "description": spec["description"],
             "inputSchema": spec["inputSchema"]}
            for name, spec in TOOLS.items()
        ]})
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        spec = TOOLS.get(name)
        if spec is None:
            _error(rid, -32602, f"未知工具: {name!r}")
            return
        try:
            data = spec["fn"](args)
            _result(rid, {
                "content": [{"type": "text",
                             "text": json.dumps(data, ensure_ascii=False,
                                                indent=2)}],
                "isError": False,
            })
        except Exception as e:  # 工具内错误按 MCP 约定以 isError 返回
            _result(rid, {"content": [{"type": "text", "text": f"ERROR: {e}"}],
                          "isError": True})
    else:
        if rid is not None:
            _error(rid, -32601, f"Method not found: {method}")


def serve_stdio(data_root: str | Path):
    """启动 MCP stdio 服务（阻塞，直到 stdin 关闭）."""
    global DATA_ROOT
    DATA_ROOT = Path(data_root)
    _log(f"data_root={DATA_ROOT}  tools={len(TOOLS)}  等待客户端…")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _error(None, -32700, "Parse error")
            continue
        try:
            _handle(msg)
        except Exception as e:
            _log(f"handler error: {e}")
            if msg.get("id") is not None:
                _error(msg["id"], -32603, f"Internal error: {e}")
    _log("stdin 关闭，服务退出")


if __name__ == "__main__":
    serve_stdio(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DATA_ROOT)
