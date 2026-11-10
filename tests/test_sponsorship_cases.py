"""Regression tests for real-world sponsorship wording we've seen in postings."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_loader import load_filters
from filters.sponsorship import sponsorship_status

S = load_filters()["sponsorship"]
RED = [
    "the Company may not be able to employ candidates for this role who have United States work authorization "
    "related to certain U.S. visa categories, or support future H-1B sponsorship at this time.",          # Roblox
    "Fidelity will not provide immigration sponsorship for this position.",                               # Fidelity
    "This candidate must be a U.S. citizen (U.S. born or naturalized).",                                  # Salesforce
    "This position requires a USA TS/SCI with Polygraph security access level.",                          # clearance
    "Applicants must be authorized to work in the U.S. without sponsorship now or in the future.",
]
NOT_RED = [
    "We are an equal opportunity employer. Join our team in Boston.",
    "We consider all applicants regardless of national origin or citizenship status.",
    "Candidates may not be able to relocate. We support H-1B sponsorship for this role.",
]


def test_red_cases():
    for t in RED:
        assert sponsorship_status(t, S) == "red", t


def test_not_red_cases():
    for t in NOT_RED:
        assert sponsorship_status(t, S) != "red", t
