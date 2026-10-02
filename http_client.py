"""Shared HTTP session: retries, timeouts, polite pacing, honest User-Agent."""
from __future__ import annotations

import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TIMEOUT = 25


class PoliteSession(requests.Session):
    def __init__(self, delay: float = 0.75):
        super().__init__()
        self.delay = delay
        self._last = 0.0
        retry = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
        )
        self.mount("https://", HTTPAdapter(max_retries=retry))
        contact = os.getenv("CONTACT_EMAIL", "")
        self.headers.update(
            {
                "User-Agent": f"Mozilla/5.0 (compatible; personal-job-alerts/1.0{'; ' + contact if contact else ''})",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def request(self, method, url, **kwargs):
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        kwargs.setdefault("timeout", TIMEOUT)
        try:
            resp = super().request(method, url, **kwargs)
        finally:
            self._last = time.monotonic()
        resp.raise_for_status()
        return resp
