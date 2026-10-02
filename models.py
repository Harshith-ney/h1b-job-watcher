"""Normalized job model + fingerprinting."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = re.compile(r"^(utm_|gh_src$|src$|source$|ref$|refId$|trk)", re.I)


def normalize_url(url: str) -> str:
    """Drop fragments + tracking params, keep meaningful query params (e.g. Greenhouse gh_jid)."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS.match(k)]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)  # Greenhouse double-escapes
    text = re.sub(r"(?i)<\s*(br|/p|/li|/div|/h\d)\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


@dataclass
class Job:
    company: str
    title: str
    location: str
    url: str
    posted_at: str | None = None
    description: str = ""
    external_id: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def fingerprint(self) -> str:
        key = "|".join(
            s.strip().lower()
            for s in (self.company, self.title, self.location, normalize_url(self.url))
        )
        return hashlib.sha256(key.encode()).hexdigest()
