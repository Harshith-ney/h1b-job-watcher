"""Eightfold-powered career sites (Microsoft = apply.careers.microsoft.com).
Config: host, domain, search_path (/api/pcsx/search for Microsoft), optional detail_path.
Detail fetch is best-effort: if it fails the job is still alerted with an empty description."""
from __future__ import annotations

from datetime import datetime, timezone

from collectors.base import Collector, log
from models import Job, html_to_text


def _positions(data: dict) -> list[dict]:
    return data.get("positions") or (data.get("data") or {}).get("positions") or []


class EightfoldCollector(Collector):
    def _abs(self, url: str) -> str:
        return url if url.startswith("http") else f"https://{self.cfg['host']}{url}"

    def fetch(self) -> list[Job]:
        path = self.cfg.get("search_path", "/api/pcsx/search")
        jobs = []
        for q in self.queries:
            start = 0
            for _ in range(self.max_pages):
                params = {
                    "domain": self.cfg["domain"],
                    "query": q,
                    "location": self.cfg.get("location", "United States"),
                    "start": start,
                    "sort_by": "timestamp",
                }
                batch = _positions(self.http.get(f"https://{self.cfg['host']}{path}", params=params).json())
                if not batch:
                    break
                for p in batch:
                    locs = p.get("standardizedLocations") or p.get("locations") or [p.get("location") or ""]
                    ts = p.get("postedTs") or p.get("t_create") or p.get("creationTs")
                    url = p.get("canonicalPositionUrl") or p.get("positionUrl") or f"/careers/job/{p['id']}"
                    jobs.append(Job(
                        company=self.company,
                        title=(p.get("name") or "").strip(),
                        location="; ".join(l for l in locs if isinstance(l, str)),
                        url=self._abs(url),
                        posted_at=datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else None,
                        description=html_to_text(p.get("job_description") or p.get("jobDescription")),
                        external_id=str(p["id"]),
                    ))
                start += len(batch)
        return self.dedupe(jobs)

    def enrich(self, job: Job) -> Job:
        if job.description:
            return job
        path = self.cfg.get("detail_path", "/api/pcsx/position_details")
        try:
            data = self.http.get(f"https://{self.cfg['host']}{path}",
                                 params={"position_id": job.external_id, "domain": self.cfg["domain"]}).json()
            d = data.get("data") or data
            job.description = html_to_text(d.get("jobDescription") or d.get("job_description") or "")
        except Exception as e:
            log.debug("%s: detail fetch failed for %s: %s", self.company, job.external_id, e)
        return job
