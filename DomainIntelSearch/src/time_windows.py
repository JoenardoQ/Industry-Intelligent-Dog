"""Single source of truth for collection and periodic artifact windows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


PERIOD_LENGTHS = {
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "quarterly": timedelta(days=90),
    "semiannual": timedelta(days=183),
    "biennial": timedelta(days=730),
    "fiveyear": timedelta(days=1826),
}


@dataclass(frozen=True)
class CollectionWindow:
    start: datetime
    end: datetime
    reason: str
    mode: str

    def as_dict(self) -> dict:
        return {
            "window_start": self.start.isoformat(timespec="seconds"),
            "window_end": self.end.isoformat(timespec="seconds"),
            "timezone": str(self.end.tzinfo),
            "window_reason": self.reason,
            "collection_mode": self.mode,
        }


def _aware(value: datetime, timezone: ZoneInfo) -> datetime:
    return value.replace(tzinfo=timezone) if value.tzinfo is None else value.astimezone(timezone)


def daily_window(now: datetime | None = None, timezone_name: str = "Asia/Shanghai") -> CollectionWindow:
    timezone = ZoneInfo(timezone_name)
    end = _aware(now or datetime.now(timezone), timezone)
    previous = end.date() - timedelta(days=1)
    start = datetime.combine(previous, time(hour=4), tzinfo=timezone)
    return CollectionWindow(start, end, "previous_local_day_04_to_now", "scheduled_incremental")


def periodic_window(
    kind: str,
    *,
    now: datetime | None = None,
    last_success: datetime | str | None = None,
    timezone_name: str = "Asia/Shanghai",
) -> CollectionWindow:
    if kind not in PERIOD_LENGTHS:
        raise ValueError(f"未知周期：{kind}")
    timezone = ZoneInfo(timezone_name)
    end_now = _aware(now or datetime.now(timezone), timezone)
    length = PERIOD_LENGTHS[kind]
    previous = parse_datetime(last_success, timezone) if last_success else None
    if previous is not None and end_now - previous >= length:
        return CollectionWindow(previous, previous + length, "continue_from_last_success", "scheduled_incremental")
    reason = "no_success_history" if previous is None else "history_shorter_than_cycle"
    return CollectionWindow(end_now - length, end_now, reason, "rolling_backfill")


def parse_datetime(value: datetime | str | None, timezone: ZoneInfo) -> datetime | None:
    if isinstance(value, datetime):
        return _aware(value, timezone)
    if not value:
        return None
    try:
        return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")), timezone)
    except ValueError:
        return None


def intersects_item(window: CollectionWindow, item: dict) -> bool:
    """Accept precise timestamps inside the window and date-only records whose day intersects it."""
    raw = item.get("published_at") or item.get("published") or item.get("date")
    if not raw:
        return False
    timezone = window.end.tzinfo
    text = str(raw).strip()
    if len(text) == 10:
        try:
            day = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return False
        day_start = datetime.combine(day, time.min, tzinfo=timezone)
        day_end = day_start + timedelta(days=1)
        return day_end > window.start and day_start <= window.end
    parsed = parse_datetime(text, timezone)
    return parsed is not None and window.start <= parsed <= window.end
