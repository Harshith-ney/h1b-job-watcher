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


def test_apple_sends_format_and_parses():
    sent = []

    class H(FakeHTTP):
        def post(self, url, json=None, **kw):
            sent.append(json)
            return Resp({"res": {"totalRecords": 1, "searchResults": [{
                "positionId": "200663858", "postingTitle": "Software Engineer, Maps",
                "transformedPostingTitle": "software-engineer-maps", "postingDate": "2026-10-03T00:30:53.671Z",
                "jobSummary": "Build maps.", "locations": [{"name": "Cupertino", "stateProvince": "California",
                                                            "countryID": "iso-country-USA", "countryName": "United States of America"}]},
                {"positionId": "200663858", "postingTitle": "Software Engineer, Maps",
                 "transformedPostingTitle": "software-engineer-maps", "postingDate": "2026-10-03T00:30:53.671Z",
                 "locations": [{"name": "Seattle", "stateProvince": "Washington", "countryID": "iso-country-USA"}]}]}})

        def get(self, url, **kw):
            r = Resp({}); r.text = open(Path(__file__).parent / "fixtures" / "apple_details.html").read(); return r

    cfg = {"key": "apple", "name": "Apple", "collector": "apple", "queries": [""], "max_pages": 3, "teams": ["AF", "MCHLN"]}
    c = build(cfg, H({}))
    jobs = c.fetch()
    assert sent[0]["format"] and sent[0]["sort"] == "newest" and len(sent) == 1
    assert sent[0]["filters"]["teams"][1] == {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-MCHLN"}
    assert len(jobs) == 1  # duplicate city rows merged
    j = jobs[0]
    assert j.url == "https://jobs.apple.com/en-us/details/200663858/software-engineer-maps"
    assert j.location == "Cupertino, California, USA; Seattle, Washington, USA" and j.posted_at == "2026-10-03"
    d = c.enrich(j).description
    assert d.startswith("Bachelor's degree in CS\n5+ years") and "Minimum Qualifications" not in d
    assert "Build maps." in d
