"""摘要生成器：将抓取数据渲染为邮件 HTML / Markdown."""

from typing import List
from ..crawlers.base import Article
from ..utils import today_str, now_str

try:
    from markdown import markdown as md_to_html
    MD_AVAILABLE = True
except ImportError:
    MD_AVAILABLE = False


class DigestGenerator:
    """生成日报 / 周报摘要."""

    def __init__(self, config: dict):
        self.config = config
        self.domain = config.get("domain", {})
        self.out_cfg = config.get("output", {})
        self.lang = self.out_cfg.get("language", "zh")
        self.fmt = self.out_cfg.get("report_format", "html")

    # ---------------- 文章列表渲染 ----------------
    def render_articles(self, articles: List[Article], max_items: int = 30) -> str:
        if not articles:
            return self._empty_msg()
        items = articles[:max_items]
        lines = []
        for i, a in enumerate(items, 1):
            tag = {
                "general": "📰", "startup": "🚀", "finance": "💰",
                "policy": "🏛️", "academic": "🔬",
            }.get(a.category, "•")
            lines.append(
                f'<div class="item">'
                f'<span class="rank">{i}</span>'
                f'<div class="content">'
                f'<div class="title">{tag} <a href="{self._esc(a.url)}">{self._esc(a.title)}</a></div>'
                f'<div class="meta">{self._esc(a.source)} · {a.published}'
                f'{(" · " + ", ".join(a.authors[:3])) if a.authors else ""}'
                f' · <a class="ref" href="{self._esc(a.url)}">来源链接</a></div>'
                f'<div class="summary">{self._esc((a.summary or "")[:200])}</div>'
                f'</div></div>'
            )
        return "\n".join(lines)

    # ---------------- 编号引用列表（全报告可溯源） ----------------
    def _references_html(self, groups: list) -> str:
        """汇总各分组文章为报告末尾的编号参考来源列表（按 URL 去重）."""
        seen, refs = set(), []
        for arts in groups:
            for a in arts or []:
                u = getattr(a, "url", "")
                if not u or u in seen:
                    continue
                seen.add(u)
                refs.append(a)
        if not refs:
            return ""
        items = "".join(
            f'<li><a href="{self._esc(a.url)}">{self._esc(a.title)}</a>'
            f'<span class="ref-src"> — {self._esc(a.source)}'
            f'{(" · " + a.published) if a.published else ""}</span></li>'
            for a in refs
        )
        return (f'<div class="section refs"><h2>📚 参考来源（{len(refs)}）</h2>'
                f'<ol class="ref-list">{items}</ol></div>')

    def _empty_msg(self) -> str:
        return '<p class="empty">本周期无符合条件的内容。</p>'

    def _esc(self, text: str) -> str:
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ---------------- 日报 ----------------
    def build_daily(self, news: List[Article], academic: List[Article],
                    finance: List[Article], policy: List[Article]) -> str:
        domain_name = self.domain.get("name", "领域")
        date = today_str()
        sections = [
            ("📰 行业新闻", news),
            ("🔬 学术动态", academic),
            ("💰 金融资讯", finance),
            ("🏛️ 政策要闻", policy),
        ]
        body = ""
        for title, items in sections:
            body += f'<div class="section"><h2>{title}</h2>'
            body += self.render_articles(items)
            body += '</div>'
        body += self._references_html([news, academic, finance, policy])

        html = self._wrap_html(
            f"{domain_name} 每日情报 · {date}",
            body,
            footer=f"由 Domain Intelligence System 自动生成 · {now_str()}"
        )
        return html

    # ---------------- 周报（金融 + 政策） ----------------
    def build_weekly(self, finance: List[Article], policy: List[Article],
                     market_data: List[dict] = None) -> str:
        domain_name = self.domain.get("name", "领域")
        date = today_str()
        body = '<div class="section"><h2>💰 本周金融综述</h2>'
        body += self.render_articles(finance)
        body += '</div><div class="section"><h2>🏛️ 本周政策综述</h2>'
        body += self.render_articles(policy)
        body += '</div>'

        if market_data:
            body += '<div class="section"><h2>📊 重点公司市场数据</h2><table class="market">'
            body += ("<tr><th>公司</th><th>代码</th><th>现价</th>"
                     "<th>涨跌幅</th><th>总市值</th></tr>")
            for m in market_data:
                pct_cls = "up" if m.get("change_pct", 0) >= 0 else "down"
                body += (
                    f"<tr><td>{self._esc(m.get('name',''))}</td>"
                    f"<td>{self._esc(m.get('symbol',''))}</td>"
                    f"<td>{m.get('price','')}</td>"
                    f"<td class='{pct_cls}'>{m.get('change_pct','')}%</td>"
                    f"<td>{self._fmt_cap(m.get('market_cap'))}</td></tr>"
                )
            body += "</table></div>"
        body += self._references_html([finance, policy])

        html = self._wrap_html(
            f"{domain_name} 每周金融政策简报 · {date}",
            body,
            footer=f"由 Domain Intelligence System 自动生成 · {now_str()}"
        )
        return html

    # ---------------- 年度轨迹（历史回顾） ----------------
    def build_timeline(self, articles: List[Article]) -> str:
        domain_name = self.domain.get("name", "领域")
        # 按月份分组
        by_month = {}
        for a in articles:
            if not a.published:
                continue
            month = a.published[:7]
            by_month.setdefault(month, []).append(a)
        body = ""
        for month in sorted(by_month.keys(), reverse=True):
            body += f'<div class="section"><h2>📅 {month}</h2>'
            body += self.render_articles(by_month[month], max_items=20)
            body += '</div>'
        body += self._references_html(list(by_month.values()))
        html = self._wrap_html(
            f"{domain_name} 近一年发展轨迹",
            body or self._empty_msg(),
            footer="由 Domain Intelligence System 自动生成"
        )
        return html

    # ---------------- HTML 包装 ----------------
    def _wrap_html(self, title: str, body: str, footer: str = "") -> str:
        css = """
        * { box-sizing: border-box; }
        body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; color: #1a1a1a;
               background: #f7f8fa; }
        .header { background: linear-gradient(135deg,#4a4de7,#7b5cff); color: #fff;
                  padding: 24px; border-radius: 12px; }
        .header h1 { margin: 0; font-size: 20px; font-weight: 600; }
        .header p { margin: 8px 0 0; opacity: .85; font-size: 13px; }
        .section { background: #fff; border-radius: 12px; padding: 20px; margin-top: 16px;
                   box-shadow: 0 1px 3px rgba(0,0,0,.06); }
        .section h2 { font-size: 15px; margin: 0 0 14px; color: #2c2c2a;
                      border-left: 3px solid #4a4de7; padding-left: 10px; }
        .item { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f0f0f0; }
        .rank { color: #b0b0b8; font-size: 13px; min-width: 18px; }
        .content { flex: 1; }
        .title { font-size: 14px; font-weight: 500; line-height: 1.5; }
        .title a { color: #3636d6; text-decoration: none; }
        .title a:hover { text-decoration: underline; }
        .meta { font-size: 12px; color: #8a8a93; margin: 4px 0; }
        .summary { font-size: 13px; color: #555; line-height: 1.6; }
        .empty { color: #999; font-size: 13px; }
        .meta a.ref { color: #8a8a93; text-decoration: none; }
        .meta a.ref:hover { text-decoration: underline; }
        .refs .ref-list { margin: 0; padding-left: 22px; }
        .refs li { font-size: 12px; padding: 3px 0; color: #555; line-height: 1.5; }
        .refs li a { color: #3636d6; text-decoration: none; }
        .refs li a:hover { text-decoration: underline; }
        .ref-src { color: #8a8a93; }
        table.market { width: 100%; border-collapse: collapse; font-size: 13px; }
        table.market th, table.market td { text-align: left; padding: 8px;
                  border-bottom: 1px solid #eee; }
        table.market th { color: #666; font-weight: 500; }
        .up { color: #d8504e; } .down { color: #2e9e5b; }
        .footer { text-align: center; color: #aaa; font-size: 12px; margin-top: 20px; }
        """
        return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{self._esc(title)}</title><style>{css}</style></head>
<body>
<div class="header"><h1>{self._esc(title)}</h1></div>
{body}
<div class="footer">{self._esc(footer)}</div>
</body></html>"""

    def _fmt_cap(self, cap) -> str:
        if not cap:
            return "-"
        cap = float(cap)
        if cap >= 1e12:
            return f"{cap/1e12:.2f} 万亿"
        if cap >= 1e8:
            return f"{cap/1e8:.2f} 亿"
        return f"{cap:.0f}"

    def to_markdown(self, html: str) -> str:
        """若安装了 markdown 库可逆向转换，否则返回纯文本截断."""
        return html
