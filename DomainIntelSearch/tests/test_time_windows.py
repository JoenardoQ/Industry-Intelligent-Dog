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


def test_long_period_windows_follow_last_success_only_after_a_full_cycle():
    now = datetime(2026, 12, 31, 12, 0, tzinfo=TZ)
    no_history = periodic_window("fiveyear", now=now)
    assert (no_history.end - no_history.start).days == 1826
    recent = periodic_window(
        "biennial", now=now, last_success="2026-01-01T12:00:00+08:00")
    assert recent.reason == "history_shorter_than_cycle"
    assert (recent.end - recent.start).days == 730


def test_dst_gap_fold_and_timezone_changes_have_stable_unique_schedule_identity():
    from src.background_worker import schedule_identity, schedule_moment

    ny = ZoneInfo("America/New_York")
    fall_schedule = {"action": "daily", "local_time": "01:30",
                     "timezone": "America/New_York"}
    first = datetime(2026, 11, 1, 1, 45, tzinfo=ny, fold=0)
    second = datetime(2026, 11, 1, 1, 45, tzinfo=ny, fold=1)
    first_key, first_moment, _ = schedule_moment(fall_schedule, first)
    second_key, second_moment, _ = schedule_moment(fall_schedule, second)
    assert first_key == second_key == "2026-11-01"
    assert first_moment.fold == second_moment.fold == 0
    assert schedule_identity(fall_schedule, first_key, first_moment) == \
        schedule_identity(fall_schedule, second_key, second_moment)

    spring = {"action": "daily", "local_time": "02:30",
              "timezone": "America/New_York"}
    key, shifted, _ = schedule_moment(
        spring, datetime(2026, 3, 8, 4, 0, tzinfo=ny))
    assert key == "2026-03-08"
    assert (shifted.hour, shifted.minute) == (3, 30)
    shanghai = {"action": "daily", "local_time": "01:30",
                "timezone": "Asia/Shanghai"}
    assert schedule_identity(fall_schedule, first_key, first_moment) != \
        schedule_identity(shanghai, first_key, first_moment.astimezone(TZ))
