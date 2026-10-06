import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_loader import load_filters
from engine import run_all
from filters.roles import is_us_location
from models import Job, job_id_from_url
from storage.database import Store

F = load_filters()


def test_job_ids():
    assert job_id_from_url("https://x.myworkdayjobs.com/en-US/S/job/A-B/Title_JR355250-1") == "JR355250-1"
    assert job_id_from_url("https://www.google.com/about/careers/applications/jobs/results/874571-software-eng") == "874571"
    assert job_id_from_url("https://jobs.uber.com/en/jobs/302988/") == "302988"
    assert job_id_from_url("https://careers.doordash.com/jobs/1?gh_jid=7580407") == "7580407"


def test_costa_rica_and_friends():
    L = F["location"]
    assert not is_us_location("San Jose, Costa Rica", L)
    assert is_us_location("San Jose, California, US", L)
    assert is_us_location("Albuquerque, New Mexico, USA", L)
    assert is_us_location("Santa Clara, CA; Bangalore, India", L)


class Notifier:
    def __init__(self): self.sent = []
    def send(self, m): self.sent.append(m); return True


class Col:
    def __init__(self, jobs): self.jobs = jobs
    def fetch(self): return [Job(**j.__dict__) for j in self.jobs]
    def enrich(self, j): j.description = "0-2 years of experience"; return j


def test_location_change_does_not_realert():
    store, n = Store(":memory:"), Notifier()
    cfg = {"acme": {"key": "acme", "name": "Acme", "collector": "x"}}
    url = "https://acme.wd5.myworkdayjobs.com/Ext/job/X/Software-Engineer_JR1"
    col = Col([Job("Acme", "Software Engineer I", "6 Locations", url)])
    run_all(cfg, lambda c: col, store, n, F, {"bootstrap": "silent"})         # first scan: silent
    col.jobs = [Job("Acme", "Software Engineer I", "7 Locations", url)]        # site edits location text
    run_all(cfg, lambda c: col, store, n, F, {"bootstrap": "silent"})
    assert n.sent == []                                                        # same job id -> no re-alert


def test_migration_backfills_job_key(tmp_path=None):
    import tempfile, os
    path = os.path.join(tempfile.mkdtemp(), "old.db")
    db = sqlite3.connect(path)
    db.executescript("""CREATE TABLE jobs (fingerprint TEXT PRIMARY KEY, company_key TEXT NOT NULL, company TEXT NOT NULL,
        title TEXT NOT NULL, location TEXT, official_url TEXT NOT NULL, posted_at TEXT, description TEXT,
        status TEXT NOT NULL, reason TEXT, early_career INTEGER DEFAULT 0, sponsorship TEXT,
        first_seen TEXT NOT NULL, notified INTEGER NOT NULL DEFAULT 0);
        INSERT INTO jobs VALUES ('fp1','google','Google','SWE III','Sunnyvale',
        'https://www.google.com/about/careers/applications/jobs/results/87457161382109894-swe','x',
        '', 'seeded','',0,'yellow','2026-10-03',0);""")
    db.commit(); db.close()
    s = Store(path)
    assert s.is_settled("different-fp", "google|87457161382109894")
