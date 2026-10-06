"""SWE/AI title filter + US location filter."""
import re

from filters._util import matches


def title_verdict(title: str, cfg: dict) -> tuple[bool, str]:
    """Returns (keep, reason)."""
    if not matches(cfg.get("include_title"), title):
        return False, "not swe/ai title"
    if matches(cfg.get("force_include_title"), title):
        return True, "forced"
    if matches(cfg.get("exclude_title"), title):
        return False, "senior/excluded title"
    return True, "ok"


_EXPLICIT_US = re.compile(r"united states|\busa?\b", re.I)


def is_us_location(location: str, cfg: dict) -> bool:
    """Keep if ANY location segment is US (or unknown). Per segment: explicit US/USA wins,
    then a non-US marker (so 'San Jose, Costa Rica' is non-US), then lenient keep."""
    if not cfg.get("us_only", True) or not location:
        return True
    segments = [seg.strip() for seg in re.split(r"[;|]", location) if seg.strip()] or [location]
    for seg in segments:
        if _EXPLICIT_US.search(seg):
            return True
        if matches(cfg.get("non_us_markers"), seg):
            continue
        return True  # US city/state marker or unknown -> keep
    return False
