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


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_WORKDAY_ID = re.compile(r"_([A-Za-z]{0,3}\d[\w-]*)$")


def job_id_from_url(url: str) -> str | None:
    """Stable job ID from an official job URL (Workday req id, numeric id, or UUID).
    Lets dedupe survive title/location edits."""
    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query))
    for k in ("gh_jid", "jobId", "job_id"):
        if q.get(k):
            return q[k]
    for seg in reversed([x for x in parts.path.split("/") if x]):
        m = _WORKDAY_ID.search(seg)
        if m:
            return m.group(1)
        m = re.match(r"^(\d{4,})", seg)
        if m:
            return m.group(1)
        if _UUID.match(seg):
            return seg.lower()
    return None


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

    @property
    def job_key(self) -> str | None:
        jid = job_id_from_url(self.url)
        return f"{self.company.strip().lower()}|{jid}" if jid else None
