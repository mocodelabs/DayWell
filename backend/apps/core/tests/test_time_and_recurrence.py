from datetime import UTC, date, datetime, time
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest

from apps.core.recurrence import RecurrenceError, normalize_rrule, occurrence_dates_between, occurrences_between
from apps.core.timeutils import day_bounds, localize, wall_time_exists, wall_time_is_ambiguous

NY = ZoneInfo("America/New_York")
NBO = ZoneInfo("Africa/Nairobi")


class TestLocalize:
    def test_nairobi_has_no_dst(self):
        assert localize(datetime(2026, 3, 8, 6, 30), NBO) == datetime(2026, 3, 8, 3, 30, tzinfo=UTC)

    def test_nonexistent_time_shifts_forward_by_gap(self):
        # 2026-03-08 02:30 does not exist in New York (02:00 → 03:00). Policy: shift forward → 03:30 EDT = 07:30 UTC.
        naive = datetime(2026, 3, 8, 2, 30)
        assert not wall_time_exists(naive, NY)
        assert localize(naive, NY) == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)

    def test_ambiguous_time_uses_first_occurrence(self):
        # 2026-11-01 01:30 happens twice in New York. Policy: the first (EDT, UTC-4) → 05:30 UTC.
        naive = datetime(2026, 11, 1, 1, 30)
        assert wall_time_is_ambiguous(naive, NY)
        assert localize(naive, NY) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)

    def test_dst_day_bounds_are_23_and_25_hours(self):
        s, e = day_bounds(date(2026, 3, 8), NY)
        assert (e - s).total_seconds() == 23 * 3600
        s, e = day_bounds(date(2026, 11, 1), NY)
        assert (e - s).total_seconds() == 25 * 3600


class TestNormalize:
    @pytest.mark.parametrize(
        "rule",
        [
            "FREQ=DAILY",
            "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR",
            "FREQ=MONTHLY;BYMONTHDAY=5",
            "FREQ=WEEKLY;INTERVAL=2",
            "FREQ=YEARLY",
            "FREQ=DAILY;COUNT=10",
            "FREQ=DAILY;UNTIL=20261231",
            "FREQ=HOURLY;INTERVAL=2;BYHOUR=9,11,13",
        ],
    )
    def test_valid(self, rule):
        assert normalize_rrule(rule).startswith("FREQ=")

    @pytest.mark.parametrize(
        "rule",
        ["FREQ=SECONDLY", "FREQ=MINUTELY", "FREQ=DAILY;COUNT=5;UNTIL=20261231", "FREQ=DAILY;FOO=1", "FREQ=DAILY;INTERVAL=0", "FREQ=DAILY;COUNT=999999", "nonsense", "FREQ=DAILY;UNTIL=2026"],
    )
    def test_invalid(self, rule):
        with pytest.raises(RecurrenceError):
            normalize_rrule(rule)

    def test_empty_means_no_recurrence(self):
        assert normalize_rrule("") == ""

    def test_canonical_order(self):
        assert normalize_rrule("BYDAY=MO;FREQ=WEEKLY;INTERVAL=2") == "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"


class TestOccurrences:
    def test_weekday_rule_keeps_local_wall_time_across_dst(self):
        # Every weekday at 06:30 New York — stays 06:30 local before and after the DST switch on 2026-03-08.
        rule = normalize_rrule("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR")
        start = datetime(2026, 3, 2, 6, 30)  # Monday
        out = occurrences_between(rule, start, NY, datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 3, 14, tzinfo=UTC))
        assert len(out) == 10
        assert {o.astimezone(NY).time() for o in out} == {time(6, 30)}
        assert out[0].hour == 11 and out[-1].hour == 10  # UTC offset changed, wall time did not

    def test_mon_wed_fri(self):
        out = occurrence_dates_between("FREQ=WEEKLY;BYDAY=MO,WE,FR", date(2026, 10, 5), date(2026, 10, 5), date(2026, 10, 18))
        assert [d.isoformat() for d in out] == ["2026-10-05", "2026-10-07", "2026-10-09", "2026-10-12", "2026-10-14", "2026-10-16"]

    def test_monthly_fifth_and_every_two_weeks(self):
        assert len(occurrence_dates_between("FREQ=MONTHLY;BYMONTHDAY=5", date(2026, 1, 5), date(2026, 1, 1), date(2026, 12, 31))) == 12
        biweekly = occurrence_dates_between("FREQ=WEEKLY;INTERVAL=2", date(2026, 1, 1), date(2026, 1, 1), date(2026, 2, 28))
        assert all((b - a).days == 14 for a, b in pairwise(biweekly))

    def test_count_and_until_end_series(self):
        assert len(occurrence_dates_between("FREQ=DAILY;COUNT=3", date(2026, 1, 1), date(2026, 1, 1), date(2026, 12, 31))) == 3
        until = occurrence_dates_between("FREQ=DAILY;UNTIL=20260105", date(2026, 1, 1), date(2026, 1, 1), date(2026, 12, 31))
        assert until[-1] == date(2026, 1, 5)

    def test_daily_through_spring_forward_gap(self):
        # A daily 02:30 alarm in New York: on the gap day it fires at 03:30 (shifted), never skipped or doubled.
        out = occurrences_between("FREQ=DAILY", datetime(2026, 3, 7, 2, 30), NY, datetime(2026, 3, 7, tzinfo=UTC), datetime(2026, 3, 10, tzinfo=UTC))
        assert [o.astimezone(NY).strftime("%d %H:%M") for o in out] == ["07 02:30", "08 03:30", "09 02:30"]

    def test_daily_through_fall_back_fires_once(self):
        out = occurrences_between("FREQ=DAILY", datetime(2026, 10, 31, 1, 30), NY, datetime(2026, 10, 31, tzinfo=UTC), datetime(2026, 11, 3, tzinfo=UTC))
        assert len(out) == 3

    def test_exclusions(self):
        start = datetime(2026, 10, 5, 9, 0)
        out = occurrences_between("FREQ=DAILY;COUNT=3", start, NBO, datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 30, tzinfo=UTC), exclude_local=[datetime(2026, 10, 6, 9, 0)])
        assert len(out) == 2
