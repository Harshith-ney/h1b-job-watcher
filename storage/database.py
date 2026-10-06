"""SQLite persistence: matched/rejected jobs (dedup) + per-collector health."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from models import Job, job_id_from_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    fingerprint   TEXT PRIMARY KEY,
    company_key   TEXT NOT NULL,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    location      TEXT,
    official_url  TEXT NOT NULL,
    posted_at     TEXT,
    description   TEXT,
    status        TEXT NOT NULL,      -- notified | pending | rejected | seeded
    reason        TEXT,
    early_career  INTEGER DEFAULT 0,
    sponsorship   TEXT,               -- red | yellow | green
    first_seen    TEXT NOT NULL,
    notified      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_key);

CREATE TABLE IF NOT EXISTS collector_health (
    company_key           TEXT PRIMARY KEY,
    last_successful_scan  TEXT,
    last_error            TEXT,
    last_error_at         TEXT,
    consecutive_failures  INTEGER NOT NULL DEFAULT 0,
    jobs_found            INTEGER,
    matching_jobs_found   INTEGER,
    warned                INTEGER NOT NULL DEFAULT 0
);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Store:
    def __init__(self, path: str | Path = "state/jobs.db"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(jobs)")}
        if "job_key" not in cols:
            self.db.execute("ALTER TABLE jobs ADD COLUMN job_key TEXT")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_key ON jobs(job_key)")
        rows = self.db.execute("SELECT fingerprint, company, official_url FROM jobs WHERE job_key IS NULL").fetchall()
        for fp, company, url in rows:
            jid = job_id_from_url(url or "")
            if jid:
                self.db.execute("UPDATE jobs SET job_key=? WHERE fingerprint=?", (f"{company.strip().lower()}|{jid}", fp))
        self.db.commit()

    # ---- jobs -------------------------------------------------------------
    def is_settled(self, fp: str, key: str | None = None) -> bool:
        """Seen and finished (pending notifications get retried). Matches by fingerprint OR stable job key."""
        rows = self.db.execute("SELECT status FROM jobs WHERE fingerprint=? OR (job_key IS NOT NULL AND job_key=?)",
                               (fp, key or "")).fetchall()
        return any(r["status"] != "pending" for r in rows)

    def save(self, key: str, job: Job, status: str, reason: str = "",
             early: bool = False, sponsorship: str | None = None, fp: str | None = None,
             job_key: str | None = None) -> None:
        self.db.execute(
            """INSERT INTO jobs (fingerprint, company_key, company, title, location, official_url, posted_at,
                                 description, status, reason, early_career, sponsorship, first_seen, notified, job_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(fingerprint) DO UPDATE SET status=excluded.status, notified=excluded.notified,
                 reason=excluded.reason""",
            (fp or job.fingerprint, key, job.company, job.title, job.location, job.url, job.posted_at,
             job.description, status, reason, int(early), sponsorship, now(), int(status == "notified"),
             job_key or job.job_key),
        )
        self.db.commit()

    def mark(self, fp: str, status: str) -> None:
        self.db.execute("UPDATE jobs SET status=?, notified=? WHERE fingerprint=?",
                        (status, int(status == "notified"), fp))
        self.db.commit()

    # ---- health -----------------------------------------------------------
    def health(self, key: str) -> dict:
        row = self.db.execute("SELECT * FROM collector_health WHERE company_key=?", (key,)).fetchone()
        return dict(row) if row else {}

    def is_first_scan(self, key: str) -> bool:
        return not self.health(key).get("last_successful_scan")

    def record_success(self, key: str, found: int, matching: int) -> dict:
        prev = self.health(key)
        self.db.execute(
            """INSERT INTO collector_health (company_key, last_successful_scan, consecutive_failures,
                                             jobs_found, matching_jobs_found, warned)
               VALUES (?,?,0,?,?,0)
               ON CONFLICT(company_key) DO UPDATE SET last_successful_scan=excluded.last_successful_scan,
                 consecutive_failures=0, jobs_found=excluded.jobs_found,
                 matching_jobs_found=excluded.matching_jobs_found, warned=0""",
            (key, now(), found, matching),
        )
        self.db.commit()
        return prev

    def record_failure(self, key: str, error: str) -> dict:
        self.db.execute(
            """INSERT INTO collector_health (company_key, last_error, last_error_at, consecutive_failures)
               VALUES (?,?,?,1)
               ON CONFLICT(company_key) DO UPDATE SET last_error=excluded.last_error,
                 last_error_at=excluded.last_error_at, consecutive_failures=consecutive_failures+1""",
            (key, error[:500], now()),
        )
        self.db.commit()
        return self.health(key)

    def set_warned(self, key: str) -> None:
        self.db.execute("UPDATE collector_health SET warned=1 WHERE company_key=?", (key,))
        self.db.commit()
