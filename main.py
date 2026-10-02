"""H1B SWE/AI Job Watcher.

  python main.py run                 # scan enabled companies, alert Discord
  python main.py run --dry-run       # print alerts instead of sending; uses a throwaway in-memory DB
  python main.py run --only nvidia amazon
  python main.py probe               # verify every collector (incl. disabled) without DB/Discord
  python main.py probe --only apple
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

import collectors
from config_loader import load_companies, load_filters, load_yaml
from engine import run_all
from filters.experience import experience_verdict
from filters.roles import is_us_location, title_verdict
from http_client import PoliteSession
from notifications.discord import Discord
from storage.database import Store


def cmd_run(args) -> int:
    settings = load_yaml("companies.yaml").get("settings", {})
    companies = load_companies(args.only)
    if not companies:
        print("No enabled companies matched.")
        return 1
    http = PoliteSession(delay=float(settings.get("request_delay_seconds", 0.75)))
    store = Store(":memory:" if args.dry_run else args.db)
    notifier = Discord(dry_run=args.dry_run)
    summary = run_all(companies, lambda c: collectors.build(c, http), store, notifier, load_filters(), settings)
    print("\n=== run summary ===")
    for k, v in summary.items():
        print(f"{k:12} {v}")
    failed = sum(1 for v in summary.values() if v.startswith("FAILED"))
    # Only fail the CI job if *everything* failed (likely a global problem, e.g. network).
    return 1 if failed == len(summary) else 0


def cmd_probe(args) -> int:
    filters = load_filters()
    http = PoliteSession(delay=0.5)
    companies = load_companies(args.only, include_disabled=True)
    ok = 0
    for key, cfg in companies.items():
        print(f"\n### {cfg['name']} [{cfg['collector']}] enabled={cfg.get('enabled')}")
        try:
            c = collectors.build({**cfg, "max_pages": 2}, http)
            jobs = c.fetch()
            print(f"  fetched {len(jobs)} postings")
            hits = [j for j in jobs if is_us_location(j.location, filters["location"])
                    and title_verdict(j.title, filters["roles"])[0]]
            print(f"  {len(hits)} pass location+title filters")
            for j in hits[:5]:
                print(f"   - {j.title} | {j.location}\n     {j.url}")
            if hits:
                j = c.enrich(hits[0])
                keep, early, why = experience_verdict(j.title, j.description, filters["experience"])
                print(f"  enrich OK: description {len(j.description)} chars | keep={keep} early={early} ({why})")
            ok += 1
        except Exception as e:
            print(f"  ❌ {type(e).__name__}: {e}")
    print(f"\n{ok}/{len(companies)} collectors responded")
    return 0


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="H1B SWE/AI job watcher")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--only", nargs="*")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--db", default=os.getenv("DB_PATH", "state/jobs.db"))
    pr = sub.add_parser("probe")
    pr.add_argument("--only", nargs="*")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return cmd_run(args) if args.cmd == "run" else cmd_probe(args)


if __name__ == "__main__":
    sys.exit(main())
