"""读取 DomainIntelData/skill/spec.md，解析"抓取领域"与"保存格式".

DomainIntelSearch 不写死任何领域或格式，全部由 DomainIntelData 里的 skill 规定。
本模块把 spec.md 解析成结构化 dict，供 Orchestrator / 各 Agent 使用。

spec.md 约定（大小写不敏感匹配标题）：
  ## 抓取领域            <- 每行一个领域，支持 "显示名 (id)" 或纯名称
  ## 保存格式            <- "键: 值" 行或要点；可由用户自由扩展
  ## 用户待规定          <- 用户后续补充/修改的说明（原样保留）

解析失败时回退到空结果 + 默认值，不影响程序运行。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DataSpec:
    domains: list[dict] = field(default_factory=list)   # [{"name", "id"}]
    format: dict = field(default_factory=dict)          # 保存格式键值对
    user_todo: str = ""                                 # 待规定原文
    raw_text: str = ""                                  # 整篇内容
    path: str = ""                                      # spec.md 路径

    @property
    def domain_ids(self) -> list[str]:
        return [d["id"] for d in self.domains if d.get("id")]

    def has_domains(self) -> bool:
        return bool(self.domains)


def _split_sections(text: str) -> dict[str, str]:
    """按 '## 标题' 切分，返回 {小写标题: 该节正文}."""
    sections: dict[str, list[str]] = {}
    cur = "_preamble"
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            sections[cur] = "\n".join(buf).strip()
            cur = m.group(1).strip().lower()
            buf = []
        else:
            buf.append(line)
    sections[cur] = "\n".join(buf).strip()
    return sections


def _parse_domains(body: str) -> list[dict]:
    out: list[dict] = []
    for line in body.splitlines():
        line = line.strip()
        if not line or not (line.startswith("-") or line.startswith("*")):
            continue
        content = line.lstrip("-*").strip()
        if not content:
            continue
        # 支持 "显示名 (id)" 或 "显示名"
        m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", content)
        if m:
            name, did = m.group(1).strip(), m.group(2).strip()
        else:
            name, did = content, content
        out.append({"name": name, "id": did})
    return out


def _parse_format(body: str) -> dict:
    out: dict = {}
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith((">", "#", "---")):  # 忽略引用/注释/分隔线
            continue
        content = re.sub(r"^[-*]\s+", "", line)  # 去掉要点符号
        if ":" in content:
            k, v = content.split(":", 1)
            out[k.strip()] = v.strip()
        else:
            # 无键的要点，归到自由字段
            out.setdefault("_notes", []).append(content)
    return out


def load_spec(data_root: str | Path) -> DataSpec:
    """加载 data_root/skill/spec.md；缺失或损坏时返回空 spec（带默认值）."""
    root = Path(data_root)
    spec_path = root / "skill" / "spec.md"
    if not spec_path.exists():
        return DataSpec(path=str(spec_path))
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError:
        return DataSpec(path=str(spec_path))

    sections = _split_sections(text)
    domains = _parse_domains(
        sections.get("抓取领域", "") or sections.get("领域 (domains)", "")
    )
    fmt = _parse_format(
        sections.get("保存格式", "") or sections.get("格式 (format)", "")
    )
    user_todo = (
        sections.get("用户待规定", "")
        or sections.get("待规定", "")
        or sections.get("todo", "")
    )
    return DataSpec(
        domains=domains,
        format=fmt,
        user_todo=user_todo,
        raw_text=text,
        path=str(spec_path),
    )


def summarize(spec: DataSpec) -> str:
    """生成一行可读摘要，供启动时打印."""
    if not spec.domains:
        dom = "（未规定，沿用 settings.yaml 行业档案）"
    else:
        dom = "、".join(d["name"] for d in spec.domains)
    fmt_keys = ", ".join(list(spec.format.keys())[:6]) or "（默认）"
    return f"[DomainIntelData] 领域={dom} | 格式键={fmt_keys}"


if __name__ == "__main__":
    import sys
    p = (sys.argv[1] if len(sys.argv) > 1
         else Path(__file__).resolve().parents[2] / "DomainIntelData")
    s = load_spec(p)
    print(summarize(s))
    print("domains:", s.domains)
    print("format:", s.format)
    if s.user_todo:
        print("--- 用户待规定 ---")
        print(s.user_todo)
