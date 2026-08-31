"""Single-owner durable scheduler for the default Web workbench."""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .commands import search_command, search_cwd

ACTIONS = ("daily", "weekly", "monthly", "quarterly")
COMMANDS = {"daily": ("自动抓取每日情报", "crawl-daily")}


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区：{name}") from exc


def schedule_moment(schedule: dict, now: datetime) -> tuple[str | None, datetime, datetime]:
    """Return (due period key, current scheduled moment, next moment)."""
    zone = _timezone(str(schedule.get("timezone") or "Asia/Shanghai"))
    local = now.astimezone(zone)
    hour, minute = (int(value) for value in str(schedule["local_time"]).split(":"))
    action = schedule["action"]
    if action == "daily":
        moment = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        key, following = local.date().isoformat(), moment + timedelta(days=1)
    elif action == "weekly":
        start = local - timedelta(days=local.weekday())
        moment = start.replace(hour=hour, minute=minute, second=0, microsecond=0)
        moment += timedelta(days=int(schedule.get("weekday") or 0))
        iso = moment.isocalendar()
        key, following = f"{iso.year}-W{iso.week:02d}", moment + timedelta(days=7)
    elif action == "monthly":
        moment = local.replace(day=int(schedule.get("monthday") or 1), hour=hour,
                               minute=minute, second=0, microsecond=0)
        if moment.month == 12:
            following = moment.replace(year=moment.year + 1, month=1)
        else:
            following = moment.replace(month=moment.month + 1)
        key = f"{moment.year}-{moment.month:02d}"
    elif action == "quarterly":
        quarter_month = ((local.month - 1) // 3) * 3 + 1
        moment = local.replace(month=quarter_month,
                               day=int(schedule.get("monthday") or 1), hour=hour,
                               minute=minute, second=0, microsecond=0)
        following = (moment.replace(year=moment.year + 1, month=1)
                     if quarter_month == 10 else moment.replace(month=quarter_month + 3))
        key = f"{moment.year}-Q{((quarter_month - 1) // 3) + 1}"
    else:
        raise ValueError("不支持的调度动作")
    if local < moment:
        return None, moment, moment
    return key, moment, following


class AutomationScheduler:
    """Poll durable schedules and enqueue each period at most once."""

    def __init__(self, data_root: Path, jobs, *, search_root: Path,
                 project_root: Path, poll_seconds: float = 15.0,
                 now=lambda: datetime.now().astimezone(), readiness=None):
        self.data_root = Path(data_root)
        from intdog_core import IntDogService
        self.service = IntDogService(self.data_root)
        self.repo = self.service.repo
        self.jobs = jobs
        self.search_root = Path(search_root)
        self.project_root = Path(project_root)
        self.poll_seconds = max(0.1, float(poll_seconds))
        self.now = now
        if readiness is None:
            from src.services.provider_readiness import provider_readiness
            readiness = provider_readiness
        self.readiness = readiness
        self.owner = f"web:{os.getpid()}:{uuid.uuid4().hex}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        for industry in self.repo.list_industries():
            self._ensure_schedules(industry["folder"])
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="intdog-automation")
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # Per-schedule failures are persisted by tick. A poller must not
                # take down the local API because a row or timezone is malformed.
                pass
            self._stop.wait(self.poll_seconds)

    def snapshot(self, folder: str) -> list[dict]:
        self._ensure_schedules(folder)
        rows = []
        existing = {row["action"]: row for row in self.repo.list_schedules(folder)}
        for action in ACTIONS:
            row = existing.get(action) or self.repo.ensure_schedule(folder, action)
            try:
                _, _, next_moment = schedule_moment(row, self.now())
                row["next_run_at"] = next_moment.isoformat(timespec="minutes")
                self.repo.set_schedule_next_run(
                    folder, action, row["next_run_at"])
            except (TypeError, ValueError):
                row["next_run_at"] = None
            row["enabled"] = bool(row["enabled"])
            row["catch_up"] = bool(row["catch_up"])
            rows.append(row)
        return rows

    def _ensure_schedules(self, folder: str) -> None:
        if self.repo.list_schedules(folder):
            return
        control = self.service.read_json(self.data_root / folder / "control.json", {})
        enabled = bool(control.get("periodic_enabled", False))
        weekdays = {"monday": 0, "tuesday": 1, "wednesday": 2,
                    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        weekly = weekdays.get(str(control.get("weekly_day") or "monday").casefold(), 0)
        try:
            monthday = max(1, min(28, int(control.get("monthly_day") or 1)))
        except (TypeError, ValueError):
            monthday = 1
        local_time = str(control.get("daily_time") or "08:00")
        try:
            datetime.strptime(local_time, "%H:%M")
        except ValueError:
            local_time = "08:00"
        for action in ACTIONS:
            self.repo.update_schedule(
                folder, action, enabled=enabled, local_time=local_time,
                weekday=weekly, monthday=monthday, catch_up=True,
                pipeline_mode="generate", provider="codex")
        self.service.update_control(folder, {"scheduler_owner": "web"})

    def tick(self) -> int:
        enqueued = 0
        for schedule in self.repo.list_schedules():
            if not schedule["enabled"]:
                continue
            folder, action = schedule["folder"], schedule["action"]
            try:
                key, moment, following = schedule_moment(schedule, self.now())
                self.repo.set_schedule_next_run(
                    folder, action, following.isoformat(timespec="minutes"))
                if not key:
                    continue
                delay = (self.now().astimezone(moment.tzinfo) - moment).total_seconds()
                if not schedule["catch_up"] and delay > self.poll_seconds * 2:
                    continue
                if not self.repo.claim_schedule(folder, action, key, self.owner):
                    continue
                self._start_job(folder, action, schedule=schedule)
                enqueued += 1
            except Exception as exc:
                self.repo.finish_schedule(folder, action, self.owner,
                                          success=False, error=str(exc))
        return enqueued

    def run_now(self, folder: str, action: str):
        if action not in ACTIONS:
            raise ValueError("不支持的调度动作")
        schedule = self.repo.get_schedule(folder, action)
        return self._start_job(folder, action, scheduled=False, schedule=schedule)

    def configure(self, folder: str, action: str, **changes) -> dict:
        row = self.repo.update_schedule(folder, action, **changes)
        schedules = self.repo.list_schedules(folder)
        self.service.update_control(folder, {
            "periodic_enabled": any(bool(item["enabled"]) for item in schedules),
            "scheduler_owner": "web",
        })
        return row

    def _start_job(self, folder: str, action: str, *, scheduled: bool = True,
                   schedule: dict | None = None):
        schedule = schedule or self.repo.get_schedule(folder, action)
        if action == "daily":
            title, args = COMMANDS[action][0], ["crawl-daily", "--folder", folder]
        elif schedule.get("pipeline_mode") == "aggregate":
            title, args = f"自动聚合{action}情报", [f"crawl-{action}", "--folder", folder]
        else:
            title = f"自动生成{action}报告"
            provider = str(schedule.get("provider") or "codex")
            ready = self.readiness(provider, self.data_root / folder)
            if not ready.get("ready"):
                raise ValueError(f"Provider {provider} 未就绪：{ready.get('detail', '请检查连接设置')}")
            args = ["generate-period", "--folder", folder, "--kind", action,
                    "--provider", provider]

        def finished(result) -> None:
            if scheduled:
                self.repo.finish_schedule(folder, action, self.owner,
                                          success=result.status == "completed",
                                          error=result.error)

        job = self.jobs.start(
            search_command(args),
            cwd=search_cwd(self.search_root), title=f"{title} · {folder}", timeout=3600,
            on_finish=finished,
            env={**os.environ, "DOMAIN_INTEL_DATA_ROOT": str(self.data_root),
                 "INTDOG_PROJECT_ROOT": str(self.project_root), "PYTHONUTF8": "1",
                 "INTDOG_DISABLE_EMAIL": "1"},
            metadata={"operation": action,
                      "operation_payload": {"action": action, "folder": folder,
                                            "provider": schedule.get("provider", ""),
                                            "pipeline_mode": schedule.get("pipeline_mode", "generate")},
                      "schedule_action": action})
        if scheduled:
            self.repo.set_schedule_job(folder, action, self.owner, job.run_id)
        return job
