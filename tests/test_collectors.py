"""Parsing tests against recorded-shape fixtures (no network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors import build

FIX = Path(__file__).parent / "fixtures"


class Resp:
    def __init__(self, data, headers=None):
        self._d, self.headers = data, headers or {}

    def json(self):
        return self._d


class FakeHTTP:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _match(self, url):
        self.calls.append(url)
        for k, v in self.routes.items():
            if k in url:
                return Resp(v() if callable(v) else v)
        raise AssertionError(f"unexpected url {url}")

    def get(self, url, **kw):
        return self._match(url)

    def post(self, url, **kw):
        return self._match(url)


def load(name):
    return json.loads((FIX / name).read_text())


def test_workday():
    cfg = {"key": "nvidia", "name": "NVIDIA", "collector": "workday", "host": "nvidia.wd5.myworkdayjobs.com",
           "tenant": "nvidia", "site": "NVIDIAExternalCareerSite", "queries": ["software engineer"]}
    http = FakeHTTP({"/NVIDIAExternalCareerSite/job/": load("workday_detail.json"), "/jobs": load("workday_list.json")})
    c = build(cfg, http)
    jobs = c.fetch()
    assert len(jobs) == 2
    assert jobs[0].url == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/Software-Engineer--New-College-Grad-2027_JR1"
    j = c.enrich(jobs[0])
    assert "0-2 years" in j.description and "<p>" not in j.description


def test_greenhouse():
    cfg = {"key": "doordash", "name": "DoorDash", "collector": "greenhouse", "board": "doordashusa"}
    jobs = build(cfg, FakeHTTP({"greenhouse": load("greenhouse.json")})).fetch()
    assert jobs[0].title == "Software Engineer, New Grad" and "Bachelor" in jobs[0].description
    assert jobs[0].location == "San Francisco, CA"


def test_amazon():
    cfg = {"key": "amazon", "name": "Amazon", "collector": "amazon", "queries": ["sde"], "max_pages": 2}
    jobs = build(cfg, FakeHTTP({"amazon.jobs": load("amazon.json")})).fetch()
    assert jobs[0].url == "https://www.amazon.jobs/en/jobs/2900001/software-dev-engineer-i"
    assert "Bachelor" in jobs[0].description
