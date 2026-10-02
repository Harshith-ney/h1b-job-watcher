"""SWE/AI title filter + US location filter."""
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


def is_us_location(location: str, cfg: dict) -> bool:
    """Lenient: only reject when clearly non-US and no US marker is present."""
    if not cfg.get("us_only", True) or not location:
        return True
    if matches(cfg.get("us_markers"), location):
        return True
    return not matches(cfg.get("non_us_markers"), location)
