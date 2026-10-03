import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors import build


class Resp:
    def __init__(self, d): self.d = d
    def json(self): return self.d


class FakeHTTP:
    def __init__(self): self.urls = []
    def get(self, url, **kw):
        self.urls.append(unquote(url))
        if "recruitingCEJobRequisitionDetails" in url:
            return Resp({"items": [{"ExternalQualificationsStr": "<ul><li>2+ years of Java experience</li></ul>",
                                    "ExternalDescriptionStr": "<p>Join JPMorgan.</p>",
                                    "ExternalResponsibilitiesStr": "<p>Build APIs</p>"}]})
        offset = int(unquote(url).split("offset=")[1].split("&")[0].split(",")[0])
        reqs = [{"Id": str(1000 + offset + i), "Title": f"Software Engineer II {offset + i}",
                 "PrimaryLocation": "New York, NY, United States", "PostedDate": "2026-10-01",
                 "ShortDescriptionStr": "short",
                 "secondaryLocations": [{"Name": "Jersey City, NJ, United States"}]}
                for i in range(25 if offset == 0 else 3)]
        return Resp({"items": [{"TotalJobsCount": 28, "requisitionList": reqs}]})


def test_oracle_search_paging_and_details():
    http = FakeHTTP()
    cfg = {"key": "jpmorgan", "name": "JPMorgan Chase", "collector": "oracle", "host": "jpmc.fa.oraclecloud.com",
           "site": "CX_1001", "queries": ["software engineer"], "max_pages": 5}
    c = build(cfg, http)
    jobs = c.fetch()
    assert len(jobs) == 28 and len(http.urls) == 2                     # stopped after short page
    u = http.urls[0]
    assert 'finder=findReqs;siteNumber=CX_1001,keyword="software engineer",sortBy=POSTING_DATES_DESC,limit=25,offset=0' in u
    j = jobs[0]
    assert j.url == "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/1000"
    assert j.location == "New York, NY, United States; Jersey City, NJ, United States"
    d = c.enrich(j).description
    assert d.startswith("2+ years of Java experience") and "<" not in d
    assert 'finder=ById;Id="1000",siteNumber=CX_1001' in http.urls[-1]
