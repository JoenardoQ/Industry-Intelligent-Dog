"""行业档案（Industry Profiles）：可插拔的行业配置.

每个 YAML 描述一个行业的关键词、数据源、跟踪公司、产业链模板等，
采集 / 研究 / 建图模块无需改代码即可切换到任意行业。

档案位置：config/industries/<id>.yaml
字段：
  id / name / name_en / aliases      标识与别名（界面搜索、CLI --industry 匹配用）
  depth                              beginner | intermediate | expert
  description                        一句话简介（界面展示）
  keywords                           新闻/论文过滤关键词
  value_chain_template               对应 research.py VALUE_CHAIN_TEMPLATES 的键
  arxiv_categories                   arXiv 分类
  semantic_scholar_fields            Semantic Scholar 领域
  tracked_companies                  [{name, symbol}] 重点跟踪公司（AKShare 行情）
  extra_rss_feeds                    {category: [{name,url,lang}]} 追加到基础 RSS 源
"""

from __future__ import annotations

import copy
import hashlib
import re
import sys
from pathlib import Path

import yaml

INDUSTRIES_DIR = Path(__file__).resolve().parent.parent / "config" / "industries"


def _industry_dirs() -> list[Path]:
    """行业档案搜索目录：打包模式下 exe 旁目录优先（用户可编辑），开发时为项目目录."""
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).parent / "config" / "industries")
    dirs.append(INDUSTRIES_DIR)
    seen, out = set(), []
    for d in dirs:
        if d.exists() and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def list_industries() -> list[dict]:
    """列出全部行业档案（按 name 排序，多目录合并、按 id 去重）."""
    found: dict[str, dict] = {}
    for d in _industry_dirs():
        for f in sorted(d.glob("*.yaml")):
            try:
                p = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            pid = p.get("id") or f.stem
            p.setdefault("id", pid)
            found[pid] = p  # 同名 id 前者优先（exe 旁覆盖内置）
    out = list(found.values())
    out.sort(key=lambda p: p.get("name", ""))
    return out


def find_profile(key: str) -> dict | None:
    """按 id / name / name_en / aliases 匹配行业档案（大小写不敏感）."""
    key = (key or "").strip()
    if not key:
        return None
    low = key.lower()
    for p in list_industries():
        candidates = [p.get("id", ""), p.get("name", ""), p.get("name_en", "")]
        candidates += p.get("aliases", []) or []
        if any(low == str(c).lower() for c in candidates if c):
            return p
    # 弱匹配：包含关系（如 "芯片" 命中 aliases 含 "芯片" 的半导体）
    for p in list_industries():
        candidates = [p.get("name", "")] + (p.get("aliases", []) or [])
        if any(key in str(c) or str(c) in key for c in candidates if c):
            return p
    return None


def profile_folder(profile: dict) -> str:
    """返回该行业在 DomainIntelData 下的文件夹名.

    优先取档案的 data_folder 字段；否则用 id（首字母大写）；
    都没有则用 name。保证是文件系统安全的单目录名。
    """
    folder = (profile or {}).get("data_folder")
    if folder:
        return str(folder)
    pid = (profile or {}).get("id") or ""
    if pid:
        return pid[:1].upper() + pid[1:]
    return (profile or {}).get("name", "Industry")


def make_custom_profile(name: str, keywords: list[str] = None,
                        name_en: str = "", depth: str = "beginner") -> dict:
    """界面"自定义行业"：无需落盘，直接构造档案 dict."""
    clean_name = name.strip() or "自定义行业"
    ascii_slug = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_")
    slug = ascii_slug or "custom_" + hashlib.sha1(
        clean_name.encode("utf-8")).hexdigest()[:8]
    return {
        "id": slug,
        "data_folder": slug,
        "name": clean_name,
        "name_en": name_en.strip(),
        "depth": depth or "beginner",
        "keywords": [k.strip() for k in (keywords or [clean_name]) if k.strip()],
        "description": "用户自定义行业",
    }


def apply_profile(config: dict, profile: dict | None) -> dict:
    """把行业档案合并进配置副本（不改原 config）.

    合并规则：domain / academic 字段直接覆盖；RSS 源按 URL 去重追加。
    """
    cfg = copy.deepcopy(config)
    if not profile:
        return cfg

    domain = cfg.setdefault("domain", {})
    if profile.get("name"):
        domain["name"] = profile["name"]
    if profile.get("name_en"):
        domain["name_en"] = profile["name_en"]
    if profile.get("depth"):
        domain["depth"] = profile["depth"]
    if profile.get("keywords"):
        domain["keywords"] = profile["keywords"]
    if profile.get("tracked_companies"):
        domain["tracked_companies"] = profile["tracked_companies"]

    academic = cfg.setdefault("academic", {})
    if profile.get("arxiv_categories"):
        academic["arxiv_categories"] = profile["arxiv_categories"]
    if profile.get("semantic_scholar_fields"):
        academic["semantic_scholar_fields"] = profile["semantic_scholar_fields"]

    # 追加行业专属 RSS 源（按 URL 去重）
    extra = profile.get("extra_rss_feeds") or {}
    if extra:
        feeds = cfg.setdefault("news", {}).setdefault("rss_feeds", {})
        for cat, items in extra.items():
            lst = feeds.setdefault(cat, [])
            existing = {f.get("url") for f in lst}
            for f in items or []:
                if f.get("url") and f["url"] not in existing:
                    lst.append(f)
                    existing.add(f["url"])

    cfg["_profile"] = {k: profile.get(k) for k in
                       ("id", "name", "name_en", "data_folder",
                        "value_chain_template", "description")}
    return cfg
