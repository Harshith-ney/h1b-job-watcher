"""Collector contract. fetch() returns cheap summaries; enrich() fills the description lazily,
only for jobs that already passed title/location filters and haven't been seen."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from models import Job

log = logging.getLogger("collector")


class Collector(ABC):
    def __init__(self, cfg: dict, http):
        self.cfg = cfg
        self.http = http
        self.company = cfg["name"]
        self.max_pages = int(cfg.get("max_pages", 10))
        self.queries = cfg.get("queries") or ["software engineer"]

    @abstractmethod
    def fetch(self) -> list[Job]:
        ...

    def enrich(self, job: Job) -> Job:
        return job

    @staticmethod
    def dedupe(jobs: list[Job]) -> list[Job]:
        seen, out = set(), []
        for j in jobs:
            if j.fingerprint not in seen:
                seen.add(j.fingerprint)
                out.append(j)
        return out
