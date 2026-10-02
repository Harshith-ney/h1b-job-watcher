"""Ashby public posting API. Config: board."""
from collectors.base import Collector
from models import Job


class AshbyCollector(Collector):
    def fetch(self) -> list[Job]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{self.cfg['board']}"
        data = self.http.get(url).json()
        out = []
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
            out.append(Job(
                company=self.company,
                title=j["title"].strip(),
                location="; ".join(l for l in locs if l),
                url=j.get("jobUrl") or j.get("applyUrl"),
                posted_at=j.get("publishedAt"),
                description=j.get("descriptionPlain") or "",
                external_id=j.get("id"),
            ))
        return out
