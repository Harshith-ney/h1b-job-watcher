import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors import build
from models import job_id_from_url


class Resp:
    def __init__(self, d): self.d = d
    def json(self): return self.d


class FakeHTTP:
    def __init__(self): self.bodies = []
    def post(self, url, json=None, headers=None, **kw):
        self.bodies.append(json)
        return Resp({"data": {"roleSearch": {"totalCount": 2, "items": [
            {"roleId": "178378", "jobTitle": "Software Engineer, Platform", "corporateTitle": "Analyst",
             "division": "Engineering", "skills": ["Java"],
             "locations": [{"primary": False, "city": "Dallas", "state": "TX", "country": "United States"},
                           {"primary": True, "city": "New York", "state": "NY", "country": "United States"}]},
            {"roleId": "152248", "jobTitle": "Full Stack Engineer", "corporateTitle": "Associate",
             "locations": [{"primary": True, "city": "Bengaluru", "state": "KA", "country": "India"}]}]}}})


def test_goldman():
    http = FakeHTTP()
    jobs = build({"key": "goldman", "name": "Goldman Sachs", "collector": "goldman", "max_pages": 3}, http).fetch()
    assert len(jobs) == 2 and len(http.bodies) == 1
    v = http.bodies[0]["variables"]["searchQueryInput"]
    assert v["filters"][0]["filters"][1]["filter"] == "Associate"
    assert v["filters"][1]["filters"][0]["filter"] == "Software Engineering"
    j = jobs[0]
    assert j.url == "https://higher.gs.com/roles/178378" and job_id_from_url(j.url) == "178378"
    assert j.location.startswith("New York, NY, United States")  # primary first
    assert "Analyst" in j.description
