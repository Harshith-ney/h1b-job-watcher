"""V1 regex sponsorship hint. red = explicit restriction found, green = explicitly offered, yellow = unknown."""
from filters._util import matches


def sponsorship_status(description: str, cfg: dict) -> str:
    if matches(cfg.get("red_flags"), description):
        return "red"
    if matches(cfg.get("green_flags"), description):
        return "green"
    return "yellow"
