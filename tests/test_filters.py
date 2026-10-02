import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_loader import load_filters
from filters.experience import experience_verdict, min_years_required
from filters.roles import is_us_location, title_verdict
from filters.sponsorship import sponsorship_status

F = load_filters()


def test_titles_kept():
    for t in [
        "Software Engineer, New College Grad",
        "Software Development Engineer I",
        "SDE I, AWS",
        "2027 Software Dev Engineer",
        "Backend Engineer",
        "Full Stack Engineer",
        "Machine Learning Engineer",
        "AI Engineer - GenAI",
        "Systems Software Engineer",
        "Software Engineer II",
        "Research Engineer, LLM",
        "AMTS, Software Engineer",
    ]:
        assert title_verdict(t, F["roles"])[0], t


def test_titles_rejected():
    for t in [
        "Senior Software Engineer",
        "Sr. Software Engineer",
        "Staff Machine Learning Engineer",
        "Principal Software Engineer",
        "Software Engineering Manager",
        "Lead Backend Engineer",
        "Software Engineer III",
        "Software Engineer Intern",
        "Solutions Architect",
        "Product Manager",
        "Sales Engineer",
        "Data Analyst",
    ]:
        assert not title_verdict(t, F["roles"])[0], t


def test_location():
    L = F["location"]
    assert is_us_location("Santa Clara, CA", L)
    assert is_us_location("US, WA, Seattle", L)
    assert is_us_location("Remote", L)
    assert is_us_location("2 Locations", L)
    assert is_us_location("Santa Clara, CA; Bangalore, India", L)
    assert not is_us_location("Bengaluru, India", L)
    assert not is_us_location("Toronto, Canada", L)
    assert not is_us_location("Tel Aviv, Israel", L)


def test_years():
    assert min_years_required("Requires 5+ years of experience in C++") == 5
    assert min_years_required("0-2 years of professional experience") == 0
    assert min_years_required("Basic: 2+ years experience. Preferred: 7+ years experience") == 2
    assert min_years_required("At least three years of industry experience") == 3
    assert min_years_required("We have offices in 10 countries") is None


def test_experience_verdict():
    E = F["experience"]
    assert experience_verdict("Software Engineer", "8+ years of experience building systems", E)[0] is False
    keep, early, _ = experience_verdict("Software Engineer", "BS/MS in CS. 0-2 years of experience.", E)
    assert keep and early
    keep, early, _ = experience_verdict("Software Engineer, New College Grad", "7+ years experience preferred", E)
    assert keep and early
    assert experience_verdict("Software Engineer", "1+ years of experience with Java", E)[0] is True
    assert experience_verdict("Software Engineer", "Build cool things.", {**E, "unknown_years": "drop"})[0] is False
    assert experience_verdict("Software Engineer", "Build cool things.", {**E, "unknown_years": "keep"})[0] is True


def test_sponsorship():
    S = F["sponsorship"]
    assert sponsorship_status("This role does not provide immigration sponsorship.", S) == "red"
    assert sponsorship_status("Must be a U.S. citizen.", S) == "red"
    assert sponsorship_status("Great benefits.", S) == "yellow"
