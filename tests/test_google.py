"""Offline tests for Google: batchexecute protocol, record mapping, page mode, paging."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.google import GoogleCollector, build_freq, parse_batchexecute, record_to_job


def rec(jid, title, company="Google", locs=(("Mountain View, CA, USA",),), ts=1790000000):
    r = [None] * 20
    r[0], r[1], r[2] = jid, title, f"https://www.google.com/about/careers/applications/signin?jobId={jid}"
    r[3] = [None, "<ul><li>Build systems</li></ul>"]
    r[4] = [None, "<p>BS in CS</p>"]
    r[7] = company
    r[9] = [list(l) for l in locs]
    r[10] = [None, "<p>Join Google.</p>"]
    r[12] = [ts, 0]
    r[19] = [None, "<p>1 year of experience with Python</p>"]
    return r


def envelope(payload, chunked=False):
    inner = [["wrb.fr", "r06xKb", json.dumps(payload), None, None, None, "generic"]]
    line = json.dumps(inner)
    return ")]}'\n\n" + (f"{len(line)}\n{line}\n25\n[[\"e\",4,null,null,123]]\n" if chunked else line)


def test_freq_roundtrip():
    f = json.loads(build_freq("r06xKb", ["q", None, 3]))
    assert f[0][0][0] == "r06xKb" and json.loads(f[0][0][1]) == ["q", None, 3]


def test_parse_plain_and_chunked():
    payload = [[rec("123", "Software Engineer")], None, 1]
    for chunked in (False, True):
        out = parse_batchexecute(envelope(payload, chunked), "r06xKb")
        assert out[0][0][0][1] == "Software Engineer"


def test_record_mapping():
    j = record_to_job(rec("123456", "Software Engineer, Early Career",
                          locs=(("Mountain View, CA, USA", "x"), ("New York, NY, USA",))))
    assert j.url == "https://www.google.com/about/careers/applications/jobs/results/123456-software-engineer-early-career"
    assert j.location == "Mountain View, CA, USA; New York, NY, USA"
    assert "1 year of experience" in j.description and "<p>" not in j.description
    assert j.posted_at == "2026-09-21"


class Resp:
    def __init__(self, text): self.text = text


class FakeHTTP:
    def __init__(self, pages): self.pages, self.calls = pages, []
    def post(self, url, params=None, data=None, headers=None):
        args = json.loads(json.loads(data["f.req"])[0][0][1])
        self.calls.append(args)
        return Resp(envelope(self.pages.get(args[7], [[], None, 0])))


def test_rpc_fallback_and_waymo_excluded():
    page1 = [[rec(str(i), f"Software Engineer {i}") for i in range(5)] + [rec("w", "SWE", company="Waymo")]]

    class Both(FakeHTTP):
        def get(self, url, params=None, headers=None):
            return Resp("<html>no embedded data</html>")

    http = Both({1: page1})
    c = GoogleCollector({"name": "Google", "queries": ["software engineer"], "max_pages": 2,
                         "exclude_companies": ["Waymo"]}, http)
    jobs = c.fetch()
    assert len(jobs) == 5 and all("Waymo" not in j.company for j in jobs)
    assert http.calls[0][0] == "software engineer" and http.calls[0][7] == 1


def html_page(records):
    payload = [records, None, len(records)]
    return ("<html><script>AF_initDataCallback({key: 'ds:0', hash: '1', data:[null], sideChannel: {}});</script>"
            f"<script>AF_initDataCallback({{key: 'ds:1', hash: '2', data:{json.dumps(payload)}, sideChannel: {{}}}});</script></html>")


class FakePageHTTP:
    def __init__(self, pages): self.pages, self.calls = pages, []
    def get(self, url, params=None, headers=None):
        self.calls.append(params)
        return Resp(html_page(self.pages.get(params["page"], [])))


def test_html_mode_pages_and_params():
    pages = {1: [rec(str(i), f"Software Engineer {i}") for i in range(20)],
             2: [rec(str(i), f"Software Engineer {i}") for i in range(20, 40)],
             3: [rec("41", "Software Engineer 41")]}
    http = FakePageHTTP(pages)
    cfg = {"name": "Google", "queries": ["software engineer"], "max_pages": 2, "bootstrap_pages": 15}
    c = GoogleCollector(cfg, http)
    assert len(c.fetch()) == 40 and [p["page"] for p in http.calls] == [1, 2]   # steady state: 2 pages
    assert http.calls[0]["target_level"] == ["EARLY", "MID"] and http.calls[0]["sort_by"] == "date"

    http2 = FakePageHTTP(pages)
    c2 = GoogleCollector(cfg, http2)
    c2.first_scan = True
    assert len(c2.fetch()) == 41 and [p["page"] for p in http2.calls] == [1, 2, 3]  # first scan: until short page
