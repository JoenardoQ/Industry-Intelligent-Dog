"""跨平台归档存储：按 时间/类别 索引，Win/macOS/Linux/Android 四端可读.

设计原则（可移植性优先）：
- 数据层  : JSON (UTF-8, ensure_ascii=False) —— 任何语言、任何系统原生可读
- 查询层  : SQLite 单文件数据库 —— 四端全平台有驱动，支持 SQL 全文检索
- 文本层  : HTML / Markdown 报告原样归档
- 索引    : master_index.json，内部全部使用【相对路径 + 正斜杠】
            整个归档目录拷贝到 Mac / Linux / U盘 / 网盘后索引依然有效
- 文件名  : 仅使用 ASCII 安全字符，避免跨平台编码问题

目录结构：
    <root>/                         默认 D:/DomainIntelligence
    ├── data/
    │   └── 2026/
    │       └── 2026-07-28/
    │           ├── news.json       ← 当日该类别全部条目
    │           ├── academic.json
    │           ├── finance.json
    │           ├── policy.json
    │           └── startup.json
    ├── reports/
    │   ├── daily/daily_2026-07-28.html
    │   ├── weekly/weekly_2026-07-28.html
    │   ├── timeline/...
    │   └── briefs/research_brief_2026-07-28.json
    ├── db/
    │   └── intelligence.db         ← SQLite（articles 表，可 SQL 查询）
    ├── index/
    │   └── master_index.json       ← 按日期 & 类别双向索引
    └── app/                        ← 安卓端 PWA（由项目部署）
"""

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path, PurePosixPath

from ..utils import ensure_dir, article_id

CATEGORIES = ("news", "academic", "finance", "policy", "startup")

# category 别名归一化（爬虫内部用 general 表示普通新闻）
_CAT_ALIAS = {"general": "news"}


def _norm_cat(cat: str) -> str:
    cat = (cat or "news").lower()
    return _CAT_ALIAS.get(cat, cat if cat in CATEGORIES else "news")


