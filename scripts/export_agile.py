#!/usr/bin/env python3
"""Read-only export of the sprint history of one agile project into sprints.csv, from Jira Cloud or Azure DevOps.

Only read requests: GET calls, plus the POST that Jira's issue search and Azure DevOps' WIQL query use to send the query (they read,
they change nothing). The token is read from an environment variable or typed in when asked; it is kept in memory and never written
to disk or printed.

Jira Cloud (Jira Software, a Scrum board)
  - GET  /rest/agile/1.0/board/{boardId}/sprint?state=closed     the closed sprints of the board (paged with startAt / isLast)
  - POST /rest/api/3/search/jql  {"jql": "sprint = {id}", ...}   the issues of each sprint (paged with nextPageToken)
  Sign-in: your Atlassian account e-mail and an API token (id.atlassian.com > Security > API tokens), as basic authentication.
  Environment: JIRA_EMAIL and JIRA_API_TOKEN. The story points field is a custom field whose id differs per site
  (Story point estimate or Story Points, for example customfield_10016): pass it with --points-field.

Azure DevOps Services
  - GET  {org}/{project}/{team}/_apis/work/teamsettings/iterations?api-version=7.1   the team's iterations (timeFrame past)
  - POST {org}/{project}/_apis/wit/wiql?api-version=7.1                             the work item ids of each iteration
  - GET  {org}/{project}/_apis/wit/workitems?ids=...&fields=...&api-version=7.1    the fields, 200 ids at a time
  Sign-in: a personal access token with the Work Items (Read) scope, as basic authentication with an empty user name.
  Environment: AZURE_DEVOPS_PAT. Story points are Microsoft.VSTS.Scheduling.StoryPoints (Agile process); with the Scrum process
  use --points-field Microsoft.VSTS.Scheduling.Effort.

Per sprint it writes the points committed (every item in the sprint at export time), completed (done and closed by the sprint end)
and added (items created after the sprint started). This is an approximation of the sprint report: items moved out of a sprint
after it closed are not seen.

Examples
  python scripts/export_agile.py jira --site https://contoso.atlassian.net --board 42 --project-id P-201 \\
      --points-field customfield_10016 --out data/sprints.csv
  python scripts/export_agile.py ado --org fabrikam --project "Broker Portal" --team "Broker Portal Team" --project-id P-201 \\
      --out data/sprints.csv --append
"""
from __future__ import annotations

import argparse
import base64
import csv
import getpass
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HEADER = ["ProjectId", "Team", "Sprint", "StartDate", "EndDate", "CommittedPoints", "CompletedPoints", "AddedPoints"]


TS = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


def _dt(v: str | None) -> datetime | None:
    """Jira (2026-10-23T09:12:45.123+0200) and Azure DevOps (2026-10-23T09:12:45.1234567Z) timestamps, as naive UTC."""
    m = TS.match(str(v or "").strip())
    if not m:
        return None
    t = m.group(2) or "00:00:00"
    d = datetime.fromisoformat(f"{m.group(1)}T{t if t.count(':') == 2 else t + ':00'}")
    tz = m.group(3)
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        d -= sign * timedelta(hours=int(tz[1:3]), minutes=int(tz[-2:]))
    return d


def summarise(items: list[dict], start: datetime | None, end: datetime | None) -> tuple[float, float, float]:
    """Committed, completed and added points of one sprint. Each item: points, done (bool), created, resolved (datetimes or None)."""
    committed = completed = added = 0.0
    for it in items:
        pts = float(it.get("points") or 0)
        committed += pts
        res = it.get("resolved")
        if it.get("done") and (end is None or res is None or res <= end):
            completed += pts
        if start and it.get("created") and it["created"] > start:
            added += pts
    return committed, completed, added


