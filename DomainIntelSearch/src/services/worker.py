"""后台爬虫调度器：常驻线程，持续抓取并写入 D 盘归档.

设计：
- 独立守护线程，不阻塞前台 UI
- 每 crawl_interval_hours 小时执行一次 daily 抓取（默认 4 小时）
- 每周一额外执行 weekly 金融政策简报
- 状态持久化到 <archive_root>/db/worker_state.json，重启程序不会立刻重复抓取
- 通过 on_status 回调把状态推给前台（线程安全：前台用 after() 轮询队列）
"""

import json
import queue
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path


class BackgroundWorker(threading.Thread):
    """常驻后台爬虫线程."""

    def __init__(self, config: dict, project_dir: Path):
        super().__init__(daemon=True, name="crawler-worker")
        self.config = config
        self.project_dir = Path(project_dir)
        dcfg = (config.get("desktop") or {})
        self.interval_h = float(dcfg.get("crawl_interval_hours", 4))
        self.send_email = bool(dcfg.get("send_email", False))
        arc = (config.get("archive") or {})
        self.state_path = Path(arc.get("root", "D:/DomainIntelligence")) / "db" / "worker_state.json"

        self.events: queue.Queue = queue.Queue()   # 前台从这里取状态
        self._stop = threading.Event()
        self._force_run = threading.Event()
        self.status = {
            "state": "启动中",
            "last_run": "",
            "next_run": "",
            "last_result": "",
            "runs": 0,
            "errors": 0,
        }

    # ------------------------------------------------------------------
    def _emit(self, **kw):
        self.status.update(kw)
        self.events.put(dict(self.status))

    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self, st: dict):
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------
    def trigger_now(self):
        """前台按钮：立即抓取一次."""
        self._force_run.set()

    def stop(self):
        self._stop.set()
        self._force_run.set()  # 打断等待

    # ------------------------------------------------------------------
    def _run_cycle(self):
        """执行一轮抓取（daily，周一加跑 weekly）."""
        from src.orchestrator import Orchestrator
        t0 = time.time()
        self._emit(state="抓取中…")
        orch = Orchestrator(config=self.config)
        r = orch.run_daily(since_days=1, send=self.send_email)
        parts = [
            f"新闻{r.get('news_count', 0)}",
            f"学术{r.get('academic_count', 0)}",
            f"金融{r.get('finance_count', 0)}",
            f"政策{r.get('policy_count', 0)}",
        ]
        st = self._load_state()
        # 每周一跑 weekly（每天只跑一次）
        today = datetime.now().strftime("%Y-%m-%d")
        if datetime.now().weekday() == 0 and st.get("last_weekly") != today:
            try:
                w = orch.run_weekly(since_days=7, send=self.send_email)
                parts.append(f"周报金融{w.get('finance_count', 0)}")
                st["last_weekly"] = today
            except Exception as e:
                parts.append(f"周报失败:{type(e).__name__}")
                st["last_weekly_error"] = str(e)
        cost = time.time() - t0
        return " | ".join(parts) + f"（{cost:.0f}s）", st

    def run(self):
        interval = timedelta(hours=self.interval_h)
        st = self._load_state()
        last = None
        if st.get("last_run"):
            try:
                last = datetime.strptime(st["last_run"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                last = None

        while not self._stop.is_set():
            now = datetime.now()
            due = (last is None) or (now - last >= interval)
            if due or self._force_run.is_set():
                self._force_run.clear()
                try:
                    result, st2 = self._run_cycle()
                    st.update(st2)
                    last = datetime.now()
                    st["last_run"] = last.strftime("%Y-%m-%d %H:%M:%S")
                    self._save_state(st)
                    self._emit(
                        state="空闲",
                        last_run=st["last_run"],
                        next_run=(last + interval).strftime("%H:%M"),
                        last_result=result,
                        runs=self.status["runs"] + 1,
                    )
                except Exception as e:
                    self._emit(
                        state="出错（将重试）",
                        last_result=f"{type(e).__name__}: {e}",
                        errors=self.status["errors"] + 1,
                    )
                    traceback.print_exc()
                    # 出错后 10 分钟重试
                    last = datetime.now() - interval + timedelta(minutes=10)
            else:
                nxt = (last + interval).strftime("%H:%M") if last else "即将开始"
                if self.status.get("next_run") != nxt or self.status["state"] != "空闲":
                    self._emit(state="空闲", next_run=nxt,
                               last_run=st.get("last_run", ""))
            # 细粒度等待，便于响应 stop / trigger_now
            self._force_run.wait(timeout=30)
