"""配置加载与全局工具."""

import os
import json
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path

import yaml


BASE_DIR = Path(os.environ.get("INTDOG_SEARCH_ROOT") or
                Path(__file__).resolve().parent.parent).resolve()
PROJECT_DIR = Path(os.environ.get("INTDOG_PROJECT_ROOT") or BASE_DIR.parent).resolve()


def resolve_config_path(value: str | Path, *, base_dir: Path = BASE_DIR) -> Path:
    """Resolve a configured path without binding the project to one machine.

    Relative paths are anchored at ``DomainIntelSearch``. Historical Windows
    paths are mapped back into the current repository on non-Windows hosts so
    an old config cannot create a literal drive-letter directory.
    """
    raw = os.path.expandvars(os.path.expanduser(str(value or ""))).strip()
    if not raw:
        return base_dir
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", raw):
        normalized = raw.replace("\\", "/").lower()
        marker = "/domaininteldata"
        if marker in normalized:
            suffix = raw.replace("\\", "/")[normalized.index(marker) + len(marker):]
            return (PROJECT_DIR / "DomainIntelData" / suffix.lstrip("/")).resolve()
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def data_root(config: dict) -> Path:
    """Canonical root for all current per-industry data."""
    override = os.environ.get("DOMAIN_INTEL_DATA_ROOT") or os.environ.get("INTDOG_DATA_ROOT")
    if override:
        return resolve_config_path(override)
    configured = (config.get("data_layer", {}) or {}).get("root", "../DomainIntelData")
    return resolve_config_path(configured)


def archive_root(config: dict) -> Path:
    """Legacy archive root, retained only for backwards-compatible commands."""
    configured = (config.get("archive", {}) or {}).get("root", "../DomainIntelData/_archive")
    return resolve_config_path(configured)


def load_config(config_path: str = None) -> dict:
    """加载 YAML 配置文件."""
    if config_path is None:
        config_path = BASE_DIR / "config" / "settings.yaml"
    config_path = Path(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # Normalize all filesystem paths once.  Downstream modules therefore do
    # not need to guess which directory a relative path belongs to.
    for section, keys in (("output", ("dir", "data_dir")),
                          ("data_layer", ("root",)),
                          ("archive", ("root",))):
        values = cfg.get(section, {}) or {}
        for key in keys:
            if values.get(key):
                values[key] = str(resolve_config_path(values[key]))
        cfg[section] = values
    return cfg


def ensure_dir(path) -> Path:
    """确保目录存在."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def days_ago(n: int) -> datetime:
    return datetime.now() - timedelta(days=n)


def article_id(url: str) -> str:
    """根据 URL 生成唯一 ID，用于去重."""
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:16]


class SeenStore:
    """已抓取文章去重存储（JSON 文件）."""

    def __init__(self, store_path):
        self.store_path = Path(store_path)
        ensure_dir(self.store_path.parent)
        self._seen = self._load()

    def _load(self) -> dict:
        if self.store_path.exists():
            try:
                with open(self.store_path, "r", encoding="utf-8") as f:
                    return dict.fromkeys(json.load(f))
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def is_seen(self, uid: str) -> bool:
        return uid in self._seen

    def mark(self, uid: str):
        self._seen.pop(uid, None)
        self._seen[uid] = None

    def save(self):
        # 只保留最近 10000 条，避免文件无限增长
        data = list(self._seen)[-10000:]
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(data, f)


def save_json(data, path):
    ensure_dir(Path(path).parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default if default is not None else []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default if default is not None else []
