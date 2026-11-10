import csv
import hashlib
import json
import os
import tempfile
import unittest
from unittest import mock
from datetime import date, datetime
from pathlib import Path

from portfoliohealth import cli
from portfoliohealth.checks import AMBER, GREEN, RED, check_project, check_releases, check_resources, resource_load, review, summary
from portfoliohealth.model import (Allocation, Data, Milestone, Project, Raid, Release, Sprint, level, load, load_projects, load_resources,
                                   month_key, pct, settings_from_dict)

AS_OF = datetime(2026, 11, 10, 9, 0)


def write(path: Path, header: list[str], rows: list[list]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def project(pid="P-1", **kw) -> Project:
    # 1 Jan to 31 Dec 2026: on 10 Nov, 86 % of the time has elapsed
    base = dict(name="Test project", programme="Prog A", sponsor="Sam Sponsor", pm="Pat Manager", methodology="Waterfall", phase="Build",
                start=date(2026, 1, 1), planned_end=date(2026, 12, 31), forecast_end=date(2026, 12, 31), budget=1_000_000, actual=860_000,
                eac=1_000_000, pct=0.86, benefit=200_000, benefit_owner="Bea Owner", priority=2, rag="GREEN", last_update=date(2026, 11, 6))
    base.update(kw)
    return Project(pid, **base)


def data(projects=(), milestones=(), raid=None, resources=None, releases=None, sprints=None, **raw) -> Data:
    d = Data(settings_from_dict(raw), AS_OF, list(projects) or [project()], list(milestones), raid, resources, releases, sprints)
    d.sources = {"projects.csv": len(d.projects)}
    return d


def codes(h) -> dict:
    return {f.code: f.severity for f in h.findings}


class TestLoading(unittest.TestCase):
    def test_ppm_columns_percentages_levels_and_months(self):
        with tempfile.TemporaryDirectory() as t:
            pp = write(Path(t) / "p.csv", ["Project ID", "Project name", "Department", "PM", "Method", "Start date", "Baseline finish",
                                           "Expected end", "Approved budget", "Spend to date", "EAC", "% complete", "Story points done",
                                           "Story points total", "Strategic priority", "Status", "Status date"],
                       [["P-9", "Portal", "Digital", "Ann", "SAFe ART", "01/02/2026", "2026-12-31", "2027-01-31", "1.200.000,00", "€ 300,000",
                         "1,250,000", "", "210", "700", "1", "Amber", "2026-11-02T10:00:00Z"],
                        ["", "No id", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]])
            ps = load_projects(pp)
            rs = write(Path(t) / "r.csv", ["Person", "Role", "Team", "ProjectId", "2026-11", "2026-12"],
                       [["Ana", "Architect", "Arch", "P-9", "60%", "0.5"], ["TBD", "Cloud Engineer", "Cloud", "P-9", "", "100"]])
            al = load_resources(rs)
        p = ps[0]
        self.assertEqual(len(ps), 1)
        self.assertEqual((p.programme, p.methodology, p.start, p.budget, p.actual, p.eac, p.priority, p.rag),
                         ("Digital", "SAFe ART", date(2026, 2, 1), 1_200_000, 300_000, 1_250_000, 1, "AMBER"))
        self.assertAlmostEqual(p.progress, 0.3)
        self.assertEqual(p.progress_source, "story points")
        self.assertEqual((pct("45"), pct("45 %"), pct("0.45"), pct("1.0")), (0.45, 0.45, 0.45, 1.0))
        self.assertEqual((level("High"), level("M"), level("4"), level("")), (4, 3, 4, None))
        self.assertEqual((month_key("Nov 2026"), month_key("11/2026"), month_key("2026-11-15")), ("2026-11", "2026-11", "2026-11"))
        self.assertEqual([(a.person, a.month, a.allocation, a.vacant) for a in al],
                         [("Ana", "2026-11", 60, False), ("Ana", "2026-12", 50, False), ("TBD", "2026-12", 100, True)])


class TestChecks(unittest.TestCase):
    def test_a_project_on_plan_is_green(self):
        h = check_project(data(), project())
        self.assertEqual(codes(h), {})
        self.assertAlmostEqual(h.cpi, 1.0, places=2)
        self.assertAlmostEqual(h.spi, 1.0, places=1)

    def test_schedule_slip_late_milestones_no_forecast_and_gates(self):
        p = project(forecast_end=date(2027, 3, 31))                      # 90 days on a 364-day plan: 25 %
        ms = [Milestone("P-1", "Build complete", date(2026, 10, 1), date(2026, 11, 12)),
              Milestone("P-1", "UAT complete", date(2026, 10, 30)),
              Milestone("P-1", "Design (G2)", date(2026, 4, 1), None, date(2026, 4, 3), True, ""),
              Milestone("P-1", "Plan (G1)", date(2026, 2, 1), None, date(2026, 2, 1), True, "SteerCo 2026-02-03")]
        h = check_project(data(milestones=ms), p)
        c = codes(h)
        self.assertEqual((c["SCH-SLIP"], c["SCH-MILESTONE"], c["SCH-NOFORECAST"], c["SCH-GATE"]), (RED, RED, AMBER, RED))
        self.assertIn("6 weeks", next(f.detail for f in h.findings if f.code == "SCH-MILESTONE"))
        self.assertEqual(sum(f.code == "SCH-GATE" for f in h.findings), 1)

    def test_evm_light_cpi_spi_forecast_and_burn(self):
        p = project(pct=0.5, actual=640_000, eac=1_020_000)              # 50 % done, 86 % of the time, 64 % spent
        h = check_project(data(), p)
        self.assertAlmostEqual(h.cpi, 0.78, places=2)
        self.assertAlmostEqual(h.spi, 0.58, places=2)
        c = codes(h)
        self.assertEqual((c["CST-CPI"], c["CST-SPI"], c["CST-FORECAST"]), (RED, RED, RED))
        self.assertNotIn("CST-EAC", c)                                   # +2 % is under the 5 % threshold
        h = check_project(data(), project(eac=1_080_000, actual=990_000, pct=0.86))
        self.assertEqual(codes(h)["CST-EAC"], AMBER)
        h = check_project(data(), project(pct=0.3, actual=500_000, start=date(2026, 9, 1), planned_end=date(2027, 8, 31),
                                          forecast_end=date(2027, 8, 31)))
        self.assertIn("CST-BURN", codes(h))                              # 50 % spent, 19 % of the time
        self.assertIsNone(check_project(data(), project(pct=0.05, actual=50_000)).cpi)   # too early to judge

    def test_stale_status_and_raid_overdue_unowned(self):
        raid = [Raid("P-1", "R1", "risk", "Vendor late", 4, 4, "", date(2026, 10, 20), "Open"),
                Raid("P-1", "R2", "issue", "Defects", None, 2, "Pat", date(2026, 11, 1), "Open"),
                Raid("P-1", "R3", "risk", "Old", 2, 2, "", date(2026, 9, 1), "Closed"),
                Raid("P-1", "R4", "assumption", "Interfaces", 2, 2, "", date(2026, 12, 1), "Open")]
        h = check_project(data(raid=raid), project(last_update=date(2026, 10, 6)))
        c = codes(h)
        self.assertEqual((c["GOV-STALE"], c["RAID-OVERDUE"], c["RAID-UNOWNED"]), (AMBER, RED, RED))
        self.assertEqual((h.raid_open, h.raid_overdue), (3, 2))
        self.assertIn("35 days ago", next(f.detail for f in h.findings if f.code == "GOV-STALE"))
        self.assertEqual(codes(check_project(data(raid=raid[1:]), project())), {"RAID-OVERDUE": AMBER, "RAID-UNOWNED": AMBER})

    def test_agile_velocity_and_scope_growth(self):
        p = project(methodology="SAFe ART", pct=None, points_done=420, points_total=1050)
        comp, added = [44, 42, 45, 31, 29, 27], [40, 45, 50, 55, 55, 55]
        sp = [Sprint("P-1", "T", f"S{k}", None, date(2026, 8, 14 + 14 * k) if k < 2 else date(2026, 9, 11 + 14 * (k - 2)) if k < 4
                     else date(2026, 10, 9 + 14 * (k - 4)), comp[k] + 5, comp[k], added[k]) for k in range(6)]
        h = check_project(data(sprints=sp), p)
        self.assertEqual((codes(h)["AGL-VELOCITY"], codes(h)["AGL-SCOPE"]), (RED, RED))
        self.assertAlmostEqual(h.scope_growth, 40.0)
        self.assertLess(h.velocity_change, -30)
        flat = [Sprint("P-1", "T", f"S{k}", None, s.end, 40, 40, 2) for k, s in enumerate(sp)]
        self.assertEqual(codes(check_project(data(sprints=flat), project(methodology="Agile", pct=None, points_done=600,
                                                                         points_total=700))), {})
        self.assertEqual(codes(check_project(data(sprints=sp), project())), {})       # waterfall: no agile checks

    def test_resources_over_allocation_key_person_and_unstaffed(self):
        ps = [project("P-1", priority=1), project("P-2", priority=1), project("P-3", priority=1), project("P-4", priority=3)]
        res = [Allocation("Marek", "Enterprise Architect", "Arch", x, m, 60) for x in ("P-1", "P-2", "P-3") for m in ("2026-11", "2026-12")]
        res += [Allocation("Ana", "Analyst", "BA", "P-4", "2026-11", 100), Allocation("Ana", "Analyst", "BA", "P-1", "2026-10", 80),
                Allocation("", "Cloud Engineer", "Cloud", "P-4", "2026-12", 100)]
        d = data(projects=ps, resources=res)
        load = resource_load(d)
        self.assertEqual({(r["person"], r["month"]): r["total"] for r in load},
                         {("Ana", "2026-11"): 100, ("Marek", "2026-11"): 180, ("Marek", "2026-12"): 180})    # October is history
        fs = {f.code: f for f in check_resources(d, load)}
        self.assertEqual((fs["RES-OVER"].severity, fs["RES-OVER"].projects), (RED, ["P-1", "P-2", "P-3"]))
        self.assertEqual(fs["RES-KEYPERSON"].projects, ["P-1", "P-2", "P-3"])
        self.assertIn("Cloud Engineer", fs["RES-UNSTAFFED"].detail)
        rv = review(d)
        by = {h.project.id: h for h in rv["health"]}
        self.assertEqual((by["P-1"].status, by["P-1"].dims["resources"]), (AMBER, AMBER))    # a person's problem is AMBER for a project

    def test_releases_in_a_freeze_and_cab_not_approved(self):
        rel = [Release("P-1", "Go-live", date(2026, 11, 13), "CHG-1", "Pending"),
               Release("P-1", "Cutover", date(2026, 12, 17), "CHG-2", "Approved"),
               Release("P-1", "Later", date(2026, 11, 30), "", "Not raised"),
               Release("P-1", "Soon, approved", date(2026, 11, 12), "CHG-3", "Approved")]
        d = data(releases=rel, freeze_windows=[{"name": "Year-end change freeze", "start": "2026-12-14", "end": "2027-01-08"}])
        fs = check_releases(d)
        self.assertEqual([(f.code, f.severity) for f in fs], [("DLV-CAB", RED), ("DLV-FREEZE", AMBER)])
        self.assertIn("3 working days", fs[0].detail)
        rv = review(d)
        cab = next(f for f in rv["findings"] if f.code == "DLV-CAB")
        self.assertEqual(cab.due, date(2026, 11, 12))                     # the working day before the go-live

    def test_watermelon_stop_candidate_benefit_owner_and_envelope(self):
        ps = [project("P-1", pct=0.5, actual=640_000, rag="GREEN", priority=1),
              project("P-2", forecast_end=date(2027, 4, 30), eac=1_300_000, rag="RED", priority=3, benefit=60_000),
              project("P-3", benefit_owner="", rag="GREEN")]
        rv = review(data(projects=ps, portfolio_envelope=3_000_000))
        by = {h.project.id: h for h in rv["health"]}
        self.assertTrue(by["P-1"].watermelon)
        self.assertEqual(by["P-1"].status, RED)
        self.assertFalse(by["P-2"].watermelon)                            # reported RED honestly
        self.assertIn("VAL-STOP", codes(by["P-2"]))
        self.assertEqual((by["P-3"].status, codes(by["P-3"])), (AMBER, {"VAL-NOOWNER": AMBER}))
        env = next(f for f in rv["findings"] if f.code == "PRT-ENVELOPE")
        self.assertEqual(env.severity, RED)                               # 3.30M against 3.00M: +10 %
        kinds = [x.kind for x in rv["decisions"]]
        self.assertEqual(kinds, ["funding", "stop", "watermelon", "benefit"])
        self.assertEqual(rv["decisions"][0].id, "D-01")

    def test_programme_and_portfolio_rag(self):
        ps = [project("A1", programme="A", priority=1, pct=0.5, actual=640_000), project("A2", programme="A"), project("A3", programme="A"),
              project("B1", programme="B", priority=2, forecast_end=date(2027, 4, 30)), project("B2", programme="B"),
              project("B3", programme="B"), project("B4", programme="B"), project("C1", programme="C")]
        rv = review(data(projects=ps))
        st = {x["programme"]: x["status"] for x in rv["programmes"]}
        self.assertEqual(st, {"A": RED, "B": AMBER, "C": GREEN})           # a critical project RED makes the programme RED
        self.assertEqual(rv["status"], RED)
        rv = review(data(projects=[project("C1", programme="C")]))
        self.assertEqual(rv["status"], GREEN)


class TestEndToEnd(unittest.TestCase):
    def test_demo_end_to_end_is_deterministic(self):
        with tempfile.TemporaryDirectory() as t:
            hashes = []
            for k in range(2):
                out = Path(t) / f"out{k}"
                self.assertEqual(cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)]), 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                h = {n: hashlib.sha1((out / n).read_bytes()).hexdigest() for n in cli.OUTPUTS}
                h.update({n.name: hashlib.sha1(n.read_bytes()).hexdigest() for n in (Path(t) / f"data{k}").iterdir()})
                hashes.append(h)
            self.assertEqual(hashes[0], hashes[1])
            self.assertEqual(json.loads((Path(t) / "data0" / "settings.json").read_text(encoding="utf-8"))["as_of"], "2026-11-10 09:00")
            self.assertLess(sum(p.stat().st_size for p in (Path(t) / "data0").iterdir()), 200_000)
            d = load(Path(t) / "data0")
        rv = review(d)
        by = {h.project.id: h for h in rv["health"]}
        self.assertEqual(len(by), 18)
        self.assertEqual({h.project.methodology for h in rv["health"]}, {"Waterfall", "Agile", "SAFe ART"})
        wm = by["P-104"]
        self.assertTrue(wm.watermelon)
        self.assertEqual((wm.project.rag, round(wm.cpi, 2)), ("GREEN", 0.78))
        self.assertIn("6 weeks late", wm.reason)
        planted = {"P-305": "GOV-STALE", "P-304": "DLV-FREEZE", "P-205": "DLV-CAB", "P-106": "VAL-NOOWNER", "P-306": "VAL-STOP",
                   "P-201": "AGL-SCOPE", "P-103": "RAID-UNOWNED", "P-302": "RES-UNSTAFFED"}
        for pid, code in planted.items():
            self.assertIn(code, codes(by[pid]), pid)
        self.assertEqual(round(by["P-201"].scope_growth), 40)
        self.assertLess(by["P-201"].velocity_change, 0)
        self.assertIn("3 working days", next(f.detail for f in by["P-205"].findings if f.code == "DLV-CAB"))
        over = next(f for f in rv["findings"] if f.code == "RES-OVER")
        self.assertIn("Marek Novak", over.subject)
        self.assertIn("180 %", over.detail)
        self.assertEqual(round(rv["over_pct"]), 6)
        sm = summary(d, rv)
        self.assertEqual((sm["overall"], sm["status"][RED], sm["status"][AMBER], sm["status"][GREEN], sm["watermelons"]), (RED, 5, 6, 7, 1))

    def test_pack_and_csv_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["demo", "--data", str(Path(t) / "d"), "--out", str(Path(t) / "o")]), 0)
            o = Path(t) / "o"
            pack = (o / "steerco-pack.md").read_text(encoding="utf-8")
            html = (o / "report.html").read_text(encoding="utf-8")
            ph, fd, ld, dc, ac = (rows(o / n) for n in ("project-health.csv", "findings.csv", "resource-load.csv", "decisions.csv",
                                                        "actions.csv"))
        for h in ("## Headlines", "## Decisions needed", "## Red and amber projects", "## Portfolio", "## Before the meeting",
                  "## Scope and evidence", "## Minutes"):
            self.assertIn(h, pack)
        self.assertIn("+6.0 %", pack)
        self.assertNotIn("\r", pack)
        self.assertEqual(len(ph), 18)
        self.assertEqual([r["project_id"] for r in ph if r["watermelon"] == "yes"], ["P-104"])
        self.assertEqual(fd[0]["severity"], RED)
        self.assertTrue(any(r["person"] == "Marek Novak" and r["allocation_pct"] == "180" and r["over"] == "yes" for r in ld))
        self.assertTrue(dc and all(r["needed_by"] == "2026-11-17" and r["outcome"] == "" for r in dc))
        self.assertTrue(all(a["done"] == "" and a["owner"] and a["due"] for a in ac))
        self.assertEqual(len({a["ref"] for a in ac}), len(ac))
        for part in ("Heat map", "<svg", "Resource load", "WATERMELON"):
            self.assertIn(part, html)

    def test_review_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)                       # no projects.csv
            self.assertEqual(cli.main(["review", "--out", str(Path(t) / "o")]), 2)
            self.assertEqual(cli.main(["review", str(Path(t) / "nope"), "--out", str(Path(t) / "o")]), 2)
            write(Path(t) / "projects.csv", ["ProjectId", "Name", "Start", "PlannedEnd", "BudgetApproved", "ActualToDate", "PercentComplete",
                                             "RagReported", "LastStatusUpdate"],
                  [["P-1", "Only one", "2026-01-01", "2026-12-31", "100000", "86000", "86", "Green", "2026-11-06"]])
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o"), "--as-of", "2026-11-10"]), 0)
            ph = rows(Path(t) / "o" / "project-health.csv")
        self.assertEqual((ph[0]["rag_computed"], ph[0]["cpi"]), (GREEN, "1.00"))


