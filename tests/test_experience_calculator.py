from datetime import date
from types import SimpleNamespace

import pytest

from app.services.experience_calculator import (
    calculate_full_time_years, career_level_for, is_internship_period,
)

TODAY = date(2026, 10, 2)


def period(start, end="", role=""):
    return SimpleNamespace(role=role, start=start, end=end)


# ---------- calculate_full_time_years ----------

def test_current_job_counts_up_to_today():
    # Jun 2024 - Oct 2026 inclusive = 29 months = 2.42y -> rounds to 2.5
    assert calculate_full_time_years([period("2024-06")], TODAY) == 2.5


@pytest.mark.parametrize("end", ["present", "Present", "CURRENT", "till date", "ongoing", "now", ""])
def test_present_variants(end):
    assert calculate_full_time_years([period("2024-06", end)], TODAY) == 2.5


def test_no_periods_is_zero():
    assert calculate_full_time_years([], TODAY) == 0


def test_single_month_counts_as_one_month():
    assert calculate_full_time_years([period("2024-06", "2024-06")], TODAY) == 0


def test_gap_between_jobs_is_not_counted():
    jobs = [period("2015-01", "2016-12"), period("2022-01", "2022-12")]  # 2y + 1y
    assert calculate_full_time_years(jobs, TODAY) == 3


def test_overlapping_jobs_counted_once():
    jobs = [period("2020-01", "2021-12"), period("2021-01", "2022-12")]  # union 2020-01..2022-12 = 3y
    assert calculate_full_time_years(jobs, TODAY) == 3


def test_nested_job_inside_another_counted_once():
    jobs = [period("2018-01", "2022-12"), period("2019-06", "2020-06")]
    assert calculate_full_time_years(jobs, TODAY) == 5


def test_unsorted_input():
    jobs = [period("2022-01", "2022-12"), period("2015-01", "2016-12")]
    assert calculate_full_time_years(jobs, TODAY) == 3


def test_back_to_back_jobs_do_not_double_count():
    jobs = [period("2020-01", "2020-12"), period("2021-01", "2021-12")]
    assert calculate_full_time_years(jobs, TODAY) == 2


@pytest.mark.parametrize("bad", ["", "abc", "2024", "2024-13", "2024-00", "June 2024"])
def test_bad_end_dates_are_skipped_not_crashing(bad):
    # an unparsable end date skips that period instead of raising
    result = calculate_full_time_years([period("2020-01", "2020-12"), period("2022-01", bad)], TODAY)
    assert result >= 1


@pytest.mark.parametrize("bad", ["abc", "2024", "2024-13", "June 2024"])
def test_bad_start_dates_are_skipped(bad):
    assert calculate_full_time_years([period(bad, "2024-12")], TODAY) == 0


def test_end_before_start_is_ignored():
    assert calculate_full_time_years([period("2024-06", "2023-01")], TODAY) == 0


def test_rounding_is_half_up_not_bankers():
    # 3 months = 0.25y -> 0.5 (banker's rounding would give 0.0)
    assert calculate_full_time_years([period("2024-01", "2024-03")], TODAY) == 0.5


def test_ten_year_career():
    assert calculate_full_time_years([period("2010-01", "2019-12")], TODAY) == 10


# ---------- career_level_for ----------

@pytest.mark.parametrize("years,level", [
    (0, "Fresher"), (0.5, "Entry Level"), (1.5, "Entry Level"), (2, "Mid Level"),
    (2.5, "Mid Level"), (5, "Mid Level"), (5.5, "Senior"), (12, "Senior"),
])
def test_career_level(years, level):
    assert career_level_for(years) == level


# ---------- is_internship_period ----------

SIVA_RESUME = """Experience
Programmer/Analyst – II
NetApp: Data Storage and Data Management Solutions, Bangalore June 2024 – Present
• Registered a service wrapper API enabling secure access for 2+ internal consumers
• Worked on AI-powered HR Assistant POC reducing
estimated query resolution time

Information Technology Internship
RPA Developer, NetApp: Data Storage and Data Management Solutions, Bangalore Aug 2023 – June 2024
• Contributed to the migration of 10+ automation bots
"""


