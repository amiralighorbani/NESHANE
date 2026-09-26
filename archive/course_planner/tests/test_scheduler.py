"""تست‌های موتور برنامه‌ریزی (بدون نیاز به اجرای سرور)."""

from __future__ import annotations

import pytest

from app.models import Course, Meeting, Parity, PlannerInput, Prefs, Section, parse_time
from app.scheduler import (
    layout_stats,
    meetings_conflict,
    score_schedule,
    solve_planner,
)


def section(course_id: str, meetings, preferred: bool = False) -> Section:
    return Section(
        id=f"{course_id}-x",
        course_id=course_id,
        preferred=preferred,
        meetings=[Meeting(**meeting) for meeting in meetings],
    )


def course(course_id: str, credits: int = 3, priority: int = 2, must: bool = False, sections=()) -> Course:
    return Course(id=course_id, name=f"درس {course_id}", credits=credits, priority=priority, must=must, sections=list(sections))


# --------------------------------------------------------------------- زمان


def test_parse_time_accepts_persian_digits() -> None:
    assert parse_time("۰۸:۳۰") == 8 * 60 + 30
    assert parse_time("8:30") == 8 * 60 + 30
    assert parse_time("08.15") == 8 * 60 + 15
    assert parse_time("bad") is None


# ---------------------------------------------------------------- هفته‌درمیان


def test_biweekly_parity_rules() -> None:
    monday_odd = Meeting(day=0, start=8 * 60, end=9 * 60, parity="odd")
    monday_even = Meeting(day=0, start=8 * 60, end=9 * 60, parity="even")
    monday_all = Meeting(day=0, start=8 * 60, end=9 * 60, parity="all")
    other_day = Meeting(day=1, start=8 * 60, end=9 * 60, parity="all")

    assert meetings_conflict(monday_odd, monday_even) is False
    assert meetings_conflict(monday_odd, monday_all) is True
    assert meetings_conflict(monday_all, monday_even) is True
    assert meetings_conflict(monday_odd, other_day) is False
    # بازه‌های چسبیده تداخل ندارند
    assert meetings_conflict(monday_odd, Meeting(day=0, start=9 * 60, end=10 * 60, parity="odd")) is False


def test_odd_and_even_sections_can_share_the_same_slot() -> None:
    odd = course("c1", sections=[section("c1", [{"day": 4, "start": "13:00", "end": "15:00", "parity": "odd"}])])
    even = course("c2", sections=[section("c2", [{"day": 4, "start": "13:00", "end": "15:00", "parity": "even"}])])
    planner = PlannerInput(courses=[odd, even], target_credits=6, max_credits=6)

    result = solve_planner(planner)

    assert result.feasible
    assert result.solutions[0].total_credits == 6, "هر دو درس باید با هم جا شوند"


# ------------------------------------------------------------------ قیدها


def test_blocked_hours_remove_conflicting_sections() -> None:
    morning = section("c1", [{"day": 0, "start": "08:00", "end": "09:30"}])
    evening = section("c1", [{"day": 0, "start": "18:00", "end": "19:30"}])
    planner = PlannerInput(
        courses=[course("c1", sections=[morning, evening])],
        blocked=[Meeting(day=0, start="08:00", end="10:00")],
        target_credits=3,
        max_credits=6,
    )

    result = solve_planner(planner)

    assert result.feasible
    assert result.solutions[0].sections[0] is evening


def test_credit_cap_is_a_hard_constraint() -> None:
    planner = PlannerInput(
        courses=[
            course("c1", credits=3, sections=[section("c1", [{"day": 0, "start": "08:00", "end": "09:30"}])]),
            course("c2", credits=3, sections=[section("c2", [{"day": 1, "start": "08:00", "end": "09:30"}])]),
            course("c3", credits=3, sections=[section("c3", [{"day": 2, "start": "08:00", "end": "09:30"}])]),
        ],
        target_credits=9,
        max_credits=6,
    )

    result = solve_planner(planner)

    assert result.feasible
    for solution in result.solutions:
        assert solution.total_credits <= 6


def test_must_take_courses_are_always_included() -> None:
    planner = PlannerInput(
        courses=[
            course("c1", credits=3, must=True, sections=[section("c1", [{"day": 0, "start": "08:00", "end": "09:30"}])]),
            course("c2", credits=3, sections=[section("c2", [{"day": 0, "start": "08:00", "end": "09:30"}])]),
            course("c3", credits=3, sections=[section("c3", [{"day": 2, "start": "08:00", "end": "09:30"}])]),
        ],
        target_credits=6,
        max_credits=6,
        prefs=Prefs(fit=3.0),
    )

    result = solve_planner(planner)

    assert result.feasible
    for solution in result.solutions:
        included = {item.course_id for item in solution.sections}
        assert "c1" in included
        assert "c2" not in included  # با c1 در همان ساعت تداخل دارد


