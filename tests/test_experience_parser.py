import pytest
from app.services.experience_parser import extract_experience_requirement


@pytest.mark.parametrize(
    "text,expected_min,expected_max,expected_raw_contains",
    [
        ("We need someone with 3-5 years of experience", 3.0, 5.0, "3-5"),
        ("Looking for 0-2 years experience", 0.0, 2.0, "0-2"),
        ("2 to 4 years of relevant work", 2.0, 4.0, "2 to 4"),
        ("3+ years of experience required", 3.0, None, "3+"),
        ("1+ year experience", 1.0, None, "1+"),
        ("Minimum 2 years of experience", 2.0, None, "Minimum 2"),
        ("Min. 5 years required", 5.0, None, "Min. 5"),
        ("At least 4 years experience needed", 4.0, None, "At least 4"),
        ("Fresher candidates welcome", 0.0, 0.0, "Fresher"),
        ("Entry-level position, no experience required", 0.0, 0.0, None),
        ("Graduate program 2024", 0.0, 0.0, "Graduate"),
        ("2 years experience in Python", 2.0, 2.0, "2 years"),
        ("0 years experience necessary", 0.0, 0.0, "0 years"),
    ],
)
def test_extract_experience_requirement_matches(text, expected_min, expected_max, expected_raw_contains):
    result = extract_experience_requirement(text)
    assert result["min_years"] == expected_min
    assert result["max_years"] == expected_max
    if expected_raw_contains:
        assert expected_raw_contains.lower() in result["raw_text"].lower()


def test_extract_experience_requirement_empty_text():
    result = extract_experience_requirement("")
    assert result == {"raw_text": "Unknown", "min_years": None, "max_years": None}


def test_extract_experience_requirement_none_text():
    result = extract_experience_requirement(None)
    assert result == {"raw_text": "Unknown", "min_years": None, "max_years": None}


def test_extract_experience_requirement_no_match():
    result = extract_experience_requirement("We are a fun team building cool products.")
    assert result == {"raw_text": "Unknown", "min_years": None, "max_years": None}


def test_range_pattern_takes_priority_over_plain_years():
    # "3-5 years" should NOT be caught by the plainer "5 years" pattern
    result = extract_experience_requirement("Requires 3-5 years of experience")
    assert result["min_years"] == 3.0
    assert result["max_years"] == 5.0


def test_plus_pattern_takes_priority_over_plain_years():
    result = extract_experience_requirement("5+ years needed")
    assert result["min_years"] == 5.0
    assert result["max_years"] is None


def test_en_dash_range_pattern():
    result = extract_experience_requirement("2–4 years of experience")
    assert result["min_years"] == 2.0
    assert result["max_years"] == 4.0


def test_case_insensitivity():
    result = extract_experience_requirement("MINIMUM 3 YEARS OF EXPERIENCE")
    assert result["min_years"] == 3.0
