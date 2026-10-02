"""jobs.apple.com JSON API used by the official site (CSRF token is part of its normal page flow)."""
from collectors.base import Collector
from models import Job

BASE = "https://jobs.apple.com"


class AppleCollector(Collector):
    def fetch(self) -> list[Job]:
        tok = self.http.get(f"{BASE}/api/v1/CSRFToken")
        headers = {"x-apple-csrf-token": tok.headers.get("x-apple-csrf-token", ""),
                   "Origin": BASE, "Referer": f"{BASE}/en-us/search"}
        jobs = []
        for q in self.queries:
            for page in range(1, self.max_pages + 1):
                body = {"query": q, "filters": {"locations": ["postLocation-USA"]},
                        "page": page, "locale": "en-us", "sort": "newest"}
                res = self.http.post(f"{BASE}/api/v1/search", json=body, headers=headers).json()
                batch = (res.get("res") or res).get("searchResults") or []
                for j in batch:
                    locs = [l.get("name", "") for l in j.get("locations") or []]
                    jobs.append(Job(
                        company=self.company,
                        title=(j.get("postingTitle") or "").strip(),
                        location="; ".join(filter(None, locs)) or "United States",
                        url=f"{BASE}/en-us/details/{j['positionId']}/{j.get('transformedPostingTitle', '')}",
                        posted_at=j.get("postingDate"),
                        description=j.get("jobSummary") or "",
                        external_id=str(j["positionId"]),
                    ))
                if len(batch) < 20:
                    break
        return self.dedupe(jobs)
