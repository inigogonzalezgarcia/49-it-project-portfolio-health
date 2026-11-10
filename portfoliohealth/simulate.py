"""Fictional demo: Fabrikam Insurance, a made-up insurer with three IT programmes (Claims Transformation, Digital Distribution and Core
IT & Infrastructure) and 18 projects, waterfall, agile and one SAFe Agile Release Train per business programme. The check runs on
Tuesday 10 November 2026, a week before the steering committee of 17 November. Every person, project, ticket and number is made up.
The problems are placed on purpose among projects that are on track."""
from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

ORG = "Fabrikam Insurance"
SEED = 49
AS_OF = date(2026, 11, 10)

SETTINGS = {
    "organisation": ORG,
    "as_of": "2026-11-10 09:00",
    "steerco_date": "2026-11-17",
    "currency": "EUR",
    "portfolio_envelope": 0,                 # set in write(): the approved envelope for the projects in this portfolio
    "envelope_red_pct": 5,
    "schedule_slip_pct": {"amber": 10, "red": 20},
    "milestone_late_days": {"amber": 14, "red": 30},
    "cost_variance_pct": {"amber": 5, "red": 10},
    "cpi": {"amber": 0.95, "red": 0.85},
    "spi": {"amber": 0.95, "red": 0.85},
    "evm_min_progress": 0.1,
    "burn_tolerance_pct": 15,
    "stale_status_days": 21,
    "over_allocation_pct": 100,
    "over_allocation_red_pct": 150,
    "key_person_critical_projects": 2,
    "critical_priority": 1,
    "stop_priority": 3,
    "resource_months": 3,
    "velocity_drop_pct": {"amber": 15, "red": 30},
    "velocity_window": 3,
    "scope_growth_pct": {"amber": 20, "red": 35},
    "cab_working_days": 5,
    "freeze_windows": [{"name": "Year-end change freeze", "start": "2026-12-14", "end": "2027-01-08"}],
    "holidays": ["2026-12-08", "2026-12-25", "2027-01-01", "2027-01-06"],
    "action_working_days": {"red": 4, "amber": 10},
    "owners": {"pmo": "Portfolio office (Rachel Moss)", "resources": "Resource manager (Victor Hale)",
               "change": "Change manager (Irene Pastor)", "architecture": "Head of architecture (Marta Silva)",
               "finance": "IT finance (George Adeyemi)"},
}