def test_infeasible_when_must_courses_conflict_everywhere() -> None:
    planner = PlannerInput(
        courses=[
            course("c1", must=True, sections=[section("c1", [{"day": 0, "start": "08:00", "end": "09:30"}])]),
            course("c2", must=True, sections=[section("c2", [{"day": 0, "start": "08:00", "end": "09:30"}])]),
        ],
        target_credits=6,
        max_credits=12,
    )

    result = solve_planner(planner)

    assert not result.feasible
    assert any("تداخل کامل" in message for message in result.diagnostics)


# ------------------------------------------------------------------ امتیاز


def test_solver_prefers_fewer_days_and_no_gaps() -> None:
    contiguous = section("c1", [{"day": 0, "start": "08:00", "end": "09:30"}, {"day": 0, "start": "09:30", "end": "11:00"}])
    scattered = section("c1", [{"day": 0, "start": "08:00", "end": "09:30"}, {"day": 3, "start": "16:00", "end": "17:30"}])
    planner = PlannerInput(
        courses=[course("c1", sections=[scattered, contiguous])],
        target_credits=3,
        max_credits=6,
        prefs=Prefs(fit=1.0, few_days=2.0, few_gaps=2.0),
    )

    result = solve_planner(planner)

    assert result.solutions[0].sections[0] is contiguous
    stats = result.solutions[0].stats
    assert stats.day_count == 1
    assert stats.gap_minutes == 0


def test_hitting_the_credit_target_beats_extra_courses() -> None:
    planner = PlannerInput(
        courses=[
            course("c1", credits=3, priority=1, sections=[section("c1", [{"day": 0, "start": "08:00", "end": "09:30"}])]),
            course("c2", credits=3, priority=1, sections=[section("c2", [{"day": 1, "start": "08:00", "end": "09:30"}])]),
        ],
        target_credits=3,
        max_credits=6,
        prefs=Prefs(fit=3.0, few_days=0.0),
    )

    result = solve_planner(planner)

    assert result.solutions[0].total_credits == 3


def test_layout_stats_counts_gaps_and_window_penalties() -> None:
    prefs = Prefs(day_start=8 * 60, day_end=16 * 60)
    stats = layout_stats(
        [section("c1", [{"day": 0, "start": "07:00", "end": "08:00"}, {"day": 0, "start": "10:00", "end": "18:00"}])],
        prefs,
    )
    assert stats.days == [0]
    assert stats.gap_minutes == 120
    assert stats.early_minutes == 60
    assert stats.late_minutes == 120
    assert score_schedule(6, 6, 40.0, stats, prefs) < 40.0


# ------------------------------------------------------------- جانشین‌ها


def test_provides_best_plus_three_distinct_alternatives() -> None:
    courses = []
    for index in range(4):
        courses.append(
            course(
                f"c{index}",
                credits=3,
                sections=[
                    section(f"c{index}", [{"day": index, "start": "08:00", "end": "09:30"}]),
                    section(f"c{index}", [{"day": index, "start": "11:00", "end": "12:30"}]),
                    section(f"c{index}", [{"day": index + 1, "start": "14:00", "end": "15:30"}]),
                ],
            )
        )
    planner = PlannerInput(courses=courses, target_credits=12, max_credits=12)

    result = solve_planner(planner)

    assert len(result.solutions) == 4
    fingerprints = {tuple(sorted(item.id + str(id(item)) for item in solution.sections)) for solution in result.solutions}
    assert len(fingerprints) == 4, "گزینه‌ها باید واقعاً متفاوت باشند"
    assert all(solution.diff_notes or index == 0 for index, solution in enumerate(result.solutions))


def test_unused_sections_are_reported_as_excluded() -> None:
    planner = PlannerInput(
        courses=[
            course("c1", credits=3, sections=[section("c1", [{"day": 0, "start": "08:00", "end": "09:30"}])]),
            course("c2", credits=3, sections=[section("c2", [{"day": 0, "start": "08:00", "end": "09:30"}])]),
        ],
        target_credits=6,
        max_credits=6,
    )

    result = solve_planner(planner)

    assert result.feasible
    assert len(result.solutions[0].excluded) == 1
    assert result.solutions[0].total_credits == 3


def test_course_without_sections_is_reported() -> None:
    planner = PlannerInput(courses=[course("c1", sections=[])], target_credits=3, max_credits=6)

    result = solve_planner(planner)

    assert not result.feasible
    assert any("هیچ کلاسی ثبت نشده" in message for message in result.diagnostics)


def test_empty_schedule_is_never_recommended() -> None:
    course_a = course("c1", credits=3, sections=[section("c1", [{"day": 0, "start": "08:00", "end": "09:30"}])])
    planner = PlannerInput(courses=[course_a], target_credits=3, max_credits=6, prefs=Prefs(fit=0.0))

    result = solve_planner(planner)

    assert result.feasible
    assert result.solutions[0].sections, "حتی با وزن صفرِ هدف، برنامه‌ی خالی پیشنهاد نمی‌شود"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
