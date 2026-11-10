import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_loader import load_filters
from engine import _maybe_heartbeat, run_all
from models import Job
from notifications.discord import format_job
from storage.database import Store

F = load_filters()


class ChanNotifier:
    def __init__(self): self.sent = []
    def send(self, msg, channel="jobs"): self.sent.append((channel, msg)); return True


class Col:
    def __init__(self, jobs): self.jobs = jobs
    def fetch(self): return [Job(**j.__dict__) for j in self.jobs]
    def enrich(self, j):
        yrs = "0-2 years" if "Grad" in j.title else "3+ years"
        j.description = f"{yrs} of experience. Visa sponsorship is available."; return j


def test_routing_newgrad_vs_jobs_and_tags():
    store, n = Store(":memory:"), ChanNotifier()
    cfg = {"acme": {"key": "acme", "name": "Acme", "collector": "x"}}
    col = Col([Job("Acme", "Platform Engineer", "Austin, TX", "https://acme.com/jobs/1001")])
    run_all(cfg, lambda c: col, store, n, F, {"bootstrap": "silent", "heartbeat_hour_utc": 99})
    col.jobs += [Job("Acme", "Software Engineer, New Grad 2027", "Austin, TX", "https://acme.com/jobs/1002"),
                 Job("Acme", "Backend Engineer", "Austin, TX", "https://acme.com/jobs/1003")]
    run_all(cfg, lambda c: col, store, n, F, {"bootstrap": "silent", "heartbeat_hour_utc": 99})
    chans = {msg.split("\n")[3]: ch for ch, msg in n.sent}
    assert chans["Software Engineer, New Grad 2027"] == "newgrad"
    assert chans["Backend Engineer"] == "jobs"
    assert all("🟢" in msg for _, msg in n.sent)


def test_sponsorship_lines():
    j = Job("A", "SWE", "Boston, MA", "https://a.com/jobs/1")
    assert "🟡" in format_job(j, False, "yellow") and "🔴" in format_job(j, False, "red")


def test_heartbeat_once_per_day():
    store, n = Store(":memory:"), ChanNotifier()
    for _ in range(20):
        store.record_run(27, 0, 1000, 2, 1)
    t = datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc)
    _maybe_heartbeat(store, n, {"heartbeat_hour_utc": 13}, 27, now=t)
    _maybe_heartbeat(store, n, {"heartbeat_hour_utc": 13}, 27, now=t)
    assert len(n.sent) == 1 and n.sent[0][0] == "health" and "ALIVE" in n.sent[0][1]
    early = Store(":memory:"); n2 = ChanNotifier()
    _maybe_heartbeat(early, n2, {"heartbeat_hour_utc": 13}, 27, now=datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc))
    assert n2.sent == []