CLM, DIG, CIT = "Claims Transformation", "Digital Distribution", "Core IT & Infrastructure"
SPONSOR = {CLM: "Helen Ashworth", DIG: "Tomás Arenas", CIT: "Priya Raman"}
# id, name, programme, PM, methodology, phase, start, planned end, forecast end, budget, SPI, CPI, forecast factor, annual benefit,
# benefit owner, priority, RAG reported by the PM, last status update
PROJECTS = [
    ("P-101", "Claims platform replacement", CLM, "Rafael Ortiz", "SAFe ART", "Build (PI 26.4)", "2025-09-01", "2027-06-30", "2027-06-30",
     4_800_000, 0.97, 0.97, 1.02, 1_900_000, "Laura Medina", 1, "GREEN", "2026-11-06"),
    ("P-102", "Fraud analytics models", CLM, "Chen Wei", "Agile", "Build", "2026-03-02", "2027-02-26", "2027-02-26",
     650_000, 1.00, 0.98, 1.00, 800_000, "Laura Medina", 2, "GREEN", "2026-11-05"),
    ("P-103", "Claims telephony to Teams Phone", CLM, "Oliver Grant", "Waterfall", "Build", "2026-05-04", "2026-12-18", "2027-01-15",
     420_000, 0.97, 0.97, 1.04, 120_000, "Laura Medina", 2, "AMBER", "2026-11-03"),
    ("P-104", "Claims document capture", CLM, "Daniel Ross", "Waterfall", "Build", "2026-02-02", "2027-03-31", "2027-03-31",
     1_200_000, 0.90, 0.78, 1.02, 600_000, "Laura Medina", 1, "GREEN", "2026-11-04"),
    ("P-105", "Motor claims self-service", CLM, "Sofia Marín", "Agile", "Release", "2026-04-06", "2026-12-11", "2026-12-11",
     380_000, 0.98, 1.01, 0.99, 250_000, "Laura Medina", 2, "GREEN", "2026-11-06"),
    ("P-106", "Policy administration automation (RPA)", CLM, "Oliver Grant", "Waterfall", "Build", "2026-06-01", "2027-01-29", "2027-01-29",
     310_000, 0.97, 0.99, 1.00, 450_000, "", 2, "GREEN", "2026-11-02"),
    ("P-201", "Broker portal", DIG, "Mark Ellis", "SAFe ART", "Build (PI 26.4)", "2026-01-12", "2027-03-26", "2027-05-28",
     2_100_000, None, 0.92, 1.08, 1_200_000, "Inês Duarte", 1, "AMBER", "2026-11-06"),
    ("P-202", "Customer app 3.0", DIG, "Hannah Kowalski", "Agile", "Build", "2026-02-02", "2027-01-29", "2027-01-29",
     900_000, 0.99, 0.97, 1.02, 700_000, "Inês Duarte", 2, "GREEN", "2026-11-05"),
    ("P-203", "Home insurance quote and buy", DIG, "Samir Haddad", "Agile", "Build", "2026-04-13", "2027-02-26", "2027-02-26",
     1_400_000, 0.96, 0.96, 1.03, 1_100_000, "Inês Duarte", 1, "GREEN", "2026-11-06"),
    ("P-204", "CRM consolidation on Dynamics 365", DIG, "Lucy Brennan", "Waterfall", "Test", "2025-11-03", "2026-12-18", "2027-02-12",
     1_600_000, 0.90, 0.94, 1.07, 500_000, "Inês Duarte", 2, "AMBER", "2026-11-02"),
    ("P-205", "E-signature for policies", DIG, "Samir Haddad", "Waterfall", "Deploy", "2026-06-15", "2026-11-27", "2026-11-27",
     240_000, 0.97, 1.00, 1.00, 180_000, "Inês Duarte", 2, "AMBER", "2026-11-06"),
    ("P-206", "Marketing website CMS move", DIG, "Lucy Brennan", "Agile", "Build", "2026-07-06", "2027-01-15", "2027-01-15",
     280_000, 0.98, 0.99, 1.00, 90_000, "Inês Duarte", 3, "GREEN", "2026-11-05"),
    ("P-301", "Data centre exit to Azure", CIT, "Grace Liu", "Waterfall", "Migrate (wave 4 of 6)", "2025-10-06", "2027-03-31", "2027-03-31",
     3_900_000, 0.96, 0.97, 1.03, 1_400_000, "Alan Pierce", 1, "GREEN", "2026-11-05"),
    ("P-302", "Data platform migration", CIT, "Chen Wei", "Agile", "Build", "2026-05-04", "2027-04-30", "2027-04-30",
     1_100_000, 0.97, 0.98, 1.00, 400_000, "Alan Pierce", 2, "GREEN", "2026-11-04"),
    ("P-303", "Identity modernisation (Entra ID)", CIT, "Grace Liu", "Waterfall", "Build", "2026-04-01", "2027-02-26", "2027-02-26",
     760_000, 0.98, 0.97, 1.01, 150_000, "Alan Pierce", 2, "GREEN", "2026-11-05"),
    ("P-304", "Network refresh wave 3", CIT, "Tom Fischer", "Waterfall", "Deploy", "2026-03-02", "2027-01-29", "2027-01-29",
     1_300_000, 0.97, 0.99, 1.00, 0, "", 2, "GREEN", "2026-11-04"),
    ("P-305", "Windows 11 and Intune rollout", CIT, "Nadia Petrova", "Waterfall", "Deploy", "2026-01-12", "2026-12-18", "2026-12-18",
     850_000, 0.98, 1.00, 1.00, 120_000, "Alan Pierce", 2, "GREEN", "2026-10-06"),
    ("P-306", "Intranet redesign", CIT, "Nadia Petrova", "Waterfall", "Build", "2026-02-02", "2026-10-30", "2027-01-29",
     520_000, 0.75, 0.82, 1.25, 60_000, "Maria Lopes", 3, "RED", "2026-11-04"),
]
VELOCITY = {"P-101": 120, "P-102": 30, "P-105": 25, "P-202": 40, "P-203": 45, "P-206": 20, "P-302": 30}
BROKER = {"total": 1050, "done": 420, "completed": [44, 42, 45, 31, 29, 27], "added": [40, 45, 50, 55, 55, 55]}

