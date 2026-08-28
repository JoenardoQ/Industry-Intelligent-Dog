"""DomainIntelData 直连读写（纯标准库，不依赖 DomainIntelSearch 的 src）.

DomainIntelApp 只做 UI：读取 / 删除 DomainIntelData 里按行业分目录保存的数据。
本模块负责定位数据根、遍历行业、读取/删除定期条目与产物、读写控制开关。

数据根定位顺序：
  1. 环境变量 INTDOG_DATA_ROOT
  2. DomainIntelApp 旁边的 ../DomainIntelData
  3. D:/IntDog/DomainIntelData（兜底）

行业文件夹结构（由 DomainIntelSearch 写入）：
  <行业>/control.json                 定期开关
  <行业>/sources.json                 信息源
  <行业>/one_time/knowledge/*.json    三层知识（industry/chains/entities）
  <行业>/one_time/reports/*           行业报告 + tasks.json
  <行业>/periodic/daily/<日期>/<类别>.json
  <行业>/periodic/{weekly,monthly,quarterly}/*.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

DAILY_CATEGORIES = ("news", "github", "funding", "hiring", "ceo", "papers")
PERIOD_KINDS = ("weekly", "monthly", "quarterly")
# 非行业目录（扫描行业时跳过）
SKIP_DIRS = {"skill", "domains", "images", "_trash"}


def find_data_root() -> Path:
    env = os.environ.get("INTDOG_DATA_ROOT")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve()
    for cand in (here.parents[2] / "DomainIntelData",
                 Path("D:/IntDog/DomainIntelData")):
        if cand.exists():
            return cand
    return here.parents[2] / "DomainIntelData"


# ----------------------------------------------------------------------
# 基础 JSON 读写（原子写）
# ----------------------------------------------------------------------
def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return default


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ----------------------------------------------------------------------
# 行业
# ----------------------------------------------------------------------
def list_industries(root: Path) -> list[dict]:
    """列出真正的行业文件夹（以 control.json 为标识，过滤旧扁平归档目录）."""
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if not (d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")):
            continue
        ctrl_path = d / "control.json"
        if not ctrl_path.exists():
            continue  # 非行业文件夹（如旧的 data/db/index/reports）
        ctrl = read_json(ctrl_path, {})
        out.append({"folder": d.name,
                    "periodic_enabled": ctrl.get("periodic_enabled", False)})
    return out


def read_control(root: Path, folder: str) -> dict:
    return read_json(root / folder / "control.json", {"periodic_enabled": False})


def set_periodic(root: Path, folder: str, enabled: bool):
    p = root / folder / "control.json"
    ctrl = read_json(p, {})
    ctrl["periodic_enabled"] = bool(enabled)
    ctrl["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_json(p, ctrl)


# ----------------------------------------------------------------------
# 信息源
# ----------------------------------------------------------------------
def read_sources(root: Path, folder: str) -> dict:
    return read_json(root / folder / "sources.json", {})


def read_bootstrap_status(root: Path, folder: str) -> dict:
    """读取来源优先研究初始化状态；旧行业没有该文件时返回空对象。"""
    return read_json(root / folder / "bootstrap_status.json", {})


def source_origin(item: dict) -> str:
    explicit = str(item.get("origin") or item.get("site_region") or "").lower()
    if explicit in {"china", "cn", "中国", "chinese"}:
        return "china"
    if explicit in {"foreign", "international", "global", "overseas", "国外", "国际"}:
        return "foreign"
    country = str(item.get("publisher_country") or item.get("country") or "").lower()
    if any(token in country for token in ("china", "中国", "chinese")):
        return "china"
    try:
        domain = urlsplit(str(item.get("url") or "")).netloc.lower().removeprefix("www.")
    except ValueError:
        domain = ""
    china_domains = ("gov.cn", "cninfo.com.cn", "wallstreetcn.com", "caict.ac.cn",
                     "miit.gov.cn", "cac.gov.cn")
    if domain.endswith(".cn") or any(domain.endswith(value) for value in china_domains):
        return "china"
    return "foreign" if domain else "unknown"


# ----------------------------------------------------------------------
# 每日定期条目
# ----------------------------------------------------------------------
def _key(item: dict) -> str:
    return (item.get("url") or item.get("title") or "")[:200]


def list_daily_dates(root: Path, folder: str) -> list[str]:
    d = root / folder / "periodic" / "daily"
    if not d.exists():
        return []
    return sorted((x.name for x in d.iterdir() if x.is_dir()), reverse=True)


def list_daily(root: Path, folder: str, date: str = None,
               category: str = None) -> list[dict]:
    daily = root / folder / "periodic" / "daily"
    if not daily.exists():
        return []
    dates = [date] if date else list_daily_dates(root, folder)
    out = []
    for dt in dates:
        day_dir = daily / dt
        if not day_dir.exists():
            continue
        cats = [category] if category else [p.stem for p in day_dir.glob("*.json")
                                            if not p.stem.startswith("_")]
        for c in cats:
            f = day_dir / f"{c}.json"
            for it in read_json(f, []):
                it = dict(it)
                it["_file"] = str(f)
                it["_cat"] = c
                it["_date"] = dt
                out.append(it)
        # 未指定日期时只取最近一天
        if not date and out:
            break
    return out


def delete_daily_item(root: Path, folder: str, date: str, category: str,
                      key: str) -> bool:
    f = root / folder / "periodic" / "daily" / date / f"{category}.json"
    items = read_json(f, [])
    new = [it for it in items if _key(it) != key]
    if len(new) == len(items):
        return False
    write_json(f, new)
    return True


# ----------------------------------------------------------------------
# 周/月/季产物
# ----------------------------------------------------------------------
def list_period(root: Path, folder: str, kind: str) -> list[dict]:
    d = root / folder / "periodic" / kind
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json"), reverse=True):
        it = read_json(f, {})
        if it:
            it["_file"] = str(f)
            it["_key"] = f.stem
            out.append(it)
    return out


def delete_period(root: Path, folder: str, kind: str, key: str) -> bool:
    f = root / folder / "periodic" / kind / f"{key}.json"
    if not f.exists():
        return False
    trash = root / "_trash"
    trash.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    f.replace(trash / f"{folder}_{kind}_{key}_{ts}.json")
    return True


# ----------------------------------------------------------------------
# 三层知识
# ----------------------------------------------------------------------
def read_knowledge(root: Path, folder: str) -> dict:
    kdir = root / folder / "one_time" / "knowledge"
    ind = read_json(kdir / "industry.json", {})
    chains = read_json(kdir / "chains.json", [])
    ents = read_json(kdir / "entities.json", [])
    for c in chains:
        c["entities"] = [e for e in ents if e.get("chain") == c.get("name")]
    return {"industry": ind, "chains": chains, "entities": ents}


def delete_entity(root: Path, folder: str, entity_id: str) -> bool:
    f = root / folder / "one_time" / "knowledge" / "entities.json"
    ents = read_json(f, [])
    new = [e for e in ents if e.get("id") != entity_id]
    if len(new) == len(ents):
        return False
    write_json(f, new)
    return True


# ----------------------------------------------------------------------
# 行业报告（one_time/reports）
# ----------------------------------------------------------------------
def list_reports(root: Path, folder: str) -> list[dict]:
    out = []
    industry = root / folder
    roots = [industry / "one_time" / "reports",
             industry / "one_time" / "research"]
    for directory in roots:
        if not directory.exists():
            continue
        for f in sorted(directory.rglob("*")):
            if (f.is_file() and f.suffix in (".md", ".json", ".html")
                    and "tasks" not in f.parts):
                out.append({"name": f.relative_to(industry).as_posix(),
                            "path": str(f), "size": f.stat().st_size})
    return out


def read_text(path: Path, limit: int = 200_000) -> str:
    try:
        t = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"读取失败: {e}"
    return t[:limit] + ("\n\n…（截断）" if len(t) > limit else "")


# ----------------------------------------------------------------------
# 竞争格局（one_time/landscape，DomainIntelSearch landscape 命令产出）
# ----------------------------------------------------------------------
def read_landscape(root: Path, folder: str) -> dict:
    """读取竞争格局最新结果 + 历史快照日期列表."""
    ldir = root / folder / "one_time" / "landscape"
    latest = read_json(ldir / "landscape.json", {})
    hdir = ldir / "history"
    history = []
    if hdir.exists():
        history = [f.stem for f in sorted(hdir.glob("*.json"))]
    return {"landscape": latest, "history": history}


def share_trend(root: Path, folder: str, company: str) -> list[dict]:
    """某公司在历史快照中的提及量序列（地位变化代理指标）."""
    hdir = root / folder / "one_time" / "landscape" / "history"
    out = []
    if not hdir.exists():
        return out
    for f in sorted(hdir.glob("*.json")):
        data = read_json(f, {})
        mentions = 0
        for tier in (data.get("tiers") or {}).values():
            for e in tier:
                if e.get("name") == company:
                    mentions = e.get("mentions", 0)
        out.append({"date": f.stem, "mentions": mentions})
    return out


# ----------------------------------------------------------------------
# 事件影响分析（one_time/impact，DomainIntelSearch impact 命令产出）
# ----------------------------------------------------------------------
def read_impact_events(root: Path, folder: str) -> dict:
    return read_json(root / folder / "one_time" / "impact" / "events.json",
                     {"events": []})


def list_impact_analyses(root: Path, folder: str) -> list[dict]:
    """列出已分析的事件（每个子目录一个）."""
    idir = root / folder / "one_time" / "impact"
    out = []
    if not idir.exists():
        return out
    for d in sorted(idir.iterdir()):
        if d.is_dir() and (d / "impact.json").exists():
            data = read_json(d / "impact.json", {})
            out.append({"slug": d.name,
                        "event": data.get("event", d.name),
                        "generated_at": data.get("generated_at", ""),
                        "companies": len(data.get("affected_companies", [])),
                        "chains": len(data.get("affected_chains", [])),
                        "papers": len(data.get("related_papers", [])),
                        "policies": len(data.get("related_policies", []))})
    return out


def read_impact(root: Path, folder: str, slug: str) -> dict:
    return read_json(root / folder / "one_time" / "impact" / slug / "impact.json", {})


# ----------------------------------------------------------------------
# 深度研究报告（one_time/reports/deep_tasks.json + deep/*.md）
# ----------------------------------------------------------------------
def read_deep_tasks(root: Path, folder: str) -> list[dict]:
    data = read_json(root / folder / "one_time" / "reports" / "deep_tasks.json", {})
    return data.get("tasks", [])


def list_deep_reports(root: Path, folder: str) -> list[dict]:
    """列出已回写完成的深度报告成品（deep/ 下的 .md）."""
    d = root / folder / "one_time" / "reports" / "deep"
    out = []
    if not d.exists():
        return out
    for f in sorted(d.glob("*.md")):
        out.append({"name": f.name, "path": str(f), "size": f.stat().st_size})
    return out
