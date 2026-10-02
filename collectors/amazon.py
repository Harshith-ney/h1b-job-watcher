"""amazon.jobs search.json (the endpoint amazon.jobs itself uses). Sorted by recent, includes descriptions."""
from collectors.base import Collector
from models import Job, html_to_text

PAGE = 100


class AmazonCollector(Collector):
    def fetch(self) -> list[Job]:
        jobs = []
        for q in self.queries:
            for page in range(self.max_pages):
                params = {
                    "base_query": q,
                    "loc_query": "United States",
                    "country": "USA",
                    "result_limit": PAGE,
                    "offset": page * PAGE,
                    "sort": "recent",
                }
                data = self.http.get("https://www.amazon.jobs/en/search.json", params=params).json()
                batch = data.get("jobs") or []
                for j in batch:
                    desc = "\n".join(filter(None, (
                        j.get("description"), j.get("basic_qualifications"), j.get("preferred_qualifications"))))
                    jobs.append(Job(
                        company=self.company,
                        title=(j.get("title") or "").strip(),
                        location=(j.get("normalized_location") or j.get("location") or "").strip(),
                        url="https://www.amazon.jobs" + j["job_path"],
                        posted_at=j.get("posted_date"),
                        description=html_to_text(desc),
                        external_id=str(j.get("id_icims") or j.get("id")),
                    ))
                if len(batch) < PAGE:
                    break
        return self.dedupe(jobs)
