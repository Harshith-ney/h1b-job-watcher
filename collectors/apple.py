"""jobs.apple.com JSON search API (anonymous; no CSRF/cookie/referer needed).
The request MUST include "format": {} - without it Apple returns 200 with totalRecords=0.
Sorted newest-first, so a few pages per run is enough. Details page is fetched only for
new candidates so the years-of-experience filter can read the minimum qualifications."""
from __future__ import annotations

import re

from collectors.base import Collector, log
from models import Job, html_to_text

BASE = "https://jobs.apple.com"
PAGE = 20


def _loc(l: dict) -> str:
    country = "USA" if l.get("countryID") == "iso-country-USA" else (l.get("countryName") or "")
    return ", ".join(p for p in (l.get("name"), l.get("stateProvince"), country) if p)


class AppleCollector(Collector):
    def _filters(self) -> dict:
        f = {"locations": [self.cfg.get("location_filter", "postLocation-USA")]}
        group = self.cfg.get("team_group", "SFTWR")
        if self.cfg.get("teams"):  # Apple sub-team codes, e.g. AF, CLD, MCHLN
            f["teams"] = [{"team": f"teamsAndSubTeams-{group}", "subTeam": f"subTeam-{t}"} for t in self.cfg["teams"]]
        return f

    def fetch(self) -> list[Job]:
        jobs = []
        for q in self.queries:
            for page in range(1, self.max_pages + 1):
                body = {
                    "query": q,
                    "filters": self._filters(),
                    "page": page,
                    "locale": "en-us",
                    "sort": "newest",
                    "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"},
                }
                data = self.http.post(f"{BASE}/api/v1/search", json=body).json()
                res = data.get("res") or data
                batch = res.get("searchResults") or []
                for j in batch:
                    pid = j.get("positionId") or j.get("id")
                    if not pid or not j.get("postingTitle"):
                        continue
                    jobs.append(Job(
                        company=self.company,
                        title=j["postingTitle"].strip(),
                        location="; ".join(dict.fromkeys(_loc(l) for l in j.get("locations") or [])),
                        url=f"{BASE}/en-us/details/{pid}/{j.get('transformedPostingTitle', '')}",
                        posted_at=(j.get("postingDate") or j.get("postDateInGMT") or "")[:10] or None,
                        description=j.get("jobSummary") or "",
                        external_id=str(pid),
                    ))
                if len(batch) < PAGE:
                    break
        # Apple returns a multi-city job once per city: merge by positionId
        merged: dict[str, Job] = {}
        for j in jobs:
            if j.external_id in merged:
                m = merged[j.external_id]
                m.location = "; ".join(dict.fromkeys((m.location + "; " + j.location).split("; ")))
            else:
                merged[j.external_id] = j
        return list(merged.values())

    def enrich(self, job: Job) -> Job:
        """Pull minimum/preferred qualifications from the JSON embedded in the details page.
        Minimum qualifications go first: the years filter reads the first years mention."""
        try:
            html = self.http.get(job.url, headers={"Accept": "text/html"}).text
            fields = extract_fields(html)
            parts = [fields.get(k) for k in ("minimumQualifications", "description", "responsibilities",
                                              "preferredQualifications")]
            extra = "\n".join(p for p in parts if p)
            if extra:
                job.description = f"{extra}\n{job.description}"
        except Exception as e:
            log.debug("apple detail failed for %s: %s", job.external_id, e)
        return job


_FIELD_RX = re.compile(
    r'\\"(minimumQualifications|preferredQualifications|description|responsibilities)\\":\\"(.*?)(?<!\\)\\"', re.S)


def _unescape(v: str) -> str:
    v = v.replace('\\\\\\"', '"')    # \\\"  -> "
    v = v.replace('\\\\n', '\n')     # \\n   -> newline
    v = v.replace('\\n', '\n')       # \n    -> newline
    v = v.replace('\\"', '"')        # \"    -> "
    v = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), v)
    return html_to_text(v.replace('\\\\', '\\'))


def extract_fields(html: str) -> dict:
    """First occurrence of each job field in the page's escaped hydration JSON."""
    out = {}
    for key, raw in _FIELD_RX.findall(html):
        if key not in out and raw.strip():
            out[key] = _unescape(raw)
    return out
