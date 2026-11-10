import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors import build
from collectors.avature import detail_text, parse_results
from models import job_id_from_url

ITEM = ('<div class="article__header__text"> <h3 class="article__header__text__title title title--04"> '
        '<a class="link" href="https://bloomberg.avature.net/careers/JobDetail/{slug}/{id}"> {title} </a> </h3> '
        '<div class="article__header__text__subtitle"> <span class="list-item-location">{loc}</span> </div> </div>')


def page(start, n):
    return "<html>" + "".join(ITEM.format(slug=f"Software-Engineer-{i}", id=46000 + i, title=f"Software Engineer {i}",
                                          loc="New York, New York, United States of America")
                                for i in range(start, start + n)) + "</html>"


DETAIL = ("<html><nav>Our Company Events Search Jobs Login</nav><h1>Software Engineer</h1> Location New York "
          "Description &amp; Requirements <p>Our Team builds systems.</p><ul><li>2+ years of experience in "
          "software development</li></ul><script>var x=1;</script></html>")


class Resp:
    def __init__(self, t): self.text = t


class FakeHTTP:
    def __init__(self): self.urls = []
    def get(self, url, **kw):
        self.urls.append(url)
        if "JobDetail" in url:
            return Resp(DETAIL)
        off = int(url.split("jobOffset=")[1])
        return Resp(page(off, 12 if off < 24 else 7))


def test_parse_and_paginate():
    http = FakeHTTP()
    cfg = {"key": "bloomberg", "name": "Bloomberg", "collector": "avature", "host": "bloomberg.avature.net",
           "search_params": "1845=%5B162508%5D&listFilterMode=1&jobRecordsPerPage=12&", "max_pages": 8}
    c = build(cfg, http)
    jobs = c.fetch()
    assert len(jobs) == 31 and len(http.urls) == 3
    assert http.urls[1].endswith("jobRecordsPerPage=12&jobOffset=12")
    j = jobs[0]
    assert j.title == "Software Engineer 0" and j.location == "New York, New York, United States of America"
    assert job_id_from_url(j.url) == "46000"
    d = c.enrich(j).description
    assert d.startswith("Our Team builds systems.") and "2+ years" in d and "var x" not in d and "Login" not in d


def test_real_snippet_shape():
    real = ('<a class="link" href="https://bloomberg.avature.net/careers/JobDetail/M365-Engineer-CW/46069"> '
            'M365 Engineer (CW) </a> </h3> <div class="article__header__text__subtitle"> '
            '<span class="list-item-location">New York, New York, United States of America</span>')
    assert parse_results(real) == [("46069", "M365 Engineer (CW)", "New York, New York, United States of America",
                                    "https://bloomberg.avature.net/careers/JobDetail/M365-Engineer-CW/46069")]
