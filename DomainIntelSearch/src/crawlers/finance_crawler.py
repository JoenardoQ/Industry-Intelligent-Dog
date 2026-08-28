"""金融与政策爬虫：政策新闻 + 公司市场数据(AKShare)."""

from typing import Optional
from datetime import datetime

from .base import BaseCrawler, Article
from ..utils import days_ago


class PolicyNewsCrawler(BaseCrawler):
    """政策新闻爬虫（使用 RSS policy 源）."""

    name = "policy_news"

    def __init__(self, config, since_days=7):
        super().__init__(config)
        self.since = days_ago(since_days)

    def fetch(self) -> list[Article]:
        # 复用 RSS 策略源
        from .news_crawler import RSSCrawler
        rss = RSSCrawler(self.config, feed_category="policy",
                         since_days=max(1, (datetime.now() - self.since).days))
        return rss.fetch()


class FinanceNewsCrawler(BaseCrawler):
    """金融新闻爬虫（使用 RSS finance 源）."""

    name = "finance_news"

    def __init__(self, config, since_days=7):
        super().__init__(config)
        self.since_days = since_days

    def fetch(self) -> list[Article]:
        from .news_crawler import RSSCrawler
        rss = RSSCrawler(self.config, feed_category="finance",
                         since_days=self.since_days)
        return rss.fetch()


class StockDataFetcher:
    """通过 AKShare 获取公司市场数据（可选依赖）."""

    def __init__(self, config):
        self.config = config
        self._ak = None
        self._zh_spot = None
        self._us_spot = None

    @property
    def ak(self):
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                print("[WARN] akshare 未安装，跳过市场数据抓取。pip install akshare")
                self._ak = False
        return self._ak

    def get_stock_snapshot(self, symbol: str, name: str = "") -> Optional[dict]:
        """
        获取单只股票快照。
        symbol: 如 'sh600519' 或 '600519'(A股) 或 'AAPL'(美股)
        """
        ak = self.ak
        if not ak:
            return None
        try:
            # A股实时行情
            normalized = str(symbol or "").lower()
            if normalized.startswith(("sh", "sz", "bj")):
                normalized = normalized[2:]
            if len(normalized) == 6 and normalized.isdigit():
                if self._zh_spot is None:
                    self._zh_spot = ak.stock_zh_a_spot_em()
                row = self._zh_spot[self._zh_spot["代码"] == normalized]
                if row.empty:
                    return None
                r = row.iloc[0]
                return {
                    "name": name or r.get("名称", ""),
                    "symbol": normalized,
                    "price": float(r.get("最新价", 0)),
                    "change_pct": float(r.get("涨跌幅", 0)),
                    "market_cap": float(r.get("总市值", 0)),
                    "turnover": float(r.get("成交额", 0)),
                    "currency": "CNY",
                    "as_of": datetime.now().isoformat(timespec="seconds"),
                    "source": "AKShare/东方财富",
                }
            else:
                # 美股
                if self._us_spot is None:
                    self._us_spot = ak.stock_us_spot_em()
                row = self._us_spot[self._us_spot["代码"] == normalized.upper()]
                if row.empty:
                    return None
                r = row.iloc[0]
                return {
                    "name": name or r.get("名称", ""),
                    "symbol": normalized.upper(),
                    "price": float(r.get("最新价", 0)),
                    "change_pct": float(r.get("涨跌幅", 0)),
                    "market_cap": float(r.get("总市值", 0) or 0),
                    "currency": "USD",
                    "as_of": datetime.now().isoformat(timespec="seconds"),
                    "source": "AKShare/东方财富",
                }
        except Exception as e:
            print(f"[StockData] 抓取 {symbol} 失败: {e}")
            return None

    def get_history(self, symbol: str, days: int = 30) -> Optional[list]:
        """获取近 N 天历史行情."""
        ak = self.ak
        if not ak:
            return None
        try:
            import akshare as ak_mod
            df = ak_mod.stock_zh_a_hist(
                symbol=symbol, period="daily",
                start_date=days_ago(days).strftime("%Y%m%d"),
                end_date=days_ago(0).strftime("%Y%m%d"),
                adjust="qfq",
            )
            return [
                {"date": r["日期"], "close": float(r["收盘"]),
                 "pct": float(r["涨跌幅"])}
                for _, r in df.iterrows()
            ]
        except Exception as e:
            print(f"[StockData] 历史 {symbol} 失败: {e}")
            return None


class FinanceAggregator:
    """聚合金融与政策数据."""

    def __init__(self, config):
        self.config = config

    def collect_news(self, since_days: int = 1) -> dict:
        """返回 {finance: [...], policy: [...]}."""
        return {
            "finance": FinanceNewsCrawler(self.config, since_days=since_days).fetch(),
            "policy": PolicyNewsCrawler(self.config, since_days=since_days).fetch(),
        }

    def collect_market_data(self, companies: list[dict]) -> list[dict]:
        """companies: [{'name':, 'symbol':}]"""
        fetcher = StockDataFetcher(self.config)
        results = []
        for c in companies:
            snap = fetcher.get_stock_snapshot(c.get("symbol", ""), c.get("name", ""))
            if snap:
                results.append(snap)
        return results
