"""Pipeline: collect -> location/title filter -> dedup -> enrich -> experience filter -> store -> notify."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from filters.experience import experience_verdict
from filters.roles import is_us_location, title_verdict
from filters.sponsorship import sponsorship_status
from models import Job
from notifications.discord import format_digest, format_job

log = logging.getLogger("engine")


@dataclass
class Result:
    found: int = 0
    candidates: int = 0
    matched: list = field(default_factory=list)
    alerts_sent: int = 0
    rejected: int = 0


def process_company(cfg: dict, collector, store, notifier, filters: dict, settings: dict) -> Result:
    key, res = cfg["key"], Result()
    roles_cfg, loc_cfg = dict(filters.get("roles", {})), filters.get("location", {})
    # per-company title tweaks, e.g. Google "Software Engineer III" is a 2-year role
    skip, extra = cfg.get("skip_exclude_title") or [], cfg.get("extra_exclude_title") or []
    if skip or extra:
        roles_cfg["exclude_title"] = [p for p in roles_cfg.get("exclude_title", []) if p not in skip] + list(extra)
    exp_cfg, sp_cfg = filters.get("experience", {}), filters.get("sponsorship", {})
    first_scan = store.is_first_scan(key)
    collector.first_scan = first_scan  # collectors may read deeper on first scan

    summaries = collector.fetch()
    res.found = len(summaries)

    # Cheap filters first, so we only hit detail endpoints for new, plausible jobs.
    candidates: list[tuple[str, Job]] = []
    for job in summaries:
        if not job.title or not job.url:
            continue
        if not is_us_location(job.location, loc_cfg):
            continue
        if not title_verdict(job.title, roles_cfg)[0]:
            continue
        fp = job.fingerprint  # computed from the summary so it's stable across runs
        if store.is_settled(fp):
            continue
        candidates.append((fp, job))
    res.candidates = len(candidates)

    matched: list[tuple[str, Job, bool, str]] = []
    for fp, job in candidates:
        try:
            job = collector.enrich(job)
        except Exception as e:  # leave unsaved -> retried next run
            log.warning("%s: enrich failed for %r: %s", key, job.title, e)
            continue
        if not is_us_location(job.location, loc_cfg):
            store.save(key, job, "rejected", "non-US location", fp=fp)
            res.rejected += 1
            continue
        keep, early, reason = experience_verdict(job.title, job.description, exp_cfg)
        sponsorship = sponsorship_status(job.description, sp_cfg)
        if keep and sponsorship == "red" and settings.get("drop_restricted"):
            keep, reason = False, "sponsorship restriction"
        if not keep:
            store.save(key, job, "rejected", reason, early, sponsorship, fp=fp)
            res.rejected += 1
            continue
        matched.append((fp, job, early, sponsorship))
    res.matched = [m[1] for m in matched]

    if not matched:
        return res

    # Early-career first so they're at the top of digests / arrive first.
    matched.sort(key=lambda m: not m[2])
    company = cfg["name"]

    if first_scan:
        for fp, job, early, sp in matched:
            store.save(key, job, "seeded", "first scan", early, sp, fp=fp)
        if settings.get("bootstrap", "digest") == "digest":
            for chunk in format_digest(company, [m[1] for m in matched], "📋 NOW WATCHING — currently open"):
                notifier.send(chunk)
        return res

    cap = int(settings.get("max_alerts_per_company", 15))
    if len(matched) > cap:  # probably a site change that shifted fingerprints; don't spam the phone
        for fp, job, early, sp in matched:
            store.save(key, job, "pending", "", early, sp, fp=fp)
        ok = all(notifier.send(c) for c in format_digest(company, [m[1] for m in matched],
                                                          "🚨 NEW JOBS (bulk — check collector if unexpected)"))
        if ok:
            for fp, *_ in matched:
                store.mark(fp, "notified")
            res.alerts_sent = len(matched)
        return res

    for fp, job, early, sp in matched:
        store.save(key, job, "pending", "", early, sp, fp=fp)
        if notifier.send(format_job(job, early, sp)):
            store.mark(fp, "notified")
            res.alerts_sent += 1
    return res


def run_all(companies: dict, build_collector, store, notifier, filters: dict, settings: dict) -> dict:
    threshold = int(settings.get("failure_alert_threshold", 3))
    summary = {}
    for key, cfg in companies.items():
        try:
            collector = build_collector(cfg)
            res = process_company(cfg, collector, store, notifier, filters, settings)
        except Exception as e:  # one broken collector never stops the others
            log.exception("%s: collector failed", key)
            h = store.record_failure(key, f"{type(e).__name__}: {e}")
            summary[key] = f"FAILED ({h['consecutive_failures']}x): {e}"
            _maybe_warn(cfg, h, store, notifier, threshold)
            continue

        prev = store.health(key)
        if res.found == 0 and (prev.get("jobs_found") or 0) > 0:
            # Returning nothing when we used to get results usually means the site changed.
            h = store.record_failure(key, f"returned 0 jobs (previously {prev['jobs_found']})")
            summary[key] = "SUSPICIOUS: 0 jobs"
            _maybe_warn(cfg, h, store, notifier, threshold)
            continue

        prev = store.record_success(key, res.found, len(res.matched))
        if prev.get("warned"):
            notifier.send(f"✅ COLLECTOR RECOVERED\n\n{cfg['name']} collector is working again.")
        summary[key] = (f"found={res.found} candidates={res.candidates} matched={len(res.matched)} "
                        f"rejected={res.rejected} alerts={res.alerts_sent}")
        log.info("%s: %s", key, summary[key])
    return summary


def _maybe_warn(cfg, health, store, notifier, threshold):
    if health["consecutive_failures"] >= threshold and not health.get("warned"):
        last_ok = health.get("last_successful_scan") or "never"
        notifier.send(
            f"⚠️ COLLECTOR WARNING\n\n{cfg['name']} collector may be failing.\n"
            f"Failed {health['consecutive_failures']} scans in a row.\n"
            f"Last successful scan: {last_ok} UTC\nError: {(health.get('last_error') or '')[:300]}"
        )
        store.set_warned(cfg["key"])
