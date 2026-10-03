# H1B SWE/AI Job Watcher

Hourly scanner for new early-career Software Engineering and AI/ML roles at H-1B-heavy US employers.
It reads each company's **official** careers backend, filters for fit, and pings Discord with the
official link, usually within about an hour of posting.

~~~
fetch (official API) → US location → SWE/AI title → already seen? → fetch details
  → years / early-career check → sponsorship check → SQLite (state branch) → Discord
~~~

## Companies (15 live)

| Company | Collector | Source |
|---|---|---|
| Amazon | `amazon` | amazon.jobs `search.json`, newest first |
| Microsoft | `eightfold` | apply.careers.microsoft.com `/api/pcsx/search` |
| Qualcomm | `eightfold` | careers.qualcomm.com `/api/pcsx/search` |
| Google | `google` | Server-rendered results page (embedded JSON); `r06xKb` RPC fallback |
| Apple | `apple` | jobs.apple.com `/api/v1/search`, filtered by 9 Software and Services sub-teams |
| NVIDIA, Salesforce, Intel, Adobe, PayPal, Cisco | `workday` | `*.myworkdayjobs.com` CXS API |
| DoorDash | `greenhouse` | Greenhouse job board API |
| Snowflake | `ashby` | Ashby posting API |
| JPMorgan Chase | `oracle` | Oracle Recruiting Cloud (`jpmc.fa.oraclecloud.com`, site `CX_1001`) |
| Uber | `oracle` | Oracle Recruiting Cloud (`iaziqy.fa.ocs.oraclecloud.com`, site `UberCareers`) |

**Not yet covered:** Meta, Goldman Sachs, Bloomberg, IBM, LinkedIn, AMD.

## How it runs

- **Schedule:** GitHub Actions, hourly at :17 (`.github/workflows/watch.yml`). GitHub's scheduler
  can be late or skip slots. For punctual runs, an external cron (e.g. cron-job.org) can call the
  `workflow_dispatch` API every hour with a fine-grained token that has *Actions: read & write* on this repo.
- **State:** `jobs.db` (SQLite) lives on the **`state` branch**, force-pushed as a single commit each run,
  so history never grows. `main` only changes when you change it.
- **Secrets:** `DISCORD_WEBHOOK_URL` (required), `CONTACT_EMAIL` (optional, added to the User-Agent).

## Alerts

| Situation | What happens |
|---|---|
| New matching job | `🚨 NEW JOB`, or `🎓 NEW GRAD JOB` when an early-career signal is found |
| First scan of a newly added company | Silent: everything currently open is recorded as seen (`bootstrap: silent`) |
| More than 15 new matches for one company in one run | One digest instead of individual pings (usually a site change) |
| Posting states no sponsorship / citizens only / clearance | Dropped if `drop_restricted: true`, otherwise sent with a ⚠️ line |
| Rejected job (too senior, too many years) | Stored as rejected, never fetched again |
| Discord send fails | Stored as pending, retried next run |
| Company fails 3 runs in a row, or suddenly returns 0 jobs | One `⚠️ COLLECTOR WARNING`, then `✅ RECOVERED` |

## Filters (`config/filters.yaml`)

- **Titles:** SWE, backend, full-stack, platform, infrastructure, distributed systems, and AI/ML titles
  (AI, ML, GenAI, LLM, deep learning, computer vision, inference, voice/conversational AI,
  forward-deployed, AI developer). Rejects Senior, Staff, Principal, Lead, Manager, Director, Architect,
  III+, intern, PhD, sales, and clearance/CTJ/Poly titles.
- **Experience:** a SWE/AI title with an early-career signal (New Grad, College Graduate, University
  Graduate, Early Career, 2027, Engineer I, AMTS…) always passes. Otherwise the **first** years figure in
  the description must be ≤ `max_min_years`. If no years are stated, `unknown_years` decides (keep | drop).
- **Location:** US only, lenient for multi-location postings that include a US site.
- **Sponsorship:** regex for explicit restrictions ("no sponsorship", "US citizens only", "security clearance", ITAR…).

### Per-company overrides (`config/companies.yaml`)

| Key | Purpose | Example |
|---|---|---|
| `queries`, `max_pages`, `page_delay` | What to search, how deep, how politely | Microsoft: `page_delay: 4` |
| `skip_exclude_title` / `extra_exclude_title` | Adjust title excludes for one company | Google allows "Software Engineer III" (≈2 yrs) |
| `experience:` | Override experience settings | Apple: `unknown_years: keep` |
| `teams` | Apple sub-team codes | `[AF, CLD, DSR, ISTECH, MCHLN, COS, SC, TS, UEE]` |
| `location`, `target_levels`, `bootstrap_pages` | Google search filters | `target_levels: [EARLY, MID]` |
| `exclude_companies` | Drop sub-brands | Google: `["Waymo"]` |
| `host`, `site`, `job_url` | Oracle setup and alert link | Uber links to `jobs.uber.com/en/jobs/{id}/` |

## Local use

~~~bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # add DISCORD_WEBHOOK_URL
python -m pytest -q                        # offline tests
python main.py probe [--only google apple] # live check per collector: counts, samples, detail fetch
python main.py run --dry-run [--only uber] # full pipeline, prints instead of sending, throwaway DB
python funnel.py --only nvidia             # where jobs drop out, with sample titles
python -m collectors.google "software engineer"   # raw Google parse check
gh workflow run job-watcher                # trigger a production run now
gh run list --limit 3                      # check runs (look for EVENT = schedule)
~~~

## Adding a company

1. Open its careers search with DevTools → Network and find the request that returns jobs.
2. If it's Workday, Greenhouse, Ashby, Lever, Eightfold or Oracle Recruiting Cloud, it's config only.
   Clicking **Apply** on a job often reveals the backend host (that's how Uber's Oracle host was found).
3. Otherwise add `collectors/<name>.py` with `fetch()` (+ optional `enrich()`), register it in
   `collectors/__init__.py`, and add a test with a fixture copied from the real response.
4. `python main.py probe --only <key>`, then a dry run, then push. The first scan is silent.

## Known limitations

- **Silent failure:** if the workflow stops entirely, nothing warns you (heartbeat not built yet).
- **Search windows:** Workday is relevance-sorted with a 200-result cap per keyword. Oracle searches
  are global newest-first. Microsoft reads 30 per keyword because of rate limits.
- **Regex judgment:** unusual titles or years phrasing can be misread. Sponsorship detection only
  catches explicit wording.
- **Undocumented APIs:** collectors depend on internal endpoints (e.g. Apple requires `"format": {}`),
  so expect occasional breakage and small fixes.
- **Existing openings never alert:** first scans are silent, so check new companies manually once.

## Rules

Official endpoints only, ~0.75s between requests, retries with backoff, honest User-Agent.
No CAPTCHA or anti-bot bypass (Uber's Cloudflare-protected API is not used), no personal credentials,
no auto-apply.