def _request(url: str, auth: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Authorization": f"Basic {auth}", "Accept": "application/json", "Content-Type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 4:
                time.sleep(int(exc.headers.get("Retry-After") or 5))
                continue
            raise SystemExit(f"error: HTTP {exc.code} from {url.split('?')[0]}: {exc.reason}")
    raise SystemExit("error: too many retries")


def _basic(user: str, secret: str) -> str:
    return base64.b64encode(f"{user}:{secret}".encode()).decode()


# ---------------------------------------------------------------- Jira Cloud

def jira(a) -> list[list]:
    email = os.environ.get("JIRA_EMAIL") or input("Atlassian account e-mail: ").strip()
    token = os.environ.get("JIRA_API_TOKEN") or getpass.getpass("Jira API token (not echoed): ")
    auth = _basic(email, token)
    site = a.site.rstrip("/")
    sprints, start_at = [], 0
    while True:
        page = _request(f"{site}/rest/agile/1.0/board/{a.board}/sprint?state=closed&startAt={start_at}&maxResults=50", auth)
        sprints += page.get("values", [])
        if page.get("isLast", True) or not page.get("values"):
            break
        start_at += len(page["values"])
    sprints = sorted(sprints, key=lambda s: s.get("completeDate") or s.get("endDate") or "")[-a.sprints:]
    out = []
    for sp in sprints:
        items, token_ = [], None
        while True:
            body = {"jql": f"sprint = {sp['id']}", "fields": [a.points_field, "status", "created", "resolutiondate"], "maxResults": 100}
            if token_:
                body["nextPageToken"] = token_
            page = _request(f"{site}/rest/api/3/search/jql", auth, body)
            for issue in page.get("issues", []):
                f = issue.get("fields", {})
                items.append({"points": f.get(a.points_field) or 0,
                              "done": ((f.get("status") or {}).get("statusCategory") or {}).get("key") == "done",
                              "created": _dt(f.get("created")), "resolved": _dt(f.get("resolutiondate"))})
            token_ = page.get("nextPageToken")
            if not token_ or page.get("isLast"):
                break
        start, end = _dt(sp.get("startDate")), _dt(sp.get("completeDate") or sp.get("endDate"))
        c, d, ad = summarise(items, start, end)
        out.append([a.project_id, a.team or f"board {a.board}", sp.get("name", sp["id"]), start.date().isoformat() if start else "",
                    end.date().isoformat() if end else "", f"{c:g}", f"{d:g}", f"{ad:g}"])
        print(f"  {sp.get('name')}: {len(items)} issues", file=sys.stderr)
    return out


# ---------------------------------------------------------------- Azure DevOps

def ado(a) -> list[list]:
    pat = os.environ.get("AZURE_DEVOPS_PAT") or getpass.getpass("Azure DevOps PAT, Work Items (Read) (not echoed): ")
    auth = _basic("", pat)
    org = a.org if a.org.startswith("https://") else f"https://dev.azure.com/{a.org}"
    proj = urllib.parse.quote(a.project)
    team = urllib.parse.quote(a.team or f"{a.project} Team")
    its = _request(f"{org}/{proj}/{team}/_apis/work/teamsettings/iterations?api-version=7.1", auth).get("value", [])
    its = [i for i in its if (i.get("attributes") or {}).get("timeFrame") == "past"]
    its = sorted(its, key=lambda i: (i.get("attributes") or {}).get("finishDate") or "")[-a.sprints:]
    done_states = {s.strip().lower() for s in a.done_states.split(",")}
    types = ", ".join("'" + t.strip().replace("'", "''") + "'" for t in a.types.split(","))
    out = []
    for it in its:
        path = it["path"].replace("'", "''")
        q = {"query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project AND [System.IterationPath] = '{path}' "
                      f"AND [System.WorkItemType] IN ({types})"}
        ids = [w["id"] for w in _request(f"{org}/{proj}/_apis/wit/wiql?api-version=7.1", auth, q).get("workItems", [])]
        items = []
        fields = ",".join(["System.State", "System.CreatedDate", "Microsoft.VSTS.Common.ClosedDate", a.points_field])
        for k in range(0, len(ids), 200):
            chunk = ",".join(str(x) for x in ids[k:k + 200])
            for w in _request(f"{org}/{proj}/_apis/wit/workitems?ids={chunk}&fields={fields}&api-version=7.1", auth).get("value", []):
                f = w.get("fields", {})
                items.append({"points": f.get(a.points_field) or 0, "done": str(f.get("System.State", "")).lower() in done_states,
                              "created": _dt(f.get("System.CreatedDate")), "resolved": _dt(f.get("Microsoft.VSTS.Common.ClosedDate"))})
        at = it.get("attributes") or {}
        start, end = _dt(at.get("startDate")), _dt(at.get("finishDate"))
        if end:
            end = end.replace(hour=23, minute=59, second=59)
        c, d, ad = summarise(items, start, end)
        out.append([a.project_id, a.team or f"{a.project} Team", it.get("name", ""), start.date().isoformat() if start else "",
                    end.date().isoformat() if end else "", f"{c:g}", f"{d:g}", f"{ad:g}"])
        print(f"  {it.get('name')}: {len(items)} work items", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="source", required=True)
    j = sub.add_parser("jira", help="Jira Cloud (Jira Software Scrum board)")
    j.add_argument("--site", required=True, help="https://<your-site>.atlassian.net")
    j.add_argument("--board", required=True, type=int, help="board id (from the board URL)")
    j.add_argument("--points-field", default="customfield_10016", help="id of the story points field (default customfield_10016)")
    z = sub.add_parser("ado", help="Azure DevOps Services")
    z.add_argument("--org", required=True, help="organisation name or https://dev.azure.com/<org>")
    z.add_argument("--project", required=True, help="Azure DevOps project")
    z.add_argument("--points-field", default="Microsoft.VSTS.Scheduling.StoryPoints")
    z.add_argument("--types", default="User Story,Product Backlog Item,Bug", help="work item types to count")
    z.add_argument("--done-states", default="Closed,Done,Resolved", help="states that count as done")
    for x in (j, z):
        x.add_argument("--project-id", required=True, help="the ProjectId of this project in projects.csv")
        x.add_argument("--team", default="", help="team name (Azure DevOps: the team whose iterations to read)")
        x.add_argument("--sprints", type=int, default=8, help="how many of the latest closed sprints (default 8)")
        x.add_argument("--out", type=Path, default=Path("data/sprints.csv"))
        x.add_argument("--append", action="store_true", help="add to an existing sprints.csv instead of replacing it")
    a = p.parse_args(argv)
    rows = jira(a) if a.source == "jira" else ado(a)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    new = not (a.append and a.out.exists())
    with open(a.out, "a" if not new else "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        if new:
            w.writerow(HEADER)
        w.writerows(rows)
    print(f"{len(rows)} sprints written to {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
