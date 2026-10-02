"""Workday CXS JSON API (the same endpoint the official *.myworkdayjobs.com site calls).
Config: host, tenant, site, optional applied_facets."""
from __future__ import annotations

from collectors.base import Collector, log
from models import Job, html_to_text

PAGE = 20  # Workday caps limit at 20


class WorkdayCollector(Collector):
    @property
    def base(self) -> str:
        c = self.cfg
        return f"https://{c['host']}/wday/cxs/{c['tenant']}/{c['site']}"

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for q in self.queries:
            total = None
            for page in range(self.max_pages):
                body = {
                    "appliedFacets": self.cfg.get("applied_facets", {}),
                    "limit": PAGE,
                    "offset": page * PAGE,
                    "searchText": q,
                }
                data = self.http.post(f"{self.base}/jobs", json=body).json()
                if total is None:
                    total = data.get("total") or 0  # only reliable on first page
                postings = data.get("jobPostings") or []
                for p in postings:
                    path = p.get("externalPath")
                    if not path or not p.get("title"):
                        continue
                    jobs.append(Job(
                        company=self.company,
                        title=p["title"].strip(),
                        location=(p.get("locationsText") or "").strip(),
                        url=f"https://{self.cfg['host']}/{self.cfg['site']}{path}",
                        posted_at=p.get("postedOn"),
                        external_id=path,
                    ))
                if len(postings) < PAGE or (page + 1) * PAGE >= total:
                    break
        log.debug("%s: %d raw postings", self.company, len(jobs))
        return self.dedupe(jobs)

    def enrich(self, job: Job) -> Job:
        data = self.http.get(f"{self.base}{job.external_id}").json()
        info = data.get("jobPostingInfo") or {}
        job.description = html_to_text(info.get("jobDescription"))
        if info.get("externalUrl"):
            job.url = info["externalUrl"]
        extra = info.get("additionalLocations") or []
        if info.get("location") and job.location.lower().endswith("locations"):
            job.location = "; ".join([info["location"], *extra])
        job.posted_at = info.get("startDate") or job.posted_at
        return job
