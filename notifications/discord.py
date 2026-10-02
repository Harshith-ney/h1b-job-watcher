"""Discord webhook sender with 429 handling and message chunking."""
from __future__ import annotations

import logging
import os
import time

import requests

from models import Job

log = logging.getLogger("discord")
LIMIT = 1900


def format_job(job: Job, early: bool, sponsorship: str) -> str:
    header = "🎓 NEW GRAD JOB" if early else "🚨 NEW JOB"
    msg = f"{header}\n\n{job.company}\n{job.title}\n{job.location or 'Location not listed'}\n\n{job.url}"
    if sponsorship == "red":
        msg += "\n\n⚠️ Posting mentions a sponsorship/citizenship restriction — verify"
    return msg


def format_digest(company: str, jobs: list[Job], title: str) -> list[str]:
    """Links wrapped in <> so Discord doesn't render 20 embeds."""
    lines = [f"{title}\n**{company}** — {len(jobs)} matching role(s)\n"]
    lines += [f"• {j.title} — {j.location or 'n/a'}\n<{j.url}>" for j in jobs]
    chunks, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > LIMIT:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    return chunks + ([cur] if cur else [])


class Discord:
    def __init__(self, webhook: str | None = None, dry_run: bool = False):
        self.webhook = webhook or os.getenv("DISCORD_WEBHOOK_URL")
        self.dry_run = dry_run
        if not self.webhook and not dry_run:
            raise RuntimeError("DISCORD_WEBHOOK_URL is not set (use --dry-run to test without it)")

    def send(self, content: str) -> bool:
        if self.dry_run:
            print("\n----- DISCORD (dry run) -----\n" + content)
            return True
        for _ in range(5):
            r = requests.post(self.webhook, json={"content": content[:2000], "allowed_mentions": {"parse": []}},
                              timeout=15)
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 2)) + 0.25)
                continue
            if r.ok:
                time.sleep(0.4)  # stay well under webhook rate limits
                return True
            log.error("discord %s: %s", r.status_code, r.text[:200])
            return False
        return False
