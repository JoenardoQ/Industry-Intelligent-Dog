"""HTTP/RSS 拉取工具：直连优先、代理兜底的弹性抓取 + 失败登记.

背景：本机环境变量里常驻 HTTP_PROXY=127.0.0.1:7890（Clash 类本地代理），
但代理并不总是在线——代理挂掉时，走环境代理的请求会全部失败。
因此所有抓取统一走本模块：

  1. 直连优先（trust_env=False，忽略环境代理）
  2. 直连失败（连接错误/超时）→ 回退环境代理再试一次
  3. 仍失败 → 登记到失败清单（crawl 结束统一汇总，不静默吞掉）

用法：
  from .http_utils import fetch_url, parse_feed, feed_failures, reset_feed_failures
"""

from __future__ import annotations

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DomainIntelSearch/1.1"}

# 本次运行中失败的源：[{name, url, error}]
_FAILURES: list[dict] = []
_SUCCESSES: list[dict] = []


def reset_feed_failures():
    """一次 crawl 开始前清空失败清单."""
    _FAILURES.clear()
    _SUCCESSES.clear()


def feed_failures() -> list[dict]:
    """返回失败清单（只读拷贝）."""
    return list(_FAILURES)


def feed_successes() -> list[dict]:
    return list(_SUCCESSES)


def _record(name: str, url: str, error: str):
    _FAILURES.append({"name": name, "url": url, "error": error})


def fetch_url(url: str, timeout: int = 15, name: str = "",
              params: dict = None, headers: dict = None) -> requests.Response:
    """直连优先、代理兜底地 GET 一个 URL.

    成功返回 Response；彻底失败登记并抛最后一次异常。
    params/headers 透传给 requests（headers 会与默认 UA 合并，调用方可覆盖）。
    """
    label = name or url
    hdrs = {**UA, **(headers or {})}
    # 1) 直连（忽略环境代理——代理常不在线）
    retry = Retry(total=2, connect=2, read=1, status=2, backoff_factor=0.5,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset({"GET"}), respect_retry_after_header=False)
    direct = requests.Session()
    direct.trust_env = False
    direct.mount("https://", HTTPAdapter(max_retries=retry))
    direct.mount("http://", HTTPAdapter(max_retries=retry))
    try:
        r = direct.get(url, params=params, headers=hdrs, timeout=timeout)
        r.raise_for_status()
        return r
    except requests.RequestException as e1:
        direct_err = f"{type(e1).__name__}: {str(e1)[:80]}"
    finally:
        direct.close()
    # 2) 回退环境代理（代理在线时可救回被墙源）
    try:
        with requests.Session() as proxied:
            proxied.mount("https://", HTTPAdapter(max_retries=retry))
            proxied.mount("http://", HTTPAdapter(max_retries=retry))
            r = proxied.get(url, params=params, headers=hdrs, timeout=timeout)
            r.raise_for_status()
            return r
    except requests.RequestException as e2:
        _record(label, url, f"直连[{direct_err}] 代理[{type(e2).__name__}: {str(e2)[:80]}]")
        raise


def parse_feed(url: str, name: str = "", timeout: int = 15):
    """拉取并解析 RSS/Atom；失败登记并返回 None（不抛异常，保证多源互不影响）."""
    try:
        r = fetch_url(url, timeout=timeout, name=name)
    except requests.RequestException:
        return None
    try:
        parsed = feedparser.parse(r.content)
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
            error = getattr(parsed, "bozo_exception", "malformed feed")
            _record(name or url, url, f"解析失败: {str(error)[:120]}")
            return None
        _SUCCESSES.append({"name": name or url, "url": url})
        return parsed
    except Exception as e:  # feedparser 极端输入也可能炸
        _record(name or url, url, f"解析失败: {type(e).__name__}: {str(e)[:60]}")
        return None
