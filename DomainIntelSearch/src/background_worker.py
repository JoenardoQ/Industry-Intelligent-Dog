"""One-shot background scheduler shared with the foreground app poller."""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.time_windows import CollectionWindow, daily_window, periodic_window


SCHEDULE_ACTIONS = ("daily", "weekly", "monthly", "quarterly")
_CHILD_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE",
    "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "CODEX_HOME",
    "CLAUDE_CONFIG_DIR", "TMP", "TEMP", "TMPDIR", "LANG", "LANGUAGE",
    "LC_ALL", "LC_CTYPE", "TZ", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
})


@dataclass(frozen=True)
class ScheduleClaim:
    folder: str
    action: str
    period_key: str
    period_identity: str
    scheduled_at: datetime
    following_at: datetime
    schedule: dict
    window: CollectionWindow


@dataclass(frozen=True)
class WorkerSummary:
    claimed: int
    completed: int
    paused: int
    failed: int
    next_run_at: str | None


class SchedulePaused(ValueError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


def _zone(name: object) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or "Asia/Shanghai"))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区：{name}") from exc


def _wall_moment(zone: ZoneInfo, day: date, hour: int, minute: int) -> datetime:
    candidate = datetime.combine(day, time(hour=hour, minute=minute),
                                 tzinfo=zone).replace(fold=0)
    round_trip = candidate.astimezone(timezone.utc).astimezone(zone)
    requested = (day, hour, minute)
    actual = (round_trip.date(), round_trip.hour, round_trip.minute)
    return round_trip if actual != requested else candidate


def _following_month(moment: datetime, months: int) -> datetime:
    absolute = moment.year * 12 + moment.month - 1 + months
    year, month_index = divmod(absolute, 12)
    zone = moment.tzinfo
    assert isinstance(zone, ZoneInfo)
    return _wall_moment(zone, date(year, month_index + 1, moment.day),
                        moment.hour, moment.minute)


