"""Discord webhook sender: routing to channels, 429 handling, message chunking.

Channels (env vars; each falls back to DISCORD_WEBHOOK_URL when unset):
  jobs    -> DISCORD_WEBHOOK_URL        regular new-job alerts and digests
  newgrad -> DISCORD_WEBHOOK_NEWGRAD    early-career (🎓) alerts
  health  -> DISCORD_WEBHOOK_HEALTH     collector warnings/recoveries + daily heartbeat
"""
from __future__ import annotations

import logging
import os
import time

import requests

from models import Job

log = logging.getLogger("discord")
LIMIT = 1900
CHANNEL_ENV = {"jobs": "DISCORD_WEBHOOK_URL", "newgrad": "DISCORD_WEBHOOK_NEWGRAD", "health": "DISCORD_WEBHOOK_HEALTH"}
SPONSORSHIP_LINE = {
    "green": "🟢 Posting says visa sponsorship is available",
    "yellow": "🟡 Sponsorship not stated: check the posting",
    "red": "🔴 Posting mentions a sponsorship/citizenship restriction: verify",
}


def format_job(job: Job, early: bool, sponsorship: str) -> str:
    header = "🎓 NEW GRAD JOB" if early else "🚨 NEW JOB"
    msg = f"{header}\n\n{job.company}\n{job.title}\n{job.location or 'Location not listed'}\n\n{job.url}"
    if sponsorship in SPONSORSHIP_LINE:
        msg += f"\n\n{SPONSORSHIP_LINE[sponsorship]}"
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
        default = webhook or os.getenv("DISCORD_WEBHOOK_URL")
        self.webhooks = {ch: (os.getenv(env) or default) for ch, env in CHANNEL_ENV.items()}
        self.webhooks["jobs"] = default
        self.dry_run = dry_run
        if not default and not dry_run:
            raise RuntimeError("DISCORD_WEBHOOK_URL is not set (use --dry-run to test without it)")

    def send(self, content: str, channel: str = "jobs") -> bool:
        if self.dry_run:
            print(f"\n----- DISCORD #{channel} (dry run) -----\n" + content)
            return True
        url = self.webhooks.get(channel) or self.webhooks["jobs"]
        for _ in range(5):
            r = requests.post(url, json={"content": content[:2000], "allowed_mentions": {"parse": []}}, timeout=15)
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 2)) + 0.25)
                continue
            if r.ok:
                time.sleep(0.4)  # stay well under webhook rate limits
                return True
            log.error("discord %s: %s", r.status_code, r.text[:200])
            return False
        return False
