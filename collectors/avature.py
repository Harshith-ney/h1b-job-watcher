"""Avature career portals (e.g. bloomberg.avature.net). Results are server-rendered HTML:
GET https://{host}/{portal}/SearchJobs/?{search_params}&jobOffset=N  (N = page * page_size)
Each result: <a class="link" href=".../JobDetail/<slug>/<id>">Title</a> ... <span class="list-item-location">Loc</span>
Detail pages are server-rendered too, so the years/sponsorship filters can read them.

Config: host, portal (default "careers"), search_params (query string copied from the site's
filtered search URL, without jobOffset), page_size (default 12), max_pages.
Note: some Avature hosts reject LibreSSL clients (macOS system Python/curl); OpenSSL (GitHub Actions) is fine.
"""
from __future__ import annotations

import html as _html
import re

from collectors.base import Collector
from models import Job, html_to_text

_LINK = re.compile(r'<a[^>]+href="(https?://[^"]+/JobDetail/[^"]+?/(\d+))"[^>]*>\s*(.*?)\s*</a>', re.S)
_LOC = re.compile(r'<span[^>]*class="[^"]*list-item-location[^"]*"[^>]*>\s*(.*?)\s*</span>', re.S)


def parse_results(page_html: str) -> list[tuple[str, str, str, str]]:
    """(job_id, title, location, url) for each result on a search page."""
    out, links = [], list(_LINK.finditer(page_html))
    for i, m in enumerate(links):
        end = links[i + 1].start() if i + 1 < len(links) else m.end() + 2000
        loc = _LOC.search(page_html, m.end(), end)
        title = _html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
        if title:
            out.append((m.group(2), title, _html.unescape(loc.group(1)).strip() if loc else "", m.group(1)))
    return out


def detail_text(page_html: str) -> str:
    body = re.sub(r"(?is)<(script|style|nav|header|footer)\b.*?</\1>", " ", page_html)
    text = html_to_text(body)
    i = text.find("Description & Requirements")
    return text[i + len("Description & Requirements"):].strip() if i >= 0 else text


class AvatureCollector(Collector):
    def _search_url(self, offset: int) -> str:
        c = self.cfg
        return (f"https://{c['host']}/{c.get('portal', 'careers')}/SearchJobs/?"
                f"{c['search_params'].strip('&')}&jobOffset={offset}")

    def fetch(self) -> list[Job]:
        size, jobs, seen = int(self.cfg.get("page_size", 12)), [], set()
        for page in range(self.max_pages):
            results = parse_results(self.http.get(self._search_url(page * size)).text)
            fresh = [r for r in results if r[0] not in seen]
            for jid, title, loc, url in fresh:
                seen.add(jid)
                jobs.append(Job(company=self.company, title=title, location=loc, url=url, external_id=jid))
            if len(results) < size or not fresh:
                break
        return jobs

    def enrich(self, job: Job) -> Job:
        job.description = detail_text(self.http.get(job.url).text)
        return job