# person, role, team, {project: allocation %} for Nov 2026 to Jan 2027 (an empty person is a role nobody fills yet)
PEOPLE = [
    ("Marek Novak", "Enterprise Architect", "Architecture", {"P-101": 60, "P-104": 60, "P-201": 60}),
    ("Rafael Ortiz", "Release Train Engineer", "Claims ART", {"P-101": 100}),
    ("Mark Ellis", "Release Train Engineer", "Distribution ART", {"P-201": 100}),
    ("Chen Wei", "Project Manager", "PMO", {"P-102": 50, "P-302": 50}),
    ("Oliver Grant", "Project Manager", "PMO", {"P-103": 50, "P-106": 40}),
    ("Daniel Ross", "Project Manager", "PMO", {"P-104": 100}),
    ("Sofia Marín", "Product Owner", "Claims ART", {"P-105": 80}),
    ("Hannah Kowalski", "Product Owner", "Digital", {"P-202": 100}),
    ("Samir Haddad", "Project Manager", "PMO", {"P-203": 60, "P-205": 40}),
    ("Lucy Brennan", "Project Manager", "PMO", {"P-204": 70, "P-206": 30}),
    ("Grace Liu", "Project Manager", "PMO", {"P-301": 60, "P-303": 40}),
    ("Tom Fischer", "Project Manager", "Infrastructure", {"P-304": 80}),
    ("Nadia Petrova", "Project Manager", "PMO", {"P-305": 50, "P-306": 50}),
    ("Elif Demir", "Solution Architect", "Architecture", {"P-301": 50, "P-302": 30, "P-303": 20}),
    ("Jonas Berg", "Business Analyst", "Business Analysis", {"P-102": 40, "P-105": 40, "P-106": 20}),
    ("Aoife Byrne", "Test Manager", "Quality Engineering", {"P-104": 50, "P-204": 50}),
    ("Pedro Alves", "Security Architect", "Security", {"P-303": 40, "P-301": 30}),
]
MONTHS = ["2026-11", "2026-12", "2027-01"]
VACANT = [("", "Cloud Engineer", "Cloud Platform", "P-302", ["2026-12", "2027-01"], 100)]

RELEASES = [
    ["P-105", "Motor claims self-service R2", "2026-11-12", "CHG-30398", "Approved"],
    ["P-205", "E-signature go-live", "2026-11-13", "CHG-30412", "Pending"],
    ["P-202", "Customer app 3.0 beta", "2026-11-26", "CHG-30420", "Pending"],
    ["P-203", "Home quote and buy MVP", "2026-12-03", "CHG-30431", "Approved"],
    ["P-304", "Wave 3 core switch cutover", "2026-12-17", "CHG-30455", "Approved"],
    ["P-305", "Windows 11 final ring", "2026-12-02", "CHG-30447", "Approved"],
    ["P-301", "Wave 5 migration", "2027-01-20", "", "Not raised"],
]
WATERFALL_MS = [("Design approved (G2)", 0.25, True), ("Build complete", 0.6, False), ("UAT complete", 0.8, False), ("Go-live (G4)", 1.0, True)]
AGILE_MS = [("Discovery complete (G1)", 0.1, True), ("MVP live", 0.5, False), ("Full release (G4)", 1.0, True)]
RAID_TITLES = {
    "risk": ["Key supplier resource leaves", "Test environment not ready in time", "Data quality lower than assumed",
             "Business users not available for UAT", "Licence costs higher than the business case"],
    "issue": ["Integration defects found in SIT", "Vendor delivery slipped by one sprint"],
    "dependency": ["Network change window from the infrastructure team", "Identity platform release needed first"],
    "assumption": ["Existing interfaces stay as they are"],
}


def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _d(s: str) -> date:
    return date.fromisoformat(s)


