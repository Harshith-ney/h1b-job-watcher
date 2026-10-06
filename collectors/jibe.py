"""Jibe (iCIMS) career sites, e.g. careers.amd.com.
GET {host}/api/jobs?keywords=..&sortBy=posted_date&descending=true&page=N + site filters (country, categories).
Search results already include qualifications/responsibilities/description, so no detail fetch.

Config: host, queries, max_pages, filters ({param: value}), job_url (optional template, default
https://{host}/careers-home/jobs/{req_id})."""
from __future__ import annotations

from collectors.base import Collector
from models import Job, html_to_text


class JibeCollector(Collector):
    def _url(self, req_id: str) -> str:
        tpl = self.cfg.get("job_url") or "https://{host}/careers-home/jobs/{req_id}"
        return tpl.format(host=self.cfg["host"], req_id=req_id)

    def fetch(self) -> list[Job]:
        jobs = []
        for q in self.queries:
            for page in range(1, self.max_pages + 1):
                params = {"keywords": q, "sortBy": "posted_date", "descending": "true", "page": page,
                          **(self.cfg.get("filters") or {})}
                data = self.http.get(f"https://{self.cfg['host']}/api/jobs", params=params).json()
                batch = data.get("jobs") or []
                for item in batch:
                    j = item.get("data", item)
                    rid, title = j.get("req_id") or j.get("slug"), j.get("title")
                    if not rid or not title:
                        continue
                    loc = j.get("full_location") or ", ".join(p for p in (j.get("city"), j.get("state")) if p)
                    country = j.get("country") or ""
                    if country and country.lower() not in loc.lower():
                        loc = f"{loc}, {country}" if loc else country
                    desc = "\n".join(html_to_text(j.get(k)) for k in ("qualifications", "responsibilities", "description")
                                     if j.get(k))
                    jobs.append(Job(
                        company=self.company,
                        title=title.strip(),
                        location=loc,
                        url=self._url(str(rid)),
                        posted_at=(j.get("posted_date") or "")[:10] or None,
                        description=desc,
                        external_id=str(rid),
                    ))
                if not batch or len(batch) < 10:
                    break
        return self.dedupe(jobs)
