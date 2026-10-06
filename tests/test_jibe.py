import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors import build
from models import job_id_from_url


class Resp:
    def __init__(self, d): self.d = d
    def json(self): return self.d


class FakeHTTP:
    def __init__(self): self.calls = []
    def get(self, url, params=None, **kw):
        self.calls.append(params)
        n = 10 if params["page"] == 1 else 3
        return Resp({"totalCount": 13, "jobs": [{"data": {
            "req_id": str(92000 + params["page"] * 100 + i), "title": "Software Development Engineer - Networking",
            "full_location": "Santa Clara, California", "city": "Santa Clara", "state": "California",
            "country": "United States", "posted_date": "2026-10-05T20:57:00+0000",
            "qualifications": "<p>BS in CS and 2+ years of experience</p>",
            "responsibilities": "<p>Build drivers</p>", "description": "<p>About AMD</p>"}} for i in range(n)]})


def test_jibe_amd():
    http = FakeHTTP()
    cfg = {"key": "amd", "name": "AMD", "collector": "jibe", "host": "careers.amd.com", "queries": ["software"],
           "max_pages": 5, "filters": {"country": "United States", "categories": "Engineering"}}
    jobs = build(cfg, http).fetch()
    assert len(jobs) == 13 and [c["page"] for c in http.calls] == [1, 2]
    p = http.calls[0]
    assert p["sortBy"] == "posted_date" and p["descending"] == "true" and p["categories"] == "Engineering"
    j = jobs[0]
    assert j.url == "https://careers.amd.com/careers-home/jobs/92100" and job_id_from_url(j.url) == "92100"
    assert j.location == "Santa Clara, California, United States" and j.posted_at == "2026-10-05"
    assert j.description.startswith("BS in CS and 2+ years")