def _exporter():
    import importlib.util
    spec = importlib.util.spec_from_file_location("export_agile", Path(__file__).resolve().parents[1] / "scripts" / "export_agile.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestExporter(unittest.TestCase):
    def test_jira_and_azure_devops_exports_read_only_with_paging(self):
        m = _exporter()
        calls = []

        def fake(url, auth, body=None):
            calls.append(("POST" if body is not None else "GET", url.split("?")[0], body))
            if "/rest/agile/1.0/board/42/sprint" in url:
                if "startAt=0" in url:
                    return {"values": [{"id": 7, "name": "Sprint 7", "startDate": "2026-10-12T08:00:00.000Z",
                                        "endDate": "2026-10-23T17:00:00.000Z", "completeDate": "2026-10-23T17:30:00.000+0000"}], "isLast": False}
                return {"values": [{"id": 6, "name": "Sprint 6", "startDate": "2026-09-28T08:00:00.000Z",
                                    "completeDate": "2026-10-09T17:00:00.000Z"}], "isLast": True}
            if url.endswith("/rest/api/3/search/jql"):
                done = {"status": {"statusCategory": {"key": "done"}}}
                issues = [{"fields": {"customfield_10016": 5, "created": "2026-09-01T10:00:00.000+0200",
                                      "resolutiondate": "2026-10-20T10:00:00.000+0200", **done}},
                          {"fields": {"customfield_10016": 3, "created": "2026-10-14T10:00:00.000+0200", "resolutiondate": None,
                                      "status": {"statusCategory": {"key": "indeterminate"}}}}]
                if "nextPageToken" not in body:
                    return {"issues": issues[:1], "nextPageToken": "abc", "isLast": False}
                return {"issues": issues[1:], "isLast": True}
            if "teamsettings/iterations" in url:
                return {"value": [{"name": "Sprint 20", "path": "Broker Portal\\Sprint 20", "attributes": {
                    "startDate": "2026-10-12T00:00:00Z", "finishDate": "2026-10-23T00:00:00Z", "timeFrame": "past"}},
                    {"name": "Sprint 21", "path": "Broker Portal\\Sprint 21", "attributes": {"timeFrame": "current"}}]}
            if "/_apis/wit/wiql" in url:
                return {"workItems": [{"id": 1}, {"id": 2}]}
            if "/_apis/wit/workitems" in url:
                return {"value": [{"fields": {"System.State": "Closed", "System.CreatedDate": "2026-10-01T09:00:00.1234567Z",
                                              "Microsoft.VSTS.Common.ClosedDate": "2026-10-23T15:00:00Z",
                                              "Microsoft.VSTS.Scheduling.StoryPoints": 8}},
                                  {"fields": {"System.State": "Active", "System.CreatedDate": "2026-10-15T09:00:00Z",
                                              "Microsoft.VSTS.Scheduling.StoryPoints": 2}}]}
            raise AssertionError(url)

        m._request = fake
        env = {"JIRA_EMAIL": "pmo@contoso.example", "JIRA_API_TOKEN": "x", "AZURE_DEVOPS_PAT": "y"}
        with mock.patch.dict(os.environ, env), tempfile.TemporaryDirectory() as t:
            out = Path(t) / "sprints.csv"
            self.assertEqual(m.main(["jira", "--site", "https://contoso.atlassian.net", "--board", "42", "--project-id", "P-201",
                                     "--out", str(out)]), 0)
            self.assertEqual(m.main(["ado", "--org", "fabrikam", "--project", "Broker Portal", "--team", "Broker Portal Team",
                                     "--project-id", "P-202", "--out", str(out), "--append"]), 0)
            got = rows(out)
            self.assertNotIn("x", out.read_text(encoding="utf-8").split(","))
        self.assertEqual([(r["ProjectId"], r["Sprint"], r["CommittedPoints"], r["CompletedPoints"], r["AddedPoints"]) for r in got],
                         [("P-201", "Sprint 6", "8", "0", "3"), ("P-201", "Sprint 7", "8", "5", "3"), ("P-202", "Sprint 20", "10", "8", "2")])
        self.assertTrue(all(method == "GET" or u.endswith(("/search/jql", "/_apis/wit/wiql")) for method, u, _ in calls))
        self.assertEqual(m.summarise([{"points": 5, "done": True, "created": None, "resolved": None}], None, None), (5.0, 5.0, 0.0))


if __name__ == "__main__":
    unittest.main()
