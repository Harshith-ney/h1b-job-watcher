import json
import sys
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors import build
from models import job_id_from_url

PAGE = '<html><script>require("x",[["LSD",[],{"token":"AdS0lPw"},323]])</script></html>'
GQL = "for (;;);" + json.dumps({"data": {"job_search_with_featured_jobs": {"all_jobs": [
    {"id": "9657291271065759", "title": "Software Engineer, Product",
     "locations": ["Sunnyvale, CA", "Remote, US", "Boston, MA"], "teams": ["Software Engineering"], "sub_teams": []},
    {"id": "1187958502273564", "title": "Software Engineer (Technical Leadership)",
     "locations": ["Menlo Park, CA"], "teams": ["Software Engineering"], "sub_teams": []}]}}})
JOB = ('<html><script>{"jobLocation":[{"address":{"\\u0040type":"PostalAddress"}}],'
       '"qualifications":"Bachelor\'s degree in Computer Science&nbsp;2+ years of experience with React",'
       '"responsibilities":"Build product experiences&nbsp;Collaborate with design"}</script></html>')


class Resp:
    def __init__(self, t): self.text = t


class FakeHTTP:
    def __init__(self): self.posts = []
    def get(self, url, **kw):
        return Resp(JOB if "/jobs/" in url else PAGE)
    def post(self, url, headers=None, data=None, **kw):
        self.posts.append((headers, data)); return Resp(GQL)


def test_meta_flow():
    http = FakeHTTP()
    c = build({"key": "meta", "name": "Meta", "collector": "meta", "teams": ["Software Engineering"]}, http)
    jobs = c.fetch()
    headers, data = http.posts[0]
    assert headers["x-fb-lsd"] == "AdS0lPw" and data["lsd"] == "AdS0lPw" and data["doc_id"] == "27129360303422352"
    v = json.loads(data["variables"])["search_input"]
    assert v["sort_by_new"] is True and v["teams"] == ["Software Engineering"]
    assert len(jobs) == 2
    j = jobs[0]
    assert j.url == "https://www.metacareers.com/jobs/9657291271065759/" and job_id_from_url(j.url) == "9657291271065759"
    assert j.location == "Sunnyvale, CA; Remote, US; Boston, MA"
    d = c.enrich(j).description
    assert d.startswith("Bachelor's degree") and "2+ years of experience" in d and "Build product" in d
