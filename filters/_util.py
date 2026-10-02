from __future__ import annotations
import re
from functools import lru_cache


@lru_cache(maxsize=None)
def compile_any(patterns: tuple[str, ...]) -> re.Pattern | None:
    if not patterns:
        return None
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def matches(patterns, text: str) -> bool:
    rx = compile_any(tuple(patterns or ()))
    return bool(rx and rx.search(text or ""))