def build(rnd: random.Random) -> dict:
    projects, milestones, raid, sprints = [], [], [], []
    for (pid, name, prog, pm, meth, phase, start, plan, fc, budget, spi, cpi, eacf, benefit, bown, prio, rag, upd) in PROJECTS:
        s0, e0, f0 = _d(start), _d(plan), _d(fc)
        dur = (e0 - s0).days
        elapsed = max(0.0, min(1.0, (AS_OF - s0).days / dur))
        agile = meth != "Waterfall"
        if pid == "P-201":
            total, done = BROKER["total"], BROKER["done"]
            progress = done / total
        else:
            progress = min(1.0, elapsed * spi)
            total = done = None
            if agile:
                total = round(VELOCITY[pid] * dur / 14 / 10) * 10
                done = round(total * progress)
                progress = done / total
        actual = round(budget * progress / cpi, -3)
        eac = round(budget * eacf, -3)
        projects.append([pid, name, prog, SPONSOR[prog], pm, meth, phase, start, plan, fc, budget, f"{actual:.0f}", f"{eac:.0f}",
                         "" if agile else f"{100 * progress:.0f}", "" if total is None else done, "" if total is None else total,
                         benefit or "", bown, prio, rag, upd])
        # milestones
        slip = (f0 - e0).days
        for ms, frac, gate in (AGILE_MS if agile else WATERFALL_MS):
            base = s0 + timedelta(days=round(dur * frac))
            fcst = act = appr = ""
            if pid == "P-104" and ms == "Build complete":
                base, fcst = date(2026, 10, 16), "2026-11-27"            # six weeks late while the PM reports GREEN
            elif pid == "P-103" and ms == "UAT complete":
                base = date(2026, 10, 30)                                 # passed, no actual and no forecast
            elif base < AS_OF - timedelta(days=7):
                act = (base + timedelta(days=rnd.randint(0, 6))).isoformat()
                appr = f"SteerCo {base + timedelta(days=rnd.randint(1, 9)):%Y-%m-%d}" if gate else ""
            else:
                fcst = (base + timedelta(days=round(slip * frac) + rnd.randint(0, 5))).isoformat()
            milestones.append([pid, ms, base.isoformat(), fcst, act, "Yes" if gate else "No", appr])
        # RAID log
        for k in range(rnd.randint(3, 5)):
            t = rnd.choice(["risk", "risk", "risk", "issue", "dependency", "assumption"])
            closed = rnd.random() < 0.3
            due = AS_OF + timedelta(days=rnd.randint(-60, -10) if closed else rnd.randint(7, 70))
            owner = rnd.choice([pm, pm, "Marta Silva", "Alan Pierce", "Jonas Berg"])
            raid.append([pid, f"{pid[2:]}-{k + 1:02d}", t.capitalize(), rnd.choice(RAID_TITLES[t]), "" if t == "issue" else
                         rnd.choice(["Low", "Medium"]), rnd.choice(["Low", "Medium", "High"]), owner, due.isoformat(),
                         "Closed" if closed else rnd.choice(["Open", "Mitigating", "Open"]),
                         (AS_OF - timedelta(days=rnd.randint(2, 20))).isoformat()])
        # sprints / iterations
        if agile:
            for k in range(6):
                end = date(2026, 11, 6) - timedelta(days=14 * (5 - k))
                it = f"PI 26.{3 + (k >= 4)} I{(k % 4) + 1}" if meth == "SAFe ART" else f"Sprint {20 + k}"
                if pid == "P-201":
                    comp, add = BROKER["completed"][k], BROKER["added"][k]
                    comm = comp + rnd.randint(6, 12)
                else:
                    v = VELOCITY[pid]
                    comp = round(v * rnd.uniform(0.96, 1.04))
                    comm = comp + rnd.randint(0, max(2, v // 10))
                    add = rnd.randint(0, max(1, v // 15))
                sprints.append([pid, f"{name} team", it, (end - timedelta(days=13)).isoformat(), end.isoformat(), comm, comp, add])
    # the RAID log of the telephony project: three items overdue, nobody owns them
    raid += [["P-103", "103-90", "Dependency", "SBC for Direct Routing delivered by the network team", "Medium", "Medium", "", "2026-10-23",
              "Open", "2026-09-29"],
             ["P-103", "103-91", "Issue", "Carrier has not confirmed the number porting date", "", "Low", "", "2026-10-30", "Open", "2026-10-02"],
             ["P-103", "103-92", "Risk", "Contact centre agents not trained before cutover", "Low", "High", "", "2026-11-02", "Open",
              "2026-10-05"]]
    resources = []
    for person, role, team, alloc in PEOPLE:
        for m in MONTHS:
            for pid, a in alloc.items():
                if pid == "P-105" and m > "2026-12":
                    continue
                resources.append([person, role, team, pid, m, a])
    for person, role, team, pid, months, a in VACANT:
        for m in months:
            resources.append([person, role, team, pid, m, a])
    resources.sort(key=lambda r: (r[3], r[4], r[1], r[0]))
    return {"projects": projects, "milestones": milestones, "raid": raid, "sprints": sprints, "resources": resources}


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(SEED)
    b = build(rnd)
    _w(folder / "projects.csv", ["ProjectId", "Name", "Programme", "Sponsor", "ProjectManager", "Methodology", "Phase", "Start", "PlannedEnd",
                                 "ForecastEnd", "BudgetApproved", "ActualToDate", "ForecastAtCompletion", "PercentComplete", "PointsDone",
                                 "PointsTotal", "BenefitAnnual", "BenefitOwner", "Priority", "RagReported", "LastStatusUpdate"], b["projects"])
    _w(folder / "milestones.csv", ["ProjectId", "Milestone", "BaselineDate", "ForecastDate", "ActualDate", "Gate", "GateApproval"],
       b["milestones"])
    _w(folder / "raid.csv", ["ProjectId", "Id", "Type", "Title", "Probability", "Impact", "Owner", "DueDate", "Status", "LastReviewed"],
       b["raid"])
    _w(folder / "resources.csv", ["Person", "Role", "Team", "ProjectId", "Month", "Allocation"], b["resources"])
    _w(folder / "releases.csv", ["ProjectId", "Release", "PlannedDate", "ChangeTicket", "CabStatus"], RELEASES)
    _w(folder / "sprints.csv", ["ProjectId", "Team", "Sprint", "StartDate", "EndDate", "CommittedPoints", "CompletedPoints", "AddedPoints"],
       b["sprints"])
    total = sum(float(p[12]) for p in b["projects"])
    settings = dict(SETTINGS, portfolio_envelope=int(round(total / 1.06, -4)))      # the portfolio forecasts 6 % over the envelope
    (folder / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder


__all__ = ["write", "ORG", "SETTINGS", "PROJECTS"]