class ArchiveStore:
    """D 盘跨平台归档库."""

    def __init__(self, config: dict, root=None, db_only: bool = False):
        arc = config.get("archive", {}) or {}
        self.root = Path(root) if root is not None else Path(arc.get("root", "D:/DomainIntelligence"))
        self.enabled = arc.get("enabled", True)
        self.domain_name = (config.get("domain", {}) or {}).get("name", "")
        if not self.enabled:
            return
        subs = (("db",) if db_only else
                ("data", "reports/daily", "reports/weekly",
                 "reports/timeline", "reports/briefs", "db", "index"))
        for sub in subs:
            ensure_dir(self.root / sub)
        self.index_path = self.root / "index" / "master_index.json"
        self.db_path = self.root / "db" / "intelligence.db"
        self._init_db()

    # ------------------------------------------------------------------
    # SQLite（查询层）
    # ------------------------------------------------------------------
    def _init_db(self):
        con = sqlite3.connect(self.db_path)
        con.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                uid TEXT PRIMARY KEY,
                date TEXT NOT NULL,          -- 归档日期 YYYY-MM-DD
                published TEXT,              -- 原文发布日期
                category TEXT NOT NULL,
                title TEXT,
                url TEXT,
                source TEXT,
                summary TEXT,
                lang TEXT,
                authors TEXT,                -- JSON array
                extra TEXT,                  -- JSON object
                archived_at TEXT
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_date ON articles(date)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cat ON articles(category)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_pub ON articles(published)")
        # ---------- IIOS 新增表（IIOS_SPEC.md §7） ----------
        con.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, etype TEXT NOT NULL,
                industry TEXT, region TEXT, summary TEXT,
                extra_json TEXT, updated_at TEXT)""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY, src_id TEXT NOT NULL, dst_id TEXT NOT NULL,
                relation TEXT NOT NULL, weight REAL DEFAULT 1.0,
                source TEXT, updated_at TEXT)""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, etype TEXT NOT NULL, subject TEXT,
                date TEXT, title TEXT, description TEXT,
                importance INTEGER DEFAULT 3, source_url TEXT)""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, name_en TEXT,
                industry TEXT, tier TEXT, region TEXT,
                is_china INTEGER DEFAULT 0, metrics_json TEXT, updated_at TEXT)""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                company_id TEXT NOT NULL, dimension TEXT NOT NULL,
                score REAL, rationale TEXT, updated_at TEXT,
                PRIMARY KEY (company_id, dimension))""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ent_name ON entities(name)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_edge_src ON edges(src_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_evt_date ON events(date)")
        con.commit()
        con.close()

    def _db_upsert(self, date: str, category: str, items: list[dict]):
        con = sqlite3.connect(self.db_path)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for it in items:
            uid = it.get("uid") or article_id(it.get("url") or it.get("title", ""))
            con.execute("""
                INSERT INTO articles
                    (uid, date, published, category, title, url, source,
                     summary, lang, authors, extra, archived_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(uid) DO UPDATE SET
                    date=excluded.date, summary=excluded.summary
            """, (
                uid, date, it.get("published", ""), category,
                it.get("title", ""), it.get("url", ""), it.get("source", ""),
                it.get("summary", ""), it.get("lang", ""),
                json.dumps(it.get("authors", []), ensure_ascii=False),
                json.dumps(it.get("extra", {}), ensure_ascii=False),
                now,
            ))
        con.commit()
        con.close()

    # ------------------------------------------------------------------
    # JSON（数据层）
    # ------------------------------------------------------------------
    def _rel(self, path: Path) -> str:
        """转为相对 root 的 POSIX 风格路径（跨平台可移植）."""
        return str(PurePosixPath(path.relative_to(self.root)))

    def _day_dir(self, date: str) -> Path:
        return ensure_dir(self.root / "data" / date[:4] / date)

    def save_articles(self, articles, category: str = None,
                      date: str = None) -> dict:
        """归档一批文章。自动按类别分组、按 URL 去重合并.

        articles: list[Article] 或 list[dict]
        category: 指定类别；None 则按每条自身 category 分组
        date:     归档日期，默认今天
        """
        if not self.enabled or not articles:
            return {}
        date = date or datetime.now().strftime("%Y-%m-%d")
        groups: dict[str, list[dict]] = {}
        for a in articles:
            d = a if isinstance(a, dict) else a.to_dict()
            cat = _norm_cat(category or d.get("category"))
            d["uid"] = d.get("extra", {}).get("uid") or article_id(
                d.get("url") or d.get("title", ""))
            groups.setdefault(cat, []).append(d)

        saved = {}
        day_dir = self._day_dir(date)
        for cat, items in groups.items():
            fpath = day_dir / f"{cat}.json"
            existing = []
            if fpath.exists():
                try:
                    existing = json.loads(fpath.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, IOError):
                    existing = []
            merged = {e.get("uid") or e.get("url"): e for e in existing}
            for it in items:
                merged[it["uid"]] = it
            final = list(merged.values())
            fpath.write_text(
                json.dumps(final, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")
            self._db_upsert(date, cat, items)
            saved[cat] = {"count": len(final), "path": self._rel(fpath)}

        self._update_index(date, saved)
        return saved

    def save_report(self, report_type: str, src_path, date: str = None) -> str:
        """归档报告文件（HTML/JSON/MD），复制到 reports/<type>/ 下."""
        if not self.enabled:
            return ""
        src = Path(src_path)
        if not src.exists():
            return ""
        date = date or datetime.now().strftime("%Y-%m-%d")
        sub = {"daily": "daily", "weekly": "weekly",
               "timeline": "timeline", "brief": "briefs"}.get(report_type, report_type)
        dest_dir = ensure_dir(self.root / "reports" / sub)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        self._update_index_report(report_type, date, self._rel(dest))
        return str(dest)

    # ------------------------------------------------------------------
    # 索引（master_index.json）
    # ------------------------------------------------------------------
    def _load_index(self) -> dict:
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "format": "domain-intelligence-archive/v1",
            "domain": self.domain_name,
            "portable": True,
            "note": "所有路径均为相对本目录的 POSIX 路径，整个文件夹可拷贝到 Windows/macOS/Linux/Android 使用",
            "updated": "",
            "by_date": {},
            "by_category": {c: [] for c in CATEGORIES},
            "reports": [],
        }

    def _save_index(self, idx: dict):
        idx["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        idx["domain"] = idx.get("domain") or self.domain_name
        self.index_path.write_text(
            json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_index(self, date: str, saved: dict):
        idx = self._load_index()
        day = idx["by_date"].setdefault(date, {})
        for cat, info in saved.items():
            day[cat] = info
            cat_dates = idx["by_category"].setdefault(cat, [])
            if date not in cat_dates:
                cat_dates.append(date)
                cat_dates.sort(reverse=True)
        self._save_index(idx)

    def _update_index_report(self, rtype: str, date: str, rel_path: str):
        idx = self._load_index()
        entry = {"type": rtype, "date": date, "path": rel_path}
        idx["reports"] = [r for r in idx["reports"] if r["path"] != rel_path]
        idx["reports"].append(entry)
        idx["reports"].sort(key=lambda r: r["date"], reverse=True)
        self._save_index(idx)

    # ------------------------------------------------------------------
    # 迁移：把项目已有 output/ data/ 的历史文件一次性搬进归档
    # ------------------------------------------------------------------
    def migrate_existing(self, project_dir) -> dict:
        if not self.enabled:
            return {}
        project_dir = Path(project_dir)
        moved = {"reports": 0, "raw": 0}
        out_dir = project_dir / "output"
        if out_dir.exists():
            for f in out_dir.iterdir():
                if f.suffix not in (".html", ".json", ".md"):
                    continue
                name = f.name
                # 从文件名解析类型与日期 daily_2026-07-28.html
                rtype = "daily"
                for t in ("daily", "weekly", "timeline", "research_brief"):
                    if name.startswith(t):
                        rtype = "brief" if t == "research_brief" else t
                        break
                date = ""
                for part in name.replace(".", "_").split("_"):
                    if len(part) == 10 and part[4] == "-":
                        date = part
                        break
                self.save_report(rtype, f, date or None)
                moved["reports"] += 1
        raw = project_dir / "data" / "raw_collect.json"
        if raw.exists():
            try:
                data = json.loads(raw.read_text(encoding="utf-8"))
                for key in ("news", "academic"):
                    items = data.get(key, [])
                    if items:
                        self.save_articles(
                            items,
                            category="academic" if key == "academic" else None)
                        moved["raw"] += len(items)
            except (json.JSONDecodeError, IOError):
                pass
        return moved

    # ------------------------------------------------------------------
    # APP 部署：把项目 app/ (PWA) 同步到归档根目录
    # ------------------------------------------------------------------
    def deploy_app(self, project_dir) -> str:
        """把 PWA 前端复制到 <root>/app/，使其可直接读取归档数据."""
        if not self.enabled:
            return ""
        src = Path(project_dir) / "app"
        if not src.exists():
            return ""
        dest = ensure_dir(self.root / "app")
        for f in src.iterdir():
            if f.is_file():
                shutil.copy2(f, dest / f.name)
        return str(dest)

    # ------------------------------------------------------------------
    # 查询（供 CLI / 其他端调用示例）
    # ------------------------------------------------------------------
    def query(self, keyword: str = "", category: str = "",
              date_from: str = "", date_to: str = "", limit: int = 50) -> list[dict]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        sql = "SELECT * FROM articles WHERE 1=1"
        args = []
        if keyword:
            sql += " AND (title LIKE ? OR summary LIKE ?)"
            args += [f"%{keyword}%", f"%{keyword}%"]
        if category:
            sql += " AND category=?"
            args.append(_norm_cat(category))
        if date_from:
            sql += " AND date>=?"
            args.append(date_from)
        if date_to:
            sql += " AND date<=?"
            args.append(date_to)
        sql += " ORDER BY date DESC, published DESC LIMIT ?"
        args.append(limit)
        rows = [dict(r) for r in con.execute(sql, args).fetchall()]
        con.close()
        return rows

    # ------------------------------------------------------------------
    # IIOS：知识图谱 / 时间轴 / 公司 / 评分（IIOS_SPEC.md §7）
    # ------------------------------------------------------------------
    def upsert_entity(self, name: str, etype: str, industry: str = "",
                      region: str = "", summary: str = "", extra: dict = None) -> str:
        eid = article_id(f"ent|{etype}|{name.lower()}")
        con = sqlite3.connect(self.db_path)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute("""
            INSERT INTO entities (id, name, etype, industry, region, summary, extra_json, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                summary=CASE WHEN excluded.summary!='' THEN excluded.summary ELSE entities.summary END,
                updated_at=excluded.updated_at
        """, (eid, name, etype, industry, region, summary,
              json.dumps(extra or {}, ensure_ascii=False), now))
        con.commit()
        con.close()
        return eid

    def upsert_edge(self, src_id: str, dst_id: str, relation: str,
                    weight: float = 1.0, source: str = "") -> str:
        gid = article_id(f"edge|{src_id}|{relation}|{dst_id}")
        con = sqlite3.connect(self.db_path)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute("""
            INSERT INTO edges (id, src_id, dst_id, relation, weight, source, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                weight=edges.weight+0.1, updated_at=excluded.updated_at
        """, (gid, src_id, dst_id, relation, weight, source, now))
        con.commit()
        con.close()
        return gid

    def save_events(self, events: list[dict]) -> int:
        con = sqlite3.connect(self.db_path)
        n = 0
        for e in events:
            eid = article_id(f"evt|{e.get('etype')}|{e.get('date')}|{e.get('title')}")
            con.execute("""
                INSERT OR REPLACE INTO events
                    (id, etype, subject, date, title, description, importance, source_url)
                VALUES (?,?,?,?,?,?,?,?)
            """, (eid, e.get("etype", "industry"), e.get("subject", ""),
                  e.get("date", ""), e.get("title", ""), e.get("description", ""),
                  int(e.get("importance", 3)), e.get("source_url", "")))
            n += 1
        con.commit()
        con.close()
        return n

    def save_companies(self, companies: list[dict], industry: str = "") -> int:
        con = sqlite3.connect(self.db_path)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n = 0
        for cpy in companies:
            name = cpy.get("name", "")
            if not name:
                continue
            cid = article_id(f"cpy|{name.lower()}")
            con.execute("""
                INSERT INTO companies
                    (id, name, name_en, industry, tier, region, is_china, metrics_json, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    tier=excluded.tier, metrics_json=excluded.metrics_json,
                    updated_at=excluded.updated_at
            """, (cid, name, cpy.get("name_en", ""),
                  cpy.get("industry", industry), cpy.get("tier", ""),
                  cpy.get("region", ""), 1 if cpy.get("is_china") else 0,
                  json.dumps(cpy.get("metrics", cpy), ensure_ascii=False), now))
            # 评分
            for dim, val in (cpy.get("scores") or {}).items():
                score = val.get("score") if isinstance(val, dict) else val
                rationale = val.get("rationale", "") if isinstance(val, dict) else ""
                con.execute("""
                    INSERT OR REPLACE INTO scores
                        (company_id, dimension, score, rationale, updated_at)
                    VALUES (?,?,?,?,?)
                """, (cid, dim, float(score or 0), rationale, now))
            n += 1
        con.commit()
        con.close()
        return n

    def graph_neighbors(self, name: str, depth: int = 1) -> dict:
        """查询实体的邻居子图（供 kg 命令 / API 使用）."""
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM entities WHERE name LIKE ? LIMIT 1", (f"%{name}%",)).fetchone()
        if not row:
            con.close()
            return {"nodes": [], "edges": []}
        seen = {row["id"]: dict(row)}
        frontier = [row["id"]]
        edges = []
        for _ in range(max(1, depth)):
            nxt = []
            for eid in frontier:
                for e in con.execute(
                        "SELECT * FROM edges WHERE src_id=? OR dst_id=?", (eid, eid)):
                    edges.append(dict(e))
                    for other in (e["src_id"], e["dst_id"]):
                        if other not in seen:
                            r = con.execute(
                                "SELECT * FROM entities WHERE id=?", (other,)).fetchone()
                            if r:
                                seen[other] = dict(r)
                                nxt.append(other)
            frontier = nxt
        con.close()
        uniq = {e["id"]: e for e in edges}
        return {"nodes": list(seen.values()), "edges": list(uniq.values())}

    def kg_stats(self) -> dict:
        con = sqlite3.connect(self.db_path)
        s = {
            "entities": con.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "edges": con.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
            "events": con.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "companies": con.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
        }
        con.close()
        return s

    def stats(self) -> dict:
        con = sqlite3.connect(self.db_path)
        total = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        by_cat = dict(con.execute(
            "SELECT category, COUNT(*) FROM articles GROUP BY category").fetchall())
        dates = con.execute(
            "SELECT MIN(date), MAX(date) FROM articles").fetchone()
        con.close()
        return {"total": total, "by_category": by_cat,
                "date_range": list(dates), "root": str(self.root)}
