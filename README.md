# H1B SWE/AI Job Watcher

Polls official career APIs of H-1B-heavy employers every 2h and pings Discord when a new
early-career-friendly SWE/AI role shows up.

```
fetch (cheap list) → US location → SWE/AI title → already seen? → fetch details
  → years-of-experience / early-career → sponsorship hint → SQLite → Discord
```

## Setup (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # paste your Discord webhook
python -m pytest -q
python main.py probe            # hits every collector (incl. disabled), prints counts + samples
python main.py run --dry-run    # full pipeline, prints messages, throwaway DB
python main.py run              # real run, writes state/jobs.db, sends Discord
```

## Deploy (GitHub Actions, free)

1. Push to a **private** repo.
2. Settings → Secrets and variables → Actions → add `DISCORD_WEBHOOK_URL` (optional `CONTACT_EMAIL`).
3. Actions → job-watcher → Run workflow (first manual run).

State lives in `state/jobs.db`, committed back after every run. ~12 runs/day × 2–4 min fits the
2,000 free private-repo minutes/month. GitHub cron can lag 10–30 min — fine at a 2h cadence.

## Behaviour

| Situation | What happens |
|---|---|
| First successful scan of a company | One 📋 digest of everything currently open, no individual pings |
| New matching job | `🚨 NEW JOB` (or `🎓 NEW GRAD JOB` if early-career signals found) |
| > 15 new matches in one run | One digest instead of 15 pings (usually means a site changed URLs) |
| Posting mentions no-sponsorship / citizens-only | Still sent, with a ⚠️ line (`drop_restricted: true` to skip) |
| Job rejected for 5+ years etc. | Stored as `rejected`, never re-fetched |
| Discord send fails | Stored as `pending`, retried next run |
| Collector fails 3× in a row / returns 0 jobs | One ⚠️ COLLECTOR WARNING, then ✅ when it recovers |

## Tuning

- `config/companies.yaml` — enable/disable companies, search queries, page limits, settings.
- `config/filters.yaml` — title include/exclude regexes, `max_min_years`, early-career signals,
  `require_early_career`, US location markers, sponsorship phrases.

## Adding a company

If its careers site runs on Workday / Greenhouse / Ashby / Lever / Eightfold, it's config only:
open the careers site, DevTools → Network → find the JSON call, copy host/tenant/site or board
into `companies.yaml`, run `python main.py probe --only <key>`.
Otherwise add `collectors/<name>.py` implementing `fetch()` (+ optional `enrich()`) and register it
in `collectors/__init__.py`.

## Rules

Official endpoints only, ~0.75s between requests, retries with backoff, honest User-Agent,
no CAPTCHA/anti-bot bypass, no auto-apply.
