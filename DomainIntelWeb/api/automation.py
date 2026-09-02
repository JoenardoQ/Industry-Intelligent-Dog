"""Single-owner durable scheduler for the default Web workbench."""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime
from pathlib import Path

from .commands import search_command, search_cwd
from src.background_worker import (
    ScheduleClaim,
    SchedulePaused,
    _safe_environment,
    claim_due_schedules,
    schedule_moment,
)

ACTIONS = ("daily", "weekly", "monthly", "quarterly")
COMMANDS = {"daily": ("自动抓取每日情报", "crawl-daily")}


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
                pipeline_mode="aggregate" if action == "daily" else "generate",
                provider="public_sources" if action == "daily" else "")
        self.service.update_control(folder, {"scheduler_owner": "web"})

    def tick(self) -> int:
        enqueued = 0
        claims = claim_due_schedules(
            self.repo, now=self.now(), owner=self.owner,
            poll_seconds=self.poll_seconds, origin="system_schedule")
        for claim in claims:
            try:
                self._start_job(
                    claim.folder, claim.action, schedule=claim.schedule,
                    claim=claim)
                enqueued += 1
            except SchedulePaused as exc:
                self.repo.finish_schedule(
                    claim.folder, claim.action, self.owner, success=False,
                    outcome="paused", error=str(exc),
                    error_category=exc.category,
                    time_window=self._window_dict(claim))
            except Exception as exc:
                self.repo.finish_schedule(
                    claim.folder, claim.action, self.owner, success=False,
                    outcome="failed", error=str(exc),
                    error_category=type(exc).__name__,
                    time_window=self._window_dict(claim))
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
                   schedule: dict | None = None,
                   claim: ScheduleClaim | None = None):
        schedule = schedule or self.repo.get_schedule(folder, action)
        provider = "public_sources"
        model = ""
        if action == "daily":
            title, args = COMMANDS[action][0], ["crawl-daily", "--folder", folder]
        elif schedule.get("pipeline_mode") == "aggregate":
            title, args = f"自动聚合{action}情报", [f"crawl-{action}", "--folder", folder]
        else:
            title = f"自动生成{action}报告"
            provider = str(schedule.get("provider") or
                           self.repo.effective_workflow_settings(folder, action)["provider"])
            if not provider:
                raise SchedulePaused("provider_required", "生成计划必须显式选择 Provider")
            ready = self.readiness(provider, self.data_root / folder)
            if not ready.get("ready"):
                raise SchedulePaused(
                    "provider_not_ready",
                    f"Provider {provider} 未就绪：{ready.get('detail', '请检查连接设置')}")
            model = str(ready.get("model") or "")
            args = ["generate-period", "--folder", folder, "--kind", action,
                    "--provider", provider, "--execution-mode", "direct"]
        if "--execution-mode" not in args:
            args.extend(["--provider", provider, "--execution-mode", "direct"])

        time_window = self._window_dict(claim) if claim else None

        def finished(result) -> None:
            if scheduled:
                status = str(result.status or "interrupted")
                self.repo.finish_schedule(
                    folder, action, self.owner,
                    success=status == "completed", outcome=status,
                    error=result.error,
                    error_category=("partial" if status == "partial" else
                                    "worker_process" if status != "completed" else ""),
                    successful_boundary=(time_window or {}).get("end"),
                    time_window=time_window)

        job = self.jobs.start(
            search_command(args),
            cwd=search_cwd(self.search_root), title=f"{title} · {folder}", timeout=3600,
            on_finish=finished,
            env=_safe_environment(self.data_root, self.project_root),
            metadata={"folder": folder, "operation": action,
                      "operation_payload": {"action": action, "folder": folder,
                                            "provider": provider,
                                            "execution_mode": "direct",
                                            "pipeline_mode": schedule.get("pipeline_mode", "generate")},
                      "origin": "system_schedule" if scheduled else "manual",
                      "provider": provider, "model": model,
                      "time_window": time_window,
                      "schedule_action": action})
        if scheduled:
            self.repo.set_schedule_job(folder, action, self.owner, job.run_id)
        return job

    @staticmethod
    def _window_dict(claim: ScheduleClaim) -> dict:
        return {
            "start": claim.window.start.isoformat(timespec="seconds"),
            "end": claim.window.end.isoformat(timespec="seconds"),
            "timezone": str(claim.window.end.tzinfo),
        }