def test_internship_heading_marks_entry_as_internship():
    assert is_internship_period(period("2023-08", "2024-06", "RPA Developer"), SIVA_RESUME)


def test_full_time_entry_next_to_internship_is_not_flagged():
    assert not is_internship_period(period("2024-06", "", "Programmer/Analyst – II"), SIVA_RESUME)


def test_word_internal_is_not_an_internship():
    text = "Engineer\nAcme Corp Jan 2020 - Dec 2021\n• Built internal tools used across international teams\n"
    assert not is_internship_period(period("2020-01", "2021-12", "Engineer"), text)


@pytest.mark.parametrize("role", ["Software Intern", "Summer Internship", "Management Trainee", "Apprentice Electrician", "INTERN"])
def test_role_title_alone_is_enough(role):
    assert is_internship_period(period("2020-01", "2020-06", role), "no matching text here")


def test_internship_listed_first_does_not_leak_into_next_job():
    text = (
        "Internship\n"
        "Backend Developer, Acme  Jan 2022 - Jun 2022\n"
        "• built stuff\n"
        "• more stuff\n"
        "Software Engineer\n"
        "Beta Corp  07/2022 - Present\n"
    )
    assert is_internship_period(period("2022-01", "2022-06", "Backend Developer"), text)
    assert not is_internship_period(period("2022-07", "", "Software Engineer"), text)


@pytest.mark.parametrize("date_text,start", [
    ("Aug 2023 - Jun 2024", "2023-08"),
    ("August 2023 – June 2024", "2023-08"),
    ("Aug, 2023 to Jun 2024", "2023-08"),
    ("08/2023 - 06/2024", "2023-08"),
    ("8/2023 - 6/2024", "2023-08"),
    ("2023-08 - 2024-06", "2023-08"),
    ("2023/08 – 2024/06", "2023-08"),
])
def test_internship_detected_across_date_formats(date_text, start):
    text = f"Data Science Internship\nAnalyst, Acme {date_text}\n• did things\n"
    assert is_internship_period(period(start, "", "Analyst"), text)


def test_full_time_not_flagged_when_no_internship_words_anywhere():
    text = "Software Engineer\nAcme Jan 2020 - Present\n• shipped features\n"
    assert not is_internship_period(period("2020-01", "", "Software Engineer"), text)


def test_unparsable_start_does_not_crash():
    assert not is_internship_period(period("garbage"), "whatever")
    assert not is_internship_period(period(""), "whatever")


def test_empty_resume_text():
    assert not is_internship_period(period("2020-01", "", "Engineer"), "")
    assert not is_internship_period(period("2020-01", "", "Engineer"), None)


def test_header_split_over_several_lines():
    text = "Internship Program\nBackend Developer\nAcme Corp\nJan 2022 - Jun 2022\n• work\n"
    assert is_internship_period(period("2022-01", "2022-06", "Backend Developer"), text)


def test_trainee_entry_directly_above_job_does_not_taint_the_job():
    # No bullets between the entries, so only the date-line boundary protects the job.
    text = (
        "Experience\n"
        "Graduate Trainee, HCL   Jul 2022 - Jun 2023\n"
        "Software Engineer, HCL   Jul 2023 - Present\n"
    )
    assert is_internship_period(period("2022-07", "2023-06", "Graduate Trainee"), text)
    assert not is_internship_period(period("2023-07", "", "Software Engineer"), text)


def test_internship_in_education_section_does_not_taint_first_job():
    text = (
        "Education\nB.Tech 2018 - 2022   (Industrial Internship during final year)\n"
        "Experience\nSoftware Engineer\nAcme  Jan 2023 - Present\n"
    )
    assert not is_internship_period(period("2023-01", "", "Software Engineer"), text)
