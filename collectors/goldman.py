"""Goldman Sachs (higher.gs.com) via its public GraphQL gateway (no login/token needed).
Search only returns metadata (title, level, locations), not descriptions. The server-side filters
(Analyst/Associate + Software Engineering) already bound experience, so config sets unknown_years: keep.

Config: experience_levels, job_functions, max_pages, page_size."""
from __future__ import annotations

import uuid

from collectors.base import Collector
from models import Job

URL = "https://api-higher.gs.com/gateway/api/v1/graphql"
QUERY = """query GetRoles($searchQueryInput: RoleSearchQueryInput!) {
  roleSearch(searchQueryInput: $searchQueryInput) {
    totalCount
    items {
      roleId corporateTitle jobTitle jobFunction
      locations { primary state country city }
      status division skills
      jobType { code description }
      externalSource { sourceId }
    }
  }
}"""


def _filter(category: str, values: list[str]) -> dict:
    return {"filterCategoryType": category, "filters": [{"filter": v, "subFilters": []} for v in values]}


class GoldmanCollector(Collector):
    def fetch(self) -> list[Job]:
        size = int(self.cfg.get("page_size", 50))
        filters = [_filter("EXPERIENCE_LEVEL", self.cfg.get("experience_levels", ["Analyst", "Associate"])),
                   _filter("JOB_FUNCTION", self.cfg.get("job_functions", ["Software Engineering"]))]
        headers = {"Origin": "https://higher.gs.com", "Referer": "https://higher.gs.com/",
                   "Content-Type": "application/json",
                   "x-higher-request-id": str(uuid.uuid4()), "x-higher-session-id": str(uuid.uuid4())}
        jobs, seen_total = [], None
        for page in range(self.max_pages):
            body = {"operationName": "GetRoles", "query": QUERY, "variables": {"searchQueryInput": {
                "page": {"pageSize": size, "pageNumber": page},
                "sort": {"sortStrategy": "RELEVANCE", "sortOrder": "DESC"},
                "filters": filters, "experiences": ["EARLY_CAREER", "PROFESSIONAL"], "searchTerm": ""}}}
            data = self.http.post(URL, json=body, headers=headers).json()
            if data.get("errors"):
                raise RuntimeError(f"goldman graphql error: {data['errors'][0].get('message')}")
            rs = (data.get("data") or {}).get("roleSearch") or {}
            items = rs.get("items") or []
            seen_total = rs.get("totalCount", seen_total)
            for r in items:
                rid, title = r.get("roleId"), r.get("jobTitle")
                if not rid or not title:
                    continue
                locs = [", ".join(p for p in (l.get("city"), l.get("state"), l.get("country")) if p)
                        for l in sorted(r.get("locations") or [], key=lambda l: not l.get("primary"))]
                level = r.get("corporateTitle") or ""
                jobs.append(Job(
                    company=self.company,
                    title=title.strip(),
                    location="; ".join(dict.fromkeys(l for l in locs if l)),
                    url=f"https://higher.gs.com/roles/{str(rid).split('_')[0]}",  # numeric id; suffixed form 404s
                    description=f"Corporate title: {level}. Division: {r.get('division') or ''}. "
                                f"Skills: {', '.join(r.get('skills') or [])}",
                    external_id=str(rid),
                ))
            if len(items) < size or (seen_total is not None and (page + 1) * size >= seen_total):
                break
        return self.dedupe(jobs)
