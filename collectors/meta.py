"""Meta (metacareers.com) via the same GraphQL query its job-search page runs, anonymously.
Flow (the site's normal one): load /jobsearch/ -> read the per-visitor `lsd` anti-CSRF token from the
HTML -> POST /graphql with doc_id + variables (teams, full-time, newest first). One request returns
all matching jobs (id, title, locations, teams). Job pages: https://www.metacareers.com/jobs/<id>/

Config: teams, doc_id (Meta may rotate it on redeploys; a failure then triggers a health warning).
"""
from __future__ import annotations

import json
import re

from collectors.base import Collector
from models import Job, html_to_text

BASE = "https://www.metacareers.com"
DOC_ID = "27129360303422352"
QUERY_NAME = "CareersJobSearchResultsV2DataQuery"
_LSD = [re.compile(r'"LSD",\[\],\{"token":"([^"]+)"'), re.compile(r'name="lsd" value="([^"]+)"')]


def find_jobs(x):
    if isinstance(x, list) and x and isinstance(x[0], dict) and "title" in x[0] and "id" in x[0]:
        return x
    for v in (x.values() if isinstance(x, dict) else x if isinstance(x, list) else []):
        f = find_jobs(v)
        if f:
            return f
    return None


def parse_graphql(text: str) -> list[dict]:
    body = text[len("for (;;);"):] if text.startswith("for (;;);") else text
    first = body.strip().splitlines()[0] if body.strip() else "{}"
    data = json.loads(first)
    if isinstance(data, dict) and data.get("errors"):
        raise RuntimeError(f"meta graphql error: {str(data['errors'])[:200]}")
    return find_jobs(data) or []


class MetaCollector(Collector):
    def _lsd(self) -> str:
        page = self.http.get(f"{BASE}/jobsearch/").text
        for rx in _LSD:
            m = rx.search(page)
            if m:
                return m.group(1)
        raise RuntimeError("meta: no lsd token on jobsearch page (site changed or requires JS)")

    def fetch(self) -> list[Job]:
        lsd = self._lsd()
        variables = {"search_input": {
            "q": None, "divisions": [], "offices": [], "roles": ["Full time employment"],
            "leadership_levels": [], "saved_jobs": [], "saved_searches": [], "sub_teams": [],
            "teams": self.cfg.get("teams", ["Software Engineering", "Artificial Intelligence"]),
            "is_leadership": False, "is_remote_only": False, "sort_by_new": True, "results_per_page": None},
            "viewasUserID": None, "isLoggedIn": False}
        r = self.http.post(f"{BASE}/graphql",
                           headers={"x-fb-lsd": lsd, "x-fb-friendly-name": QUERY_NAME,
                                    "content-type": "application/x-www-form-urlencoded",
                                    "origin": BASE, "referer": f"{BASE}/jobsearch/"},
                           data={"av": "0", "__user": "0", "__a": "1", "lsd": lsd,
                                 "doc_id": str(self.cfg.get("doc_id", DOC_ID)),
                                 "fb_api_req_friendly_name": QUERY_NAME, "variables": json.dumps(variables)})
        jobs = []
        for j in parse_graphql(r.text):
            locs = j.get("locations") or []
            jobs.append(Job(company=self.company, title=(j.get("title") or "").strip(),
                            location="; ".join(l for l in locs if isinstance(l, str)),
                            url=f"{BASE}/jobs/{j['id']}/", external_id=str(j["id"])))
        return self.dedupe(jobs)

    def enrich(self, job: Job) -> Job:
        """The job page embeds structured job-posting data (JSON) with qualifications, responsibilities
        and description. Qualifications go first so the years filter reads the real requirement."""
        try:
            job.description = extract_details(self.http.get(job.url).text)
        except Exception:
            pass
        return job


_FIELD = r'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"'


def extract_details(page_html: str) -> str:
    parts = []
    for key in ("qualifications", "experienceRequirements", "responsibilities", "description"):
        m = re.search(_FIELD.format(key=key), page_html)
        if m:
            try:
                val = json.loads('"' + m.group(1) + '"')
            except ValueError:
                val = m.group(1)
            parts.append(html_to_text(val.replace("&nbsp;", "\n")))
    return "\n".join(p for p in parts if p)
