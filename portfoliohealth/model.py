"""Loading: the project list from the PPM tool or a sheet, the milestones, the RAID log, the resource plan and, optionally, the releases
and the sprint or PI history exported from Jira or Azure DevOps. Forgiving column names, into plain dataclasses."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ALIASES = {
    "id": ["ProjectId", "Project ID", "id", "project code", "code", "key"],
    "name": ["Name", "Project", "Project name", "title"],
    "programme": ["Programme", "Program", "Department", "portfolio", "business unit"],
    "sponsor": ["Sponsor", "Executive sponsor", "business sponsor"],
    "pm": ["ProjectManager", "Project manager", "PM", "manager", "owner", "release train engineer", "rte"],
    "methodology": ["Methodology", "Method", "delivery approach", "approach", "framework"],
    "phase": ["Phase", "Gate", "Stage", "phase gate"],
    "start": ["Start", "StartDate", "Start date", "baseline start"],
    "planned_end": ["PlannedEnd", "Planned end", "baseline end", "baseline finish", "planned finish", "end date"],
    "forecast_end": ["ForecastEnd", "Forecast end", "forecast finish", "expected end", "estimated end"],
    "budget": ["BudgetApproved", "Budget approved", "budget", "approved budget", "bac"],
    "actual": ["ActualToDate", "Actual to date", "actual", "actual cost", "spend to date", "ac"],
    "eac": ["ForecastAtCompletion", "Forecast at completion", "eac", "fac", "estimate at completion", "forecast cost"],
    "pct": ["PercentComplete", "% complete", "percent complete", "pct complete", "progress"],
    "points_done": ["PointsDone", "story points done", "points done", "completed points"],
    "points_total": ["PointsTotal", "story points total", "points total", "total points", "scope points"],
    "benefit": ["BenefitAnnual", "Annual benefit", "benefit", "business case benefit", "benefits"],
    "benefit_owner": ["BenefitOwner", "Benefit owner", "benefits owner"],
    "priority": ["Priority", "Strategic priority", "strategic rank", "tier"],
    "rag": ["RagReported", "RAG", "Reported RAG", "status", "pm rag", "overall status"],
    "last_update": ["LastStatusUpdate", "Last status update", "status date", "last update", "last updated", "status updated"],
}
MILESTONE_ALIASES = {
    "project": ["ProjectId", "Project ID", "project"],
    "name": ["Milestone", "Name", "title"],
    "baseline": ["BaselineDate", "Baseline", "baseline date", "planned date"],
    "forecast": ["ForecastDate", "Forecast", "forecast date", "expected date"],
    "actual": ["ActualDate", "Actual", "actual date", "completed"],
    "gate": ["Gate", "is gate", "stage gate"],
    "approval": ["GateApproval", "Approval", "approved by", "gate approval", "approval reference"],
}
RAID_ALIASES = {
    "project": ["ProjectId", "Project ID", "project"],
    "id": ["Id", "RaidId", "Key", "reference", "ref"],
    "type": ["Type", "raid type", "category"],
    "title": ["Title", "Summary", "description"],
    "probability": ["Probability", "likelihood"],
    "impact": ["Impact", "severity"],
    "owner": ["Owner", "Assignee", "action owner"],
    "due": ["DueDate", "Due date", "due", "target date"],
    "status": ["Status", "state"],
    "last_reviewed": ["LastReviewed", "Last reviewed", "reviewed", "updated"],
}
RESOURCE_ALIASES = {
    "person": ["Person", "Name", "Resource", "assignee", "employee"],
    "role": ["Role", "skill", "position"],
    "team": ["Team", "Department", "resource pool", "line"],
    "project": ["ProjectId", "Project ID", "project"],
    "month": ["Month", "period"],
    "allocation": ["Allocation", "Allocation %", "allocation pct", "percent", "fte %"],
}
RELEASE_ALIASES = {
    "project": ["ProjectId", "Project ID", "project"],
    "release": ["Release", "Name", "title", "go-live"],
    "planned": ["PlannedDate", "Planned date", "release date", "go live date", "date"],
    "change": ["ChangeTicket", "Change", "change request", "rfc", "change number"],
    "cab": ["CabStatus", "CAB status", "cab", "approval status", "change status"],
}
SPRINT_ALIASES = {
    "project": ["ProjectId", "Project ID", "project"],
    "team": ["Team", "board"],
    "sprint": ["Sprint", "Iteration", "iteration path", "pi", "name"],
    "start": ["StartDate", "Start", "start date"],
    "end": ["EndDate", "End", "end date", "finish date", "finishdate"],
    "committed": ["CommittedPoints", "Committed", "planned points", "points planned"],
    "completed": ["CompletedPoints", "Completed", "done points", "points done"],
    "added": ["AddedPoints", "Added", "scope added", "points added"],
}
YES = {"yes", "y", "true", "1", "x", "si", "gate"}
NO = {"no", "n", "false", "0", "none", "rejected", "not approved"}
CLOSED = {"closed", "done", "resolved", "mitigated", "retired", "cancelled", "canceled", "accepted", "complete", "completed"}
VACANT = {"", "tbd", "tba", "vacant", "unfilled", "open", "to hire", "unassigned", "n a", "none"}
LEVEL = {"very low": 1, "low": 2, "l": 2, "medium": 3, "med": 3, "m": 3, "high": 4, "h": 4, "very high": 5, "vh": 5, "critical": 5}
RAG_WORDS = {"green": "GREEN", "g": "GREEN", "on track": "GREEN", "amber": "AMBER", "a": "AMBER", "yellow": "AMBER", "at risk": "AMBER",
             "red": "RED", "r": "RED", "off track": "RED"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%d %b %Y", "%d-%b-%Y")
DEFAULT_OWNERS = {"pmo": "Portfolio office (PMO)", "resources": "Resource manager", "change": "Change manager",
                  "architecture": "Head of architecture", "finance": "IT finance"}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip()
    if not s or _norm(s) in {"n a", "na", "none", "null", "tbd"}:
        return None
    s = re.sub(r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})$", "", s)
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def parse_d(v) -> date | None:
    x = parse_dt(v)
    return x.date() if x else None


def num(v) -> float | None:
    s = re.sub(r"[^\d,.\-]", "", str(v or ""))
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def pct(v) -> float | None:
    """A share between 0 and 1 from '45', '45%', '45,0 %' or '0.45'."""
    raw = str(v or "").strip()
    x = num(raw)
    if x is None:
        return None
    if "%" in raw or x > 1 or (x == 1 and "." not in raw):
        x = x / 100
    return max(0.0, min(1.0, x))


def level(v) -> int | None:
    """Probability or impact on a 1-5 scale, from 1-5, 1-3 (L/M/H) or the words."""
    n = _norm(v)
    if not n:
        return None
    if n in LEVEL:
        return LEVEL[n]
    x = num(n)
    return None if x is None else max(1, min(5, int(round(x))))


def rag(v) -> str:
    return RAG_WORDS.get(_norm(v), "")


def month_key(v) -> str:
    """'2026-11', 'Nov 2026', '11/2026' or a date, as YYYY-MM."""
    s = str(v or "").strip()
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.fullmatch(r"(\d{1,2})[-/](\d{4})", s)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    for f in ("%b %Y", "%B %Y", "%b-%Y", "%b-%y"):
        try:
            return datetime.strptime(s, f).strftime("%Y-%m")
        except ValueError:
            pass
    d = parse_d(s)
    return f"{d:%Y-%m}" if d else ""


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header = fh.readline()
        fh.seek(0)
        delim = max(",;\t", key=header.count)
        reader = csv.DictReader(fh, delimiter=delim)
        return list(reader.fieldnames or []), list(reader)


def _map(fields: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    heads = {_norm(h): h for h in fields}
    cols = {}
    for k, names in aliases.items():
        for n in names + [k.replace("_", " ")]:
            if _norm(n) in heads and heads[_norm(n)] not in cols.values():
                cols[k] = heads[_norm(n)]
                break
    return cols


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    fields, raw = _read(path)
    cols = _map(fields, aliases)
    return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in raw]


def methodology(v) -> str:
    n = _norm(v)
    if "safe" in n or "art" in n.split() or "release train" in n:
        return "SAFe ART"
    if any(w in n for w in ("agile", "scrum", "kanban", "sprint")):
        return "Agile"
    if any(w in n for w in ("hybrid", "mixed")):
        return "Hybrid"
    return "Waterfall" if n else ""


def is_agile(m: str) -> bool:
    return m in ("Agile", "SAFe ART", "Hybrid")


# ---------------------------------------------------------------- working days

def is_working(d: date, holidays: set) -> bool:
    return d.weekday() < 5 and d not in holidays


def working_days(a: date, b: date, holidays: set) -> int:
    """Working days in [a, b); negative when b is before a."""
    if b < a:
        return -working_days(b, a, holidays)
    n, d = 0, a
    while d < b:
        n += is_working(d, holidays)
        d += timedelta(days=1)
    return n


def add_working(d: date, n: int, holidays: set) -> date:
    step = 1 if n >= 0 else -1
    left = abs(n)
    while left:
        d += timedelta(days=step)
        if is_working(d, holidays):
            left -= 1
    return d


# ---------------------------------------------------------------- records

@dataclass
class Project:
    id: str
    name: str
    programme: str = ""
    sponsor: str = ""
    pm: str = ""
    methodology: str = ""
    phase: str = ""
    start: date | None = None
    planned_end: date | None = None
    forecast_end: date | None = None
    budget: float | None = None
    actual: float | None = None
    eac: float | None = None
    pct: float | None = None             # 0..1, as reported
    points_done: float | None = None
    points_total: float | None = None
    benefit: float | None = None
    benefit_owner: str = ""
    priority: int = 2
    rag: str = ""                        # GREEN, AMBER, RED as the PM reported it
    last_update: date | None = None

    @property
    def progress(self) -> float | None:
        """% complete as a share: the reported value, else story points done over total."""
        if self.pct is not None:
            return self.pct
        if self.points_total:
            return max(0.0, min(1.0, (self.points_done or 0) / self.points_total))
        return None

    @property
    def progress_source(self) -> str:
        return "reported" if self.pct is not None else ("story points" if self.points_total else "")


@dataclass
class Milestone:
    project: str
    name: str
    baseline: date | None = None
    forecast: date | None = None
    actual: date | None = None
    gate: bool = False
    approval: str = ""

    @property
    def approved(self) -> bool:
        return bool(self.approval) and _norm(self.approval) not in NO


@dataclass
class Raid:
    project: str
    id: str
    type: str = "risk"
    title: str = ""
    probability: int | None = None
    impact: int | None = None
    owner: str = ""
    due: date | None = None
    status: str = ""
    last_reviewed: date | None = None

    @property
    def open(self) -> bool:
        return _norm(self.status) not in CLOSED

    @property
    def score(self) -> int:
        p = 5 if self.type == "issue" else (self.probability or 3)
        return p * (self.impact or 3)


@dataclass
class Allocation:
    person: str
    role: str
    team: str
    project: str
    month: str
    allocation: float

    @property
    def vacant(self) -> bool:
        return _norm(self.person) in VACANT


@dataclass
class Release:
    project: str
    release: str
    planned: date | None = None
    change: str = ""
    cab: str = ""

    @property
    def approved(self) -> bool:
        return _norm(self.cab) in {"approved", "authorised", "authorized", "scheduled", "implemented", "closed"}


@dataclass
class Sprint:
    project: str
    team: str
    sprint: str
    start: date | None = None
    end: date | None = None
    committed: float = 0
    completed: float = 0
    added: float = 0


@dataclass
class Settings:
    organisation: str = "IT project portfolio"
    as_of: datetime | None = None
    steerco_date: str = ""
    currency: str = "EUR"
    portfolio_envelope: float | None = None
    envelope_red_pct: float = 5.0
    schedule_slip_pct: dict = field(default_factory=lambda: {"amber": 10, "red": 20})
    milestone_late_days: dict = field(default_factory=lambda: {"amber": 14, "red": 30})
    cost_variance_pct: dict = field(default_factory=lambda: {"amber": 5, "red": 10})
    cpi: dict = field(default_factory=lambda: {"amber": 0.95, "red": 0.85})
    spi: dict = field(default_factory=lambda: {"amber": 0.95, "red": 0.85})
    evm_min_progress: float = 0.1
    burn_tolerance_pct: float = 15.0
    stale_status_days: int = 21
    over_allocation_pct: float = 100.0
    over_allocation_red_pct: float = 150.0
    key_person_critical_projects: int = 2
    critical_priority: int = 1
    stop_priority: int = 3
    resource_months: int = 3
    velocity_drop_pct: dict = field(default_factory=lambda: {"amber": 15, "red": 30})
    velocity_window: int = 3
    scope_growth_pct: dict = field(default_factory=lambda: {"amber": 20, "red": 35})
    cab_working_days: int = 5
    freeze_windows: list = field(default_factory=list)
    holidays: list = field(default_factory=list)
    action_working_days: dict = field(default_factory=lambda: {"red": 4, "amber": 10})
    owners: dict = field(default_factory=lambda: dict(DEFAULT_OWNERS))

    def owner(self, k: str) -> str:
        return self.owners.get(k) or DEFAULT_OWNERS.get(k, "Portfolio office (PMO)")

    @property
    def holiday_set(self) -> set:
        return {d for d in (parse_d(x) for x in self.holidays) if d}

    @property
    def steerco(self) -> date | None:
        return parse_d(self.steerco_date)

    @property
    def freezes(self) -> list[tuple[str, date, date]]:
        out = []
        for w in self.freeze_windows:
            a, b = parse_d(w.get("start")), parse_d(w.get("end"))
            if a and b:
                out.append((str(w.get("name") or "Change freeze"), a, b))
        return out


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k) or v is None:
            continue
        cur = getattr(s, k)
        if k == "as_of":
            s.as_of = parse_dt(v)
        elif k == "portfolio_envelope":
            s.portfolio_envelope = num(v)
        elif isinstance(cur, dict):
            cur.update({str(a): b for a, b in v.items()})
        elif isinstance(cur, list):
            setattr(s, k, list(v))
        elif isinstance(cur, bool):
            setattr(s, k, bool(v))
        elif isinstance(cur, int):
            setattr(s, k, int(num(v) or 0))
        elif isinstance(cur, float):
            setattr(s, k, float(num(v) or 0))
        else:
            setattr(s, k, str(v))
    return s


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    projects: list[Project] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    raid: list[Raid] | None = None
    resources: list[Allocation] | None = None
    releases: list[Release] | None = None
    sprints: list[Sprint] | None = None
    sources: dict = field(default_factory=dict)

    @property
    def today(self) -> date:
        return self.as_of.date()


# ---------------------------------------------------------------- loaders

def load_projects(path: Path) -> list[Project]:
    out = []
    for r in _rows(path, PROJECT_ALIASES):
        if not r.get("id"):
            continue
        pr = num(r.get("priority"))
        out.append(Project(r["id"], r.get("name", "") or r["id"], r.get("programme", ""), r.get("sponsor", ""), r.get("pm", ""),
                           methodology(r.get("methodology")), r.get("phase", ""), parse_d(r.get("start")), parse_d(r.get("planned_end")),
                           parse_d(r.get("forecast_end")), num(r.get("budget")), num(r.get("actual")), num(r.get("eac")),
                           pct(r.get("pct")), num(r.get("points_done")), num(r.get("points_total")), num(r.get("benefit")),
                           r.get("benefit_owner", ""), int(pr) if pr else 2, rag(r.get("rag")), parse_d(r.get("last_update"))))
    return sorted(out, key=lambda p: (p.programme, p.id))


def load_milestones(path: Path) -> list[Milestone]:
    return [Milestone(r["project"], r.get("name", ""), parse_d(r.get("baseline")), parse_d(r.get("forecast")), parse_d(r.get("actual")),
                      _norm(r.get("gate")) in YES, r.get("approval", "")) for r in _rows(path, MILESTONE_ALIASES) if r.get("project")]


def load_raid(path: Path) -> list[Raid]:
    out = []
    for r in _rows(path, RAID_ALIASES):
        if not r.get("project"):
            continue
        t = _norm(r.get("type")) or "risk"
        t = next((k for k in ("risk", "issue", "dependency", "assumption", "action", "decision") if t.startswith(k[:3])), t)
        out.append(Raid(r["project"], r.get("id", ""), t, r.get("title", ""), level(r.get("probability")), level(r.get("impact")),
                        "" if _norm(r.get("owner")) in VACANT else r.get("owner", ""), parse_d(r.get("due")), r.get("status", ""),
                        parse_d(r.get("last_reviewed"))))
    return out


def load_resources(path: Path) -> list[Allocation]:
    """Long format (one row per person, project and month) or wide format (one column per month, YYYY-MM)."""
    fields, raw = _read(path)
    cols = _map(fields, RESOURCE_ALIASES)
    months = [h for h in fields if month_key(h) and re.match(r"^\s*\d{4}[-/]\d{1,2}\s*$", h)]
    out = []
    for r in raw:
        g = {k: (r.get(c) or "").strip() for k, c in cols.items()}
        if not g.get("project"):
            continue
        pairs = [(month_key(m), r.get(m)) for m in months] if months and "month" not in cols else [(month_key(g.get("month")), g.get("allocation"))]
        for m, v in pairs:
            a = num(str(v or "").replace("%", ""))
            if m and a:
                out.append(Allocation(g.get("person", ""), g.get("role", ""), g.get("team", ""), g["project"], m, a * 100 if a <= 1.5 else a))
    return out


def load_releases(path: Path) -> list[Release]:
    return [Release(r["project"], r.get("release", ""), parse_d(r.get("planned")), r.get("change", ""), r.get("cab", ""))
            for r in _rows(path, RELEASE_ALIASES) if r.get("project")]


def load_sprints(path: Path) -> list[Sprint]:
    out = [Sprint(r["project"], r.get("team", ""), r.get("sprint", ""), parse_d(r.get("start")), parse_d(r.get("end")),
                  num(r.get("committed")) or 0, num(r.get("completed")) or 0, num(r.get("added")) or 0)
           for r in _rows(path, SPRINT_ALIASES) if r.get("project")]
    return sorted(out, key=lambda s: (s.project, s.team, s.end or date.min, s.sprint))


FILES = {
    "projects.csv": "Projects from the PPM tool or the portfolio sheet",
    "milestones.csv": "Milestones and stage gates per project",
    "raid.csv": "RAID log: risks, issues, dependencies and assumptions",
    "resources.csv": "Resource plan: allocation % per person, project and month",
    "releases.csv": "Planned releases with change ticket and CAB status (optional)",
    "sprints.csv": "Sprint or PI history from Jira or Azure DevOps (optional)",
}


def load(folder: Path, as_of: datetime | None = None) -> Data:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"no folder {folder}")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    when = as_of or s.as_of or datetime.now().replace(second=0, microsecond=0)
    if not (folder / "projects.csv").exists():
        raise FileNotFoundError(f"{folder}: need projects.csv ({FILES['projects.csv']})")
    d = Data(s, when)
    d.projects = load_projects(folder / "projects.csv")
    if not d.projects:
        raise ValueError(f"{folder / 'projects.csv'}: no projects (check the ProjectId column)")
    d.sources = {"projects.csv": len(d.projects)}
    loaders = {"milestones.csv": ("milestones", load_milestones), "raid.csv": ("raid", load_raid),
               "resources.csv": ("resources", load_resources), "releases.csv": ("releases", load_releases),
               "sprints.csv": ("sprints", load_sprints)}
    for name, (attr, fn) in loaders.items():
        if (folder / name).exists():
            rows = fn(folder / name)
            setattr(d, attr, rows)
            d.sources[name] = len(rows)
    return d


__all__ = ["Data", "Settings", "Project", "Milestone", "Raid", "Allocation", "Release", "Sprint", "load", "load_projects", "load_milestones",
           "load_raid", "load_resources", "load_releases", "load_sprints", "settings_from_dict", "working_days", "add_working", "pct",
           "level", "month_key", "methodology", "is_agile", "FILES"]
