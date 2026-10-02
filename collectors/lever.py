"""Lever public postings API. Config: board."""
from datetime import datetime, timezone

from collectors.base import Collector
from models import Job


class LeverCollector(Collector):
    def fetch(self) -> list[Job]:
        data = self.http.get(f"https://api.lever.co/v0/postings/{self.cfg['board']}", params={"mode": "json"}).json()
        out = []
        for j in data:
            created = j.get("createdAt")
            out.append(Job(
                company=self.company,
                title=j["text"].strip(),
                location=((j.get("categories") or {}).get("location") or "").strip(),
                url=j["hostedUrl"],
                posted_at=datetime.fromtimestamp(created / 1000, timezone.utc).date().isoformat() if created else None,
                description=j.get("descriptionPlain") or "",
                external_id=j.get("id"),
            ))
        return out
