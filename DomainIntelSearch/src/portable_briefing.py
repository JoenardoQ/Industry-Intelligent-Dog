"""Offline, self-contained HTML briefing export."""
from __future__ import annotations

import html
import json
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse


def build_manifest(markdown: str, metadata: dict | None = None) -> dict:
    metadata = metadata if isinstance(metadata, dict) else {}
    content = str(markdown or "")
    references = []
    for item in metadata.get("references", []):
        candidate = item if isinstance(item, dict) else {"title": str(item), "url": str(item)}
        url = str(candidate.get("url") or "")
        if urlparse(url).scheme in {"http", "https"}:
            references.append({"title": str(candidate.get("title") or url), "url": url,
                               "status": str(candidate.get("status") or "unreviewed")})
    items = metadata.get("items") if isinstance(metadata.get("items"), list) else []
    normalized = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        normalized.append({"id": str(item.get("id") or index),
                           "title": str(item.get("title") or "未命名条目"),
                           "summary": str(item.get("summary") or item.get("abstract") or ""),
                           "date": str(item.get("date") or item.get("published_at") or ""),
                           "source": str(item.get("source") or metadata.get("source") or "IntDog"),
                           "status": str(item.get("status") or metadata.get("status") or "unknown"),
                           "chain_stage": str(item.get("chain_stage") or metadata.get("chain_stage") or "未分类"),
                           "url": url if urlparse(url).scheme in {"http", "https"} else ""})
    return {
        "version": "portable-brief-v1", "title": metadata.get("title") or "IntDog Briefing",
        "generated_at": metadata.get("generated_at") or metadata.get("window_end") or "",
        "status": metadata.get("artifact_status") or metadata.get("status") or "unknown",
        "chain_stage": metadata.get("chain_stage") or "未分类",
        "source": metadata.get("source") or "IntDog",
        "markdown": content, "references": references,
        "items": normalized,
        "quality": metadata.get("quality") or {},
        "content_sha256": sha256(content.encode("utf-8")).hexdigest(),
    }


def _json_for_script(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def write_portable_html(path: str | Path, manifest: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    title = html.escape(str(manifest.get("title") or "IntDog Briefing"))
    payload = _json_for_script(manifest)
    document = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; img-src data:"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>
:root{{--ink:#1f2925;--muted:#5d6963;--line:#d9dfdb;--accent:#315f50;--soft:#eef2ef}}*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f3;color:var(--ink);font:16px/1.75 Inter,"Noto Sans SC",system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:32px}}header,.tools,article{{background:white;border:1px solid var(--line);border-radius:20px;padding:22px;margin-bottom:16px}}h1{{margin:0;font-size:30px}}.meta{{color:var(--muted)}}.tools{{display:flex;gap:10px;flex-wrap:wrap;position:sticky;top:0}}input,select,button{{min-height:44px;border:1px solid var(--line);border-radius:12px;background:white;padding:0 12px;font:inherit}}input{{flex:1;min-width:220px}}button{{cursor:pointer}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:16px/1.8 inherit}}li{{margin:.65em 0}}a{{color:var(--accent)}}.saved{{background:var(--soft)}}@media(max-width:680px){{main{{padding:14px}}.tools>*{{width:100%}}}}@media print{{.tools{{display:none}}body{{background:white}}main{{max-width:none;padding:0}}}}
</style></head><body><main><header><h1 id="title"></h1><p class="meta" id="meta"></p></header><section class="tools" aria-label="简报工具"><input id="search" type="search" placeholder="搜索简报"><select id="source" data-filter-source aria-label="来源筛选"><option value="">全部来源</option></select><select id="status" data-filter-status aria-label="状态筛选"><option value="">全部状态</option></select><select id="chain" data-filter-chain aria-label="产业链筛选"><option value="">全部产业链</option></select><button id="favorite">☆ 收藏</button><button onclick="window.print()">打印 / PDF</button></section><section id="items"></section><article id="brief"><pre id="content"></pre><h2>证据与审核状态</h2><p id="review"></p><ol id="evidence"></ol></article></main><script id="intdog-manifest" type="application/json">{payload}</script><script>
(()=>{{'use strict';const m=JSON.parse(document.getElementById('intdog-manifest').textContent);const q=id=>document.getElementById(id);q('title').textContent=m.title;q('meta').textContent=[m.generated_at,m.status,m.chain_stage,m.content_sha256].filter(Boolean).join(' · ');q('content').textContent=m.markdown;q('review').textContent='审核状态：'+m.status+(m.quality&&m.quality.passed===false?' · 成品质量门未通过':'');const refs=(m.references||[]);for(const r of refs){{const li=document.createElement('li'),a=document.createElement('a');a.textContent=(r.title||r.url||'证据')+' · '+(r.status||'unreviewed');a.href=r.url;a.rel='noreferrer';li.append(a);q('evidence').append(li)}}const rows=(m.items||[]);for(const r of rows){{const card=document.createElement('article');card.dataset.source=r.source;card.dataset.status=r.status;card.dataset.chain=r.chain_stage;card.dataset.search=(r.title+' '+r.summary+' '+r.source).toLowerCase();const h=document.createElement('h2');h.textContent=r.title;const p=document.createElement('p');p.textContent=r.summary;const meta=document.createElement('p');meta.className='meta';meta.textContent=[r.date,r.source,r.status,r.chain_stage].filter(Boolean).join(' · ');card.append(h,p,meta);if(r.url){{const a=document.createElement('a');a.href=r.url;a.rel='noreferrer';a.textContent='查看证据';card.append(a)}}q('items').append(card)}}const choices={{source:new Set(rows.map(r=>r.source).filter(Boolean)),status:new Set(rows.map(r=>r.status).filter(Boolean)),chain:new Set(rows.map(r=>r.chain_stage).filter(Boolean))}};for(const [id,values] of Object.entries(choices))for(const value of values){{const o=document.createElement('option');o.value=value;o.textContent=value;q(id).append(o)}}const apply=()=>{{const term=q('search').value.toLowerCase();let visible=0;for(const card of q('items').children){{const match=(!term||card.dataset.search.includes(term))&&(!q('source').value||q('source').value===card.dataset.source)&&(!q('status').value||q('status').value===card.dataset.status)&&(!q('chain').value||q('chain').value===card.dataset.chain);card.hidden=!match;if(match)visible++}}q('brief').hidden=rows.length?visible===0:!!term&&!m.markdown.toLowerCase().includes(term)}};for(const id of ['search','source','status','chain'])q(id).addEventListener('input',apply);const key='intdog.favorite.'+m.content_sha256;let memory=false;const saved=()=>{{try{{return localStorage.getItem(key)==='1'}}catch{{return memory}}}},setSaved=value=>{{memory=value;try{{localStorage.setItem(key,value?'1':'0')}}catch{{}}}},paint=()=>{{const value=saved();q('favorite').textContent=value?'★ 已收藏':'☆ 收藏';q('favorite').classList.toggle('saved',value)}};q('favorite').onclick=()=>{{setSaved(!saved());paint()}};paint()}})();
</script></body></html>'''
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(document, encoding="utf-8")
    temp.replace(target)
    return target
