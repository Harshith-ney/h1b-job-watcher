import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_loader import load_filters
from engine import run_all
from models import Job, normalize_url
from storage.database import Store

F = load_filters()
SETTINGS = {"bootstrap": "digest", "max_alerts_per_company": 15, "failure_alert_threshold": 3}
CFG = {"acme": {"key": "acme", "name": "Acme", "collector": "fake"}}


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)
        return True


class FakeCollector:
    def __init__(self, jobs, fail=False):
        self.jobs, self.fail, self.enriched = jobs, fail, 0

    def fetch(self):
        if self.fail:
            raise RuntimeError("site changed")
        return [Job(**j.__dict__) for j in self.jobs]

    def enrich(self, job):
        self.enriched += 1
        job.description = job.description or "BS in CS. 0-2 years of experience."
        return job


def J(title, loc="Austin, TX", n=1, desc=""):
    return Job("Acme", title, loc, f"https://careers.acme.com/job/{n}", description=desc)


def run(store, col, notif):
    return run_all(CFG, lambda c: col, store, notif, F, SETTINGS)


def test_bootstrap_then_new_then_no_duplicate():
    store, notif = Store(":memory:"), FakeNotifier()
    base = [J("Software Engineer I", n=1), J("Senior Software Engineer", n=2), J("Product Manager", n=3)]
    col = FakeCollector(base)

    run(store, col, notif)                       # first scan -> one digest, no individual pings
    assert len(notif.sent) == 1 and "NOW WATCHING" in notif.sent[0]
    assert "Software Engineer I" in notif.sent[0] and "Senior" not in notif.sent[0]

    col.jobs = base + [J("Machine Learning Engineer", "Seattle, WA", n=4)]
    run(store, col, notif)                       # new matching job -> single alert
    assert len(notif.sent) == 2
    assert notif.sent[1].startswith(("🚨 NEW JOB", "🎓 NEW GRAD JOB"))
    assert "Machine Learning Engineer" in notif.sent[1] and "https://careers.acme.com/job/4" in notif.sent[1]

    enriched_before = col.enriched
    run(store, col, notif)                       # nothing new -> nothing sent, no detail fetches
    assert len(notif.sent) == 2
    assert col.enriched == enriched_before


def test_experience_rejection_is_remembered():
    store, notif = Store(":memory:"), FakeNotifier()
    col = FakeCollector([J("Software Engineer", n=1, desc="10+ years of experience required")])
    run(store, col, notif)
    run(store, col, notif)
    assert col.enriched == 1      # rejected once, never re-fetched
    assert notif.sent == []       # (digest only fires if something matched)


def test_failure_isolation_and_health_warning():
    store, notif = Store(":memory:"), FakeNotifier()
    cfgs = {"bad": {"key": "bad", "name": "Bad", "collector": "x"},
            "good": {"key": "good", "name": "Good", "collector": "y"}}
    cols = {"bad": FakeCollector([], fail=True), "good": FakeCollector([J("Software Engineer I")])}
    for _ in range(3):
        summary = run_all(cfgs, lambda c: cols[c["key"]], store, notif, F, SETTINGS)
    assert summary["bad"].startswith("FAILED") and summary["good"].startswith("found=1")
    warnings = [m for m in notif.sent if "COLLECTOR WARNING" in m]
    assert len(warnings) == 1     # warned once, not every run

    cols["bad"] = FakeCollector([J("Software Engineer I")])
    run_all(cfgs, lambda c: cols[c["key"]], store, notif, F, SETTINGS)
    assert any("RECOVERED" in m for m in notif.sent)


def test_bulk_cap_sends_digest():
    store, notif = Store(":memory:"), FakeNotifier()
    col = FakeCollector([J("Software Engineer I", n=0)])
    run(store, col, notif)
    col.jobs = [J("Software Engineer I", n=i) for i in range(30)]
    run(store, col, notif)
    assert len(notif.sent) <= 4 and "bulk" in notif.sent[1]


def test_url_normalization_keeps_job_ids():
    a = normalize_url("https://x.com/jobs?gh_jid=1&utm_source=li#apply")
    b = normalize_url("https://x.com/jobs?gh_jid=2")
    assert a != b and "utm_source" not in a
