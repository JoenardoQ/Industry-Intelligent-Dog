from datetime import datetime
from zoneinfo import ZoneInfo

from src.time_windows import daily_window, intersects_item, periodic_window


TZ = ZoneInfo("Asia/Shanghai")


def test_daily_window_is_previous_day_0400_to_current_system_time():
    now = datetime(2026, 8, 31, 17, 30, tzinfo=TZ)
    window = daily_window(now)
    assert window.start == datetime(2026, 8, 30, 4, 0, tzinfo=TZ)
    assert window.end == now
    assert window.reason == "previous_local_day_04_to_now"


def test_periodic_window_continues_only_after_full_cycle():
    now = datetime(2026, 8, 31, 12, 0, tzinfo=TZ)
    recent = periodic_window("weekly", now=now, last_success="2026-08-28T12:00:00+08:00")
    assert recent.start == datetime(2026, 8, 24, 12, 0, tzinfo=TZ)
    assert recent.end == now
    assert recent.reason == "history_shorter_than_cycle"

    continued = periodic_window("weekly", now=now, last_success="2026-08-20T12:00:00+08:00")
    assert continued.start == datetime(2026, 8, 20, 12, 0, tzinfo=TZ)
    assert continued.end == datetime(2026, 8, 27, 12, 0, tzinfo=TZ)
    assert continued.reason == "continue_from_last_success"


def test_periodic_window_without_history_uses_one_full_cycle():
    now = datetime(2026, 8, 31, 12, 0, tzinfo=TZ)
    window = periodic_window("quarterly", now=now)
    assert (window.end - window.start).days == 90
    assert window.reason == "no_success_history"


def test_date_only_item_is_kept_when_its_day_intersects_window():
    window = daily_window(datetime(2026, 8, 31, 9, 0, tzinfo=TZ))
    assert intersects_item(window, {"published_at": "2026-08-30"})
    assert not intersects_item(window, {"published_at": "2026-08-29"})