def schedule_moment(schedule: dict, now: datetime) -> tuple[str | None,
                                                              datetime, datetime]:
    """Resolve a due wall-clock moment deterministically across DST gaps/folds."""
    zone = _zone(schedule.get("timezone"))
    local = now.replace(tzinfo=zone) if now.tzinfo is None else now.astimezone(zone)
    try:
        hour, minute = (int(value) for value in str(schedule["local_time"]).split(":"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("时间必须是 HH:MM") from exc
    action = str(schedule.get("action") or "")
    if action == "daily":
        day = local.date()
        moment = _wall_moment(zone, day, hour, minute)
        following = _wall_moment(zone, day + timedelta(days=1), hour, minute)
        key = day.isoformat()
    elif action == "weekly":
        week_start = local.date() - timedelta(days=local.weekday())
        day = week_start + timedelta(days=int(schedule.get("weekday") or 0))
        moment = _wall_moment(zone, day, hour, minute)
        following = _wall_moment(zone, day + timedelta(days=7), hour, minute)
        iso = moment.isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
    elif action == "monthly":
        day = date(local.year, local.month, int(schedule.get("monthday") or 1))
        moment = _wall_moment(zone, day, hour, minute)
        following = _following_month(moment, 1)
        key = f"{moment.year}-{moment.month:02d}"
    elif action == "quarterly":
        quarter_month = ((local.month - 1) // 3) * 3 + 1
        day = date(local.year, quarter_month, int(schedule.get("monthday") or 1))
        moment = _wall_moment(zone, day, hour, minute)
        following = _following_month(moment, 3)
        key = f"{moment.year}-Q{((quarter_month - 1) // 3) + 1}"
    else:
        raise ValueError("不支持的调度动作")
    if local < moment:
        return None, moment, moment
    return key, moment, following


def schedule_identity(schedule: dict, period_key: str,
                      moment: datetime) -> str:
    zone_name = str(schedule.get("timezone") or "Asia/Shanghai")
    instant = moment.astimezone(timezone.utc).isoformat(timespec="seconds")
    return f"{period_key}|{zone_name}|{instant}"


def _window(schedule: dict, now: datetime) -> CollectionWindow:
    zone_name = str(schedule.get("timezone") or "Asia/Shanghai")
    if schedule["action"] == "daily":
        return daily_window(now, zone_name)
    last = schedule.get("last_success_boundary") or schedule.get("last_success_at")
    return periodic_window(schedule["action"], now=now, last_success=last,
                           timezone_name=zone_name)


def claim_due_schedules(repo, *, now: datetime, owner: str,
                        poll_seconds: float, origin: str = "app") -> list[ScheduleClaim]:
    claims = []
    for schedule in repo.list_schedules():
        if not schedule["enabled"] or schedule.get("runtime_status") == "paused":
            continue
        key, moment, following = schedule_moment(schedule, now)
        repo.set_schedule_next_run(
            schedule["folder"], schedule["action"],
            following.isoformat(timespec="minutes"))
        if not key:
            continue
        local_now = now.astimezone(moment.tzinfo)
        delay = (local_now - moment).total_seconds()
        if not schedule["catch_up"] and delay > float(poll_seconds) * 2:
            continue
        identity = schedule_identity(schedule, key, moment)
        if not repo.claim_schedule(
                schedule["folder"], schedule["action"], key, owner,
                period_identity=identity, origin=origin):
            continue
        claims.append(ScheduleClaim(
            schedule["folder"], schedule["action"], key, identity,
            moment, following, dict(schedule), _window(schedule, now)))
    return claims


def _safe_environment(data_root: Path, project_root: Path) -> dict[str, str]:
    clean = {key: value for key, value in os.environ.items()
             if key.upper() in _CHILD_ENV_ALLOWLIST}
    clean.update({"DOMAIN_INTEL_DATA_ROOT": str(data_root),
                  "INTDOG_PROJECT_ROOT": str(project_root), "PYTHONUTF8": "1",
                  "INTDOG_DISABLE_EMAIL": "1"})
    return clean


def _default_command(arguments: list[str]) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "cli", *arguments]
    return [sys.executable, "-m", "src.main", *arguments]


class BackgroundWorker:
    def __init__(self, data_root: str | Path, jobs, *, search_root: str | Path,
                 project_root: str | Path, readiness=None, command_builder=None):
        from intdog_core import IntDogService

        self.data_root = Path(data_root)
        self.service = IntDogService(self.data_root)
        self.repo = self.service.repo
        self.jobs = jobs
        self.search_root = Path(search_root)
        self.project_root = Path(project_root)
        if readiness is None:
            from src.services.provider_readiness import provider_readiness
            readiness = provider_readiness
        self.readiness = readiness
        self.command_builder = command_builder or _default_command
        self.owner = f"background-worker:{os.getpid()}:{uuid.uuid4().hex}"

    @staticmethod
    def _window_dict(window: CollectionWindow) -> dict:
        return {"start": window.start.isoformat(timespec="seconds"),
                "end": window.end.isoformat(timespec="seconds"),
                "timezone": str(window.end.tzinfo)}

    def _job(self, claim: ScheduleClaim):
        schedule, folder, action = claim.schedule, claim.folder, claim.action
        if action == "daily":
            title = "自动抓取每日情报"
            arguments = ["crawl-daily", "--folder", folder]
            provider, model = "public_sources", ""
        elif schedule.get("pipeline_mode") == "aggregate":
            title = f"自动聚合{action}情报"
            arguments = [f"crawl-{action}", "--folder", folder]
            provider, model = "public_sources", ""
        else:
            title = f"自动生成{action}报告"
            provider = str(schedule.get("provider") or "")
            if not provider:
                raise SchedulePaused("provider_required", "生成计划必须显式选择 Provider")
            ready = self.readiness(provider, self.data_root / folder)
            if not ready.get("ready"):
                raise SchedulePaused(
                    "provider_not_ready",
                    f"Provider {provider} 未就绪：{ready.get('detail', '请检查连接设置')}")
            model = str(ready.get("model") or "")
            arguments = ["generate-period", "--folder", folder,
                         "--kind", action, "--provider", provider,
                         "--execution-mode", "direct"]
        if "--execution-mode" not in arguments:
            arguments.extend(["--provider", provider, "--execution-mode", "direct"])
        window = self._window_dict(claim.window)
        job = self.jobs.start(
            self.command_builder(arguments), cwd=self.search_root,
            title=f"{title} · {folder}", timeout=3600,
            env=_safe_environment(self.data_root, self.project_root),
            metadata={
                "folder": folder, "operation": action,
                "operation_payload": {
                    "action": action, "folder": folder, "provider": provider,
                    "execution_mode": "direct",
                    "pipeline_mode": schedule.get("pipeline_mode", "generate")},
                "origin": "background_worker", "provider": provider,
                "model": model, "time_window": window,
                "schedule_action": action,
            })
        self.repo.set_schedule_job(folder, action, self.owner, job.run_id)
        return job, window

    def run_once(self, now: datetime) -> WorkerSummary:
        wake_id = self.repo.begin_worker_wakeup(
            self.owner, origin="background_worker")
        completed = paused = failed = 0
        claims: list[ScheduleClaim] = []
        try:
            claims = claim_due_schedules(
                self.repo, now=now, owner=self.owner, poll_seconds=15,
                origin="background_worker")
            for claim in claims:
                try:
                    job, window = self._job(claim)
                    result = job.wait(3660)
                    status = str(getattr(result, "status", "interrupted") or "interrupted")
                    error = str(getattr(result, "error", "") or "")
                    if status == "completed":
                        completed += 1
                    elif status == "paused":
                        paused += 1
                    else:
                        failed += 1
                    self.repo.finish_schedule(
                        claim.folder, claim.action, self.owner,
                        success=status == "completed", outcome=status,
                        error=error, error_category=(
                            "partial" if status == "partial" else
                            "worker_process" if status != "completed" else ""),
                        successful_boundary=window["end"], time_window=window)
                except SchedulePaused as exc:
                    paused += 1
                    self.repo.finish_schedule(
                        claim.folder, claim.action, self.owner, success=False,
                        outcome="paused", error=str(exc), error_category=exc.category,
                        time_window=self._window_dict(claim.window))
                except Exception as exc:
                    failed += 1
                    self.repo.finish_schedule(
                        claim.folder, claim.action, self.owner, success=False,
                        outcome="failed", error=str(exc),
                        error_category=type(exc).__name__,
                        time_window=self._window_dict(claim.window))
            next_values = [str(row.get("next_run_at")) for row in self.repo.list_schedules()
                           if row.get("enabled") and row.get("next_run_at") and
                           row.get("runtime_status") != "paused"]
            summary = WorkerSummary(len(claims), completed, paused, failed,
                                    min(next_values) if next_values else None)
            self.repo.finish_worker_wakeup(
                wake_id, status="completed" if failed == 0 else "partial",
                summary=asdict(summary))
            return summary
        except Exception as exc:
            summary = WorkerSummary(len(claims), completed, paused, failed + 1, None)
            self.repo.finish_worker_wakeup(
                wake_id, status="failed", summary=asdict(summary),
                error={"category": type(exc).__name__, "message": str(exc)})
            raise
