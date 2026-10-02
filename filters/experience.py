"""Early-career signals + minimum years-of-experience extraction."""
from __future__ import annotations

import re

from filters._util import matches

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15}
_NUM = r"(\d{1,2}|" + "|".join(_WORDS) + r")"
_YEARS_RX = re.compile(
    rf"(?:\b{_NUM}\s*\+?\s*(?:-|–|to)\s*{_NUM}\s*\+?\s*years?"          # 2-4 years
    rf"|(?:minimum of|at least|min\.?)\s*{_NUM}\s*\+?\s*years?"          # at least 3 years
    rf"|\b{_NUM}\s*(?:\+|plus|or more)\s*years?"                         # 5+ years
    rf"|\b{_NUM}\s*years?\s+(?:of\s+)?(?:\w+\s+){{0,4}}experience)",     # 3 years of ... experience
    re.IGNORECASE,
)


def _n(tok: str | None) -> int | None:
    if not tok:
        return None
    tok = tok.lower()
    return int(tok) if tok.isdigit() else _WORDS.get(tok)


def min_years_required(text: str) -> int | None:
    """Smallest years-of-experience figure mentioned near 'experience'. Lenient on purpose:
    if basic quals say 2+ and preferred say 5+, we keep the job."""
    found = []
    for m in _YEARS_RX.finditer(text or ""):
        window = text[max(0, m.start() - 150): m.end() + 150].lower()
        if "experience" not in window:
            continue
        nums = [n for n in (_n(g) for g in m.groups() if g) if n is not None and n <= 20]
        if nums:
            found.append(nums[0])  # first number = lower bound of a range
    return found[0] if found else None


def experience_verdict(title: str, description: str, cfg: dict) -> tuple[bool, bool, str]:
    """Returns (keep, early_career, reason).
    1. Early-career signal in the TITLE  -> keep (beats any years text).
    2. Years stated in description       -> keep if <= max_min_years.
    3. No years stated                   -> keep if description has an early-career signal,
                                            else cfg['unknown_years'] (keep | drop)."""
    signals = cfg.get("early_career_signals")
    if matches(signals, title):
        return True, True, "early-career title"
    desc_early = matches(signals, description)
    if cfg.get("require_early_career") and not desc_early:
        return False, False, "no early-career signal"
    yrs = min_years_required(description)
    if yrs is not None:
        limit = cfg.get("max_min_years", 2)
        if yrs > limit:
            return False, desc_early, f"requires {yrs}+ years"
        return True, desc_early, f"{yrs} years ok"
    if desc_early:
        return True, True, "early-career description"
    return cfg.get("unknown_years", "keep") == "keep", False, "years not stated"
