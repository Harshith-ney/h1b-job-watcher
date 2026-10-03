"""Oracle Fusion Recruiting Cloud (Candidate Experience) - used by JPMorgan Chase, Uber, ...

Search : GET {host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
         finder=findReqs;siteNumber=..,keyword="..",sortBy=POSTING_DATES_DESC,limit=..,offset=..
Details: GET {host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails
         finder=ById;Id="..",siteNumber=..
Both unauthenticated. Details carry structured text fields; qualifications go first so the
years filter reads the real requirement.

Config: host (e.g. jpmc.fa.oraclecloud.com), site (e.g. CX_1001), queries, max_pages,
        job_url (optional template, default Oracle candidate-experience URL).
"""
from __future__ import annotations

from urllib.parse import quote

from collectors.base import Collector, log
from models import Job, html_to_text

API = "/hcmRestApi/resources/latest"
DETAIL_FIELDS = ("ExternalQualificationsStr", "ExternalResponsibilitiesStr",
                 "ExternalDescriptionStr", "ShortDescriptionStr")


def _qs(params: dict) -> str:
    # Oracle's finder syntax uses ; , = and quotes - keep the separators literal, encode the rest
    return "&".join(f"{k}={quote(str(v), safe=';,=')}" for k, v in params.items())


class OracleCollector(Collector):
    PAGE = 25

    @property
    def base(self) -> str:
        return f"https://{self.cfg['host']}{API}"

    def _url(self, job_id: str) -> str:
        tpl = self.cfg.get("job_url") or \
            "https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{id}"
        return tpl.format(host=self.cfg["host"], site=self.cfg["site"], id=job_id)

    def fetch(self) -> list[Job]:
        jobs = []
        site, limit = self.cfg["site"], int(self.cfg.get("page_size", self.PAGE))
        for q in self.queries:
            for page in range(self.max_pages):
                finder = (f'findReqs;siteNumber={site},keyword="{q}",'
                          f'sortBy=POSTING_DATES_DESC,limit={limit},offset={page * limit}')
                params = {"onlyData": "true", "expand": "requisitionList.secondaryLocations",
                          "finder": finder}
                data = self.http.get(f"{self.base}/recruitingCEJobRequisitions?{_qs(params)}").json()
                items = data.get("items") or [{}]
                reqs = items[0].get("requisitionList") or []
                for r in reqs:
                    jid, title = r.get("Id"), r.get("Title")
                    if not jid or not title:
                        continue
                    locs = [r.get("PrimaryLocation") or ""] + \
                           [l.get("Name", "") for l in r.get("secondaryLocations") or []]
                    jobs.append(Job(
                        company=self.company,
                        title=title.strip(),
                        location="; ".join(dict.fromkeys(l for l in locs if l)),
                        url=self._url(str(jid)),
                        posted_at=(r.get("PostedDate") or "")[:10] or None,
                        description=html_to_text(r.get("ShortDescriptionStr")),
                        external_id=str(jid),
                    ))
                if len(reqs) < limit:
                    break
        return self.dedupe(jobs)

    def enrich(self, job: Job) -> Job:
        params = {"onlyData": "true", "expand": "all",
                  "finder": f'ById;Id="{job.external_id}",siteNumber={self.cfg["site"]}'}
        try:
            data = self.http.get(f"{self.base}/recruitingCEJobRequisitionDetails?{_qs(params)}").json()
            d = (data.get("items") or [{}])[0]
            text = "\n".join(html_to_text(d.get(f)) for f in DETAIL_FIELDS if d.get(f))
            if text:
                job.description = text
        except Exception as e:
            log.debug("%s: oracle detail failed for %s: %s", self.company, job.external_id, e)
        return job
