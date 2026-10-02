"""Greenhouse public Job Board API. Config: board."""
from collectors.base import Collector
from models import Job, html_to_text


class GreenhouseCollector(Collector):
    def fetch(self) -> list[Job]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{self.cfg['board']}/jobs"
        data = self.http.get(url, params={"content": "true"}).json()
        return [
            Job(
                company=self.company,
                title=j["title"].strip(),
                location=((j.get("location") or {}).get("name") or "").strip(),
                url=j["absolute_url"],
                posted_at=j.get("first_published") or j.get("updated_at"),
                description=html_to_text(j.get("content")),
                external_id=str(j["id"]),
            )
            for j in data.get("jobs", [])
        ]
