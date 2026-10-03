"""Google Careers.

Primary path: the server-rendered results page (same filters as the site's URL), whose job data
is embedded as JSON in AF_initDataCallback blocks. Fallback: the site's r06xKb batchexecute RPC.
Sorted by date, so after the first scan only the first few pages are read.

Job record (by index): 0 id, 1 title, 2 apply url, 3 responsibilities, 4 qualifications,
                       7 company, 9 locations, 10 description, 12/13 timestamps, 19 min quals

Debug:  python -m collectors.google "software engineer"   -> parses page 1 live
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from collectors.base import Collector, log
from models import Job, html_to_text

BASE = "https://www.google.com/about/careers/applications"
RPC_URL = f"{BASE}/_/HiringCportalFrontendUi/data/batchexecute"
SEARCH_RPC, DETAIL_RPC = "r06xKb", "sf9Qmf"


# ---------------------------------------------------------------- protocol helpers
def build_freq(rpcid: str, args: list) -> str:
    return json.dumps([[[rpcid, json.dumps(args, separators=(",", ":")), None, "generic"]]],
                      separators=(",", ":"))


def parse_batchexecute(text: str, rpcid: str) -> list:
    """Return decoded payloads for rpcid. Handles plain and chunked (rt=c) responses."""
    body = text.lstrip()
    if body.startswith(")]}'"):
        body = body[4:]
    candidates = []
    try:
        candidates.append(json.loads(body))
    except ValueError:
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("["):
                try:
                    candidates.append(json.loads(line))
                except ValueError:
                    pass
    out = []
    for arr in candidates:
        for e in arr if isinstance(arr, list) else []:
            if isinstance(e, list) and len(e) > 2 and e[0] == "wrb.fr" and e[1] == rpcid:
                if e[2] is None:
                    raise RuntimeError(f"{rpcid} returned an error envelope: {json.dumps(e)[:300]}")
                out.append(json.loads(e[2]))
    if not out:
        raise RuntimeError(f"no {rpcid} payload in response: {text[:300]!r}")
    return out


def _strings(x) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, list):
        return [s for item in x for s in _strings(item)]
    return []


def _find_records(node, depth=0):
    """Locate the list of job records inside the payload without hard-coding its path."""
    if depth > 6 or not isinstance(node, list):
        return None
    head = node[:3]
    if head and all(isinstance(r, list) and len(r) > 10 and isinstance(r[1], str) for r in head):
        return node
    for child in node:
        found = _find_records(child, depth + 1)
        if found is not None:
            return found
    return None


_AF_RX = re.compile(r"AF_initDataCallback\(\{key: '([^']+)'.*?data:(.*?), sideChannel: \{\}\}\);", re.S)


def records_from_html(html: str) -> list:
    """Job records embedded in the server-rendered results page."""
    for _key, raw in _AF_RX.findall(html):
        try:
            recs = _find_records(json.loads(raw))
        except ValueError:
            continue
        if recs:
            return recs
    return []


def _get(r: list, i: int):
    return r[i] if len(r) > i else None


def _ts(x) -> str | None:
    while isinstance(x, list) and x:
        x = x[0]
    if isinstance(x, (int, float)) and x > 1_000_000_000:
        sec = x / 1000 if x > 10_000_000_000 else x
        return datetime.fromtimestamp(sec, timezone.utc).date().isoformat()
    return None


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def record_to_job(r: list, company_default: str = "Google") -> Job | None:
    jid, title = _get(r, 0), _get(r, 1)
    if not jid or not isinstance(title, str):
        return None
    jid = str(jid).split("/")[-1]
    locs = []
    for loc in _get(r, 9) or []:
        s = _strings(loc)
        if s:
            locs.append(s[0])
    company = (_strings(_get(r, 7)) or [company_default])[0]
    parts = [_get(r, i) for i in (10, 3, 19, 4)]
    desc = "\n".join(html_to_text(s) for p in parts for s in _strings(p) if s)
    return Job(
        company=company,
        title=title.strip(),
        location="; ".join(dict.fromkeys(locs)),
        url=f"{BASE}/jobs/results/{jid}-{_slug(title)}",
        posted_at=_ts(_get(r, 12)) or _ts(_get(r, 13)),
        description=desc,
        external_id=jid,
        raw={"apply_url": _get(r, 2)},
    )


# ---------------------------------------------------------------- collector
class GoogleCollector(Collector):
    def _call(self, rpcid: str, args: list) -> list:
        resp = self.http.post(
            RPC_URL,
            params={"rpcids": rpcid, "source-path": "/about/careers/applications/jobs/results",
                    "hl": "en_US", "rt": "c"},
            data={"f.req": build_freq(rpcid, args)},
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        return parse_batchexecute(resp.text, rpcid)

    def search_args(self, query: str, page: int) -> list:
        args = [None] * 17
        args[0], args[7] = query, page
        for k, v in (self.cfg.get("arg_overrides") or {}).items():
            args[int(k)] = v
        return args

    def _page_records(self, query: str, page: int) -> list:
        params = {
            "location": self.cfg.get("location", "United States"),
            "target_level": self.cfg.get("target_levels", ["EARLY", "MID"]),
            "sort_by": "date",
            "q": query,
            "page": page,
        }
        html = self.http.get(f"{BASE}/jobs/results/", params=params,
                             headers={"Accept": "text/html,application/xhtml+xml"}).text
        recs = records_from_html(html)
        if not recs and page == 1 and self.cfg.get("rpc_fallback", True):
            log.info("google: no embedded data on results page, falling back to r06xKb")
            recs = _find_records(self._call(SEARCH_RPC, self.search_args(query, page))[0]) or []
        return recs

    def fetch(self) -> list[Job]:
        excluded = {c.lower() for c in self.cfg.get("exclude_companies", [])}
        pages = int(self.cfg.get("bootstrap_pages", 15)) if getattr(self, "first_scan", False) else self.max_pages
        jobs = []
        for q in self.queries:
            for page in range(1, pages + 1):
                records = self._page_records(q, page)
                for r in records:
                    j = record_to_job(r, self.company)
                    if j and j.company.lower() not in excluded:
                        j.company = self.company if j.company.lower() == "google" else f"{self.company} ({j.company})"
                        jobs.append(j)
                if len(records) < 20:
                    break
        log.debug("google: %d records over %d page(s)/query", len(jobs), pages)
        return self.dedupe(jobs)

    def enrich(self, job: Job) -> Job:
        if job.description:
            return job
        try:
            payloads = self._call(DETAIL_RPC, [job.external_id])
            rec = _find_records([payloads[0]]) or [payloads[0]]
            full = record_to_job(rec[0], self.company)
            if full:
                job.description = full.description
        except Exception as e:
            log.debug("google detail failed for %s: %s", job.external_id, e)
        return job


if __name__ == "__main__":  # live check: parse page 1 and show what we got
    import sys
    from http_client import PoliteSession

    q = sys.argv[1] if len(sys.argv) > 1 else "software engineer"
    c = GoogleCollector({"name": "Google", "queries": [q], "max_pages": 1}, PoliteSession())
    recs = c._page_records(q, 1)
    print(f"records on page 1: {len(recs)}")
    for r in recs[:5]:
        print("  ", record_to_job(r))
