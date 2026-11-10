"""The portfolio health checks. Per project: schedule (forecast end against the plan, late milestones, milestones with no forecast, a
gate passed without approval), cost (EVM-light CPI and SPI from % complete and budget, forecast at completion over budget, a forecast
below what the CPI points to, burn rate against time elapsed), governance (stale status, "watermelon" projects that the PM reports
GREEN while the metrics say RED, RAID items overdue or unowned), agile (velocity falling, scope growth), resources (people over 100 %,
one key person on several critical projects, unstaffed roles), delivery (releases inside a change freeze, a change not approved with
the go-live a few working days away) and value (a benefit with no owner, a low-priority RED project as a pause or stop candidate).
For the portfolio: the forecast against the approved envelope. Each project gets a computed RAG with the reason, each programme and
the portfolio a RAG, and the decisions the steering committee has to take are listed with options and impact."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from .model import Data, Project, add_working, is_agile, working_days

GREEN, AMBER, RED = "GREEN", "AMBER", "RED"
RAG_ORDER = {RED: 0, AMBER: 1, GREEN: 2}
DIMENSIONS = ["schedule", "cost", "governance", "agile", "resources", "delivery", "value"]
DIM_LABEL = {"schedule": "Schedule", "cost": "Cost", "governance": "Governance", "agile": "Agile", "resources": "Resources",
             "delivery": "Delivery", "value": "Value"}
# code: dimension, title, owner kind (pm, sponsor, or a settings owner key), counts towards the project RAG
CHECKS = {
    "SCH-SLIP": ("schedule", "Forecast end later than planned", "pm", True),
    "SCH-MILESTONE": ("schedule", "Milestone late", "pm", True),
    "SCH-NOFORECAST": ("schedule", "Milestone past its baseline with no forecast", "pm", True),
    "SCH-GATE": ("schedule", "Gate passed without approval", "sponsor", True),
    "CST-CPI": ("cost", "Cost performance (CPI) low", "pm", True),
    "CST-SPI": ("schedule", "Schedule performance (SPI) low", "pm", True),
    "CST-EAC": ("cost", "Forecast at completion over budget", "pm", True),
    "CST-FORECAST": ("cost", "Forecast below what the CPI points to", "pm", True),
    "CST-BURN": ("cost", "Spending faster than time elapsed", "pm", True),
    "GOV-STALE": ("governance", "Status not updated", "pm", True),
    "GOV-WATERMELON": ("governance", "Reported GREEN, metrics RED (watermelon)", "sponsor", True),
    "RAID-OVERDUE": ("governance", "RAID items overdue", "pm", True),
    "RAID-UNOWNED": ("governance", "RAID items with no owner", "pm", True),
    "AGL-VELOCITY": ("agile", "Velocity falling", "pm", True),
    "AGL-SCOPE": ("agile", "Scope growth", "pm", True),
    "RES-OVER": ("resources", "Person allocated over 100 %", "resources", True),
    "RES-KEYPERSON": ("resources", "One person on several critical projects", "resources", True),
    "RES-UNSTAFFED": ("resources", "Role not staffed", "resources", True),
    "DLV-FREEZE": ("delivery", "Release inside a change freeze", "change", True),
    "DLV-CAB": ("delivery", "Change not approved close to go-live", "change", True),
    "VAL-NOOWNER": ("value", "Benefit with no owner", "sponsor", True),
    "VAL-STOP": ("value", "Low priority and RED: pause or stop candidate", "sponsor", False),
    "PRT-ENVELOPE": ("cost", "Portfolio forecast over the approved envelope", "pmo", False),
}
# a person's problem is not a project's RED on its own: resource findings count as AMBER at most for each project
DIM_CAP = {"resources": AMBER}


@dataclass
class Finding:
    code: str
    severity: str                 # RED or AMBER
    projects: list                # project ids ([] for the portfolio)
    subject: str
    detail: str
    action: str
    owner: str = ""
    due: date | None = None
    reason: str = ""              # short, for the RAG reason of a project

    @property
    def dimension(self) -> str:
        return CHECKS[self.code][0]

    @property
    def title(self) -> str:
        return CHECKS[self.code][1]


@dataclass
class Health:
    project: Project
    elapsed: float | None = None          # share of the planned duration elapsed
    progress: float | None = None
    ev: float | None = None
    pv: float | None = None
    cpi: float | None = None
    spi: float | None = None
    slip_days: int | None = None
    slip_pct: float | None = None
    eac_var_pct: float | None = None
    cpi_eac: float | None = None          # budget / CPI
    spent_pct: float | None = None
    days_since_update: int | None = None
    velocity_change: float | None = None
    scope_growth: float | None = None
    raid_open: int = 0
    raid_overdue: int = 0
    findings: list = field(default_factory=list)
    status: str = GREEN
    dims: dict = field(default_factory=dict)
    reason: str = ""
    watermelon: bool = False


def _sev(value: float, th: dict, higher_is_worse: bool = True) -> str | None:
    if higher_is_worse:
        return RED if value > th["red"] else AMBER if value > th["amber"] else None
    return RED if value < th["red"] else AMBER if value < th["amber"] else None


def worst(xs) -> str:
    xs = list(xs)
    return min(xs, key=lambda x: RAG_ORDER[x]) if xs else GREEN


def money(x: float | None, cur: str = "EUR") -> str:
    if x is None:
        return "–"
    a = abs(x)
    s = f"{a / 1e6:.2f}M" if a >= 1e6 else f"{a / 1e3:.0f}k" if a >= 1e3 else f"{a:.0f}"
    return f"{'-' if x < 0 else ''}{cur} {s}"


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


# ---------------------------------------------------------------- per project

def metrics(d: Data, p: Project) -> Health:
    h = Health(p)
    t = d.today
    if p.start and p.planned_end and p.planned_end > p.start:
        dur = (p.planned_end - p.start).days
        h.elapsed = max(0.0, min(1.0, (t - p.start).days / dur))
        if p.forecast_end:
            h.slip_days = (p.forecast_end - p.planned_end).days
            h.slip_pct = 100 * h.slip_days / dur
    h.progress = p.progress
    if p.budget:
        if h.progress is not None:
            h.ev = p.budget * h.progress
        if h.elapsed is not None:
            h.pv = p.budget * h.elapsed
        if p.actual is not None:
            h.spent_pct = 100 * p.actual / p.budget
        if p.eac is not None:
            h.eac_var_pct = 100 * (p.eac - p.budget) / p.budget
        if h.ev is not None and p.actual and (h.progress or 0) >= d.settings.evm_min_progress:
            h.cpi = h.ev / p.actual
            h.cpi_eac = p.budget / h.cpi if h.cpi else None
        if h.ev is not None and h.pv and (h.elapsed or 0) >= d.settings.evm_min_progress:
            h.spi = h.ev / h.pv
    if p.last_update:
        h.days_since_update = (t - p.last_update).days
    return h


def check_project(d: Data, p: Project) -> Health:
    s = d.settings
    h = metrics(d, p)
    t = d.today
    cur = s.currency
    out = h.findings

    def f(code: str, sev: str, detail: str, action: str, reason: str, subject: str = "") -> None:
        out.append(Finding(code, sev, [p.id], subject or p.name, detail, action, reason=reason))

    # schedule
    if h.slip_pct is not None and h.slip_days and h.slip_days > 0:
        sev = _sev(h.slip_pct, s.schedule_slip_pct)
        if sev:
            f("SCH-SLIP", sev, f"forecast end {p.forecast_end:%d %b %Y} against {p.planned_end:%d %b %Y} planned: {h.slip_days} days, "
                               f"{h.slip_pct:.0f} % of the planned duration", "Re-plan with the sponsor: confirm the new date and what "
                               "drives it, or recover scope or resources to hold the plan.", f"end {h.slip_days} days late ({h.slip_pct:.0f} %)")
    ms = [m for m in d.milestones if m.project == p.id]
    for m in sorted(ms, key=lambda m: (m.baseline or date.max, m.name)):
        if m.baseline and not m.actual and not m.forecast and m.baseline < t:
            f("SCH-NOFORECAST", AMBER, f"{m.name}: baseline {m.baseline:%d %b %Y} has passed, no actual and no forecast date",
              "Give the milestone a forecast date or record it as done.", f"{m.name} with no forecast", f"{p.name}: {m.name}")
            continue
        late = None
        if m.baseline and (m.actual or m.forecast):
            late = ((m.actual or m.forecast) - m.baseline).days
        if late is not None and not m.actual and late > 0:
            sev = _sev(late, s.milestone_late_days)
            if sev:
                f("SCH-MILESTONE", sev, f"{m.name}: forecast {m.forecast:%d %b %Y} against the baseline {m.baseline:%d %b %Y}, {late} days "
                                        f"({late // 7} weeks) late", "Agree the recovery plan for the milestone, or re-baseline it at the SteerCo.",
                  f"{m.name} {late // 7} weeks late", f"{p.name}: {m.name}")
        if m.gate and m.actual and not m.approved:
            f("SCH-GATE", RED, f"{m.name}: passed on {m.actual:%d %b %Y} with no approval recorded",
              "Record the gate decision (who approved, when, on what evidence) or hold the next phase until the gate is approved.",
              f"{m.name} passed without approval", f"{p.name}: {m.name}")
    # cost
    if h.cpi is not None:
        sev = _sev(h.cpi, s.cpi, higher_is_worse=False)
        if sev:
            f("CST-CPI", sev, f"CPI {h.cpi:.2f}: {100 * h.progress:.0f} % done for {h.spent_pct:.0f} % of the budget spent ({money(p.actual, cur)} "
                              f"spent for {money(h.ev, cur)} of work done)", "Find where the cost goes (rates, rework, scope) and agree a cost "
                              "recovery plan or a new forecast.", f"CPI {h.cpi:.2f}")
    if h.spi is not None:
        sev = _sev(h.spi, s.spi, higher_is_worse=False)
        if sev:
            f("CST-SPI", sev, f"SPI {h.spi:.2f}: {100 * h.progress:.0f} % done ({p.progress_source}) with {100 * h.elapsed:.0f} % of the planned time elapsed",
              "Check the plan against the work left and the team's capacity; re-plan if the gap is structural.", f"SPI {h.spi:.2f}")
    if h.eac_var_pct is not None and h.eac_var_pct > 0:
        sev = _sev(h.eac_var_pct, s.cost_variance_pct)
        if sev:
            f("CST-EAC", sev, f"forecast at completion {money(p.eac, cur)} against {money(p.budget, cur)} approved: "
                              f"+{h.eac_var_pct:.0f} % ({money(p.eac - p.budget, cur)})", "Bring the change request for the extra budget "
                              "to the SteerCo, or reduce scope to the approved budget.", f"forecast +{h.eac_var_pct:.0f} % over budget")
    if h.cpi_eac and p.eac and h.cpi_eac > p.eac:
        gap = 100 * (h.cpi_eac - p.eac) / p.eac
        sev = _sev(gap, s.cost_variance_pct)
        if sev:
            f("CST-FORECAST", sev, f"reported forecast {money(p.eac, cur)}; at the current CPI the budget lands at {money(h.cpi_eac, cur)} "
                                   f"({gap:.0f} % more)", "Ask the PM to explain what will make the rest of the work cheaper, or update "
                                   "the forecast.", f"forecast {gap:.0f} % below the CPI trend")
    if h.spent_pct is not None and h.elapsed is not None and h.spent_pct - 100 * h.elapsed > s.burn_tolerance_pct:
        f("CST-BURN", AMBER, f"{h.spent_pct:.0f} % of the budget spent with {100 * h.elapsed:.0f} % of the planned time elapsed",
          "Check the burn rate with finance: front-loaded licences or hardware are fine, a team burning too fast is not.",
          "burning faster than time")
    # governance
    if h.days_since_update is None or h.days_since_update > s.stale_status_days:
        when = f"last status update on {p.last_update:%d %b %Y}, {h.days_since_update} days ago" if p.last_update else "no status date"
        f("GOV-STALE", AMBER, f"{when} (the cadence is every {s.stale_status_days} days at most)",
          "Ask the PM for a status update before the SteerCo pack goes out.", f"status {h.days_since_update // 7 if p.last_update else '?'} weeks old")
    if d.raid is not None:
        items = [r for r in d.raid if r.project == p.id and r.open]
        h.raid_open = len(items)
        over = [r for r in items if r.due and r.due < t]
        h.raid_overdue = len(over)
        if over:
            high = [r for r in over if r.score >= 12]
            f("RAID-OVERDUE", RED if high else AMBER,
              f"{_n(len(over), 'open item')} past the due date: " + "; ".join(f"{r.id} {r.type} '{r.title}' due {r.due:%d %b}"
                                                                                + ("" if r.owner else ", no owner") for r in over[:4]),
              "Review the overdue items with their owners: close, re-date with a reason, or escalate.", f"{_n(len(over), 'RAID item')} overdue")
        unowned = [r for r in items if not r.owner]
        if unowned:
            f("RAID-UNOWNED", RED if any(r.score >= 12 and r in over for r in unowned) else AMBER,
              f"{_n(len(unowned), 'open item')} with no owner: " + "; ".join(f"{r.id} '{r.title}'" for r in unowned[:4]),
              "Give every open RAID item a named owner.", f"{_n(len(unowned), 'RAID item')} unowned")
    # agile
    if d.sprints is not None and is_agile(p.methodology):
        sp = [x for x in d.sprints if x.project == p.id and x.end and x.end <= t]
        k = s.velocity_window
        if len(sp) >= 2 * k:
            by_end = defaultdict(float)
            for x in sp:
                by_end[x.end] += x.completed
            vel = [by_end[e] for e in sorted(by_end)]
            if len(vel) >= 2 * k:
                before, last = sum(vel[-2 * k:-k]) / k, sum(vel[-k:]) / k
                if before:
                    h.velocity_change = 100 * (last - before) / before
                    sev = _sev(-h.velocity_change, s.velocity_drop_pct)
                    if sev:
                        f("AGL-VELOCITY", sev, f"points completed per sprint fell from {before:.0f} to {last:.0f} on average "
                                               f"({h.velocity_change:.0f} %), last {k} sprints against the {k} before",
                          "Look at the cause with the team (people moved, unplanned work, dependencies) at the retrospective or the "
                          "Inspect & Adapt.", f"velocity {h.velocity_change:.0f} %")
        added = sum(x.added for x in [x for x in d.sprints if x.project == p.id])
        if p.points_total and added and p.points_total > added:
            h.scope_growth = 100 * added / (p.points_total - added)
            sev = _sev(h.scope_growth, s.scope_growth_pct)
            if sev:
                f("AGL-SCOPE", sev, f"{added:.0f} points added to a scope of {p.points_total - added:.0f}: +{h.scope_growth:.0f} %, now "
                                    f"{p.points_total:.0f} with {p.points_done or 0:.0f} done",
                  "Fix the scope for the plan with the product owner: what comes out for what came in, or a new date.",
                  f"scope +{h.scope_growth:.0f} %")
    # value
    if p.benefit and not p.benefit_owner.strip():
        f("VAL-NOOWNER", AMBER, f"business case benefit of {money(p.benefit, cur)} a year with no benefit owner",
          "Name the business owner who will be accountable for the benefit after go-live.", "benefit has no owner")
    return h


# ---------------------------------------------------------------- portfolio-wide checks

def resource_load(d: Data) -> list[dict]:
    if d.resources is None:
        return []
    months = sorted({a.month for a in d.resources if a.month >= f"{d.today:%Y-%m}"})[:d.settings.resource_months]
    crit = {p.id for p in d.projects if p.priority <= d.settings.critical_priority}
    rows = defaultdict(lambda: {"total": 0.0, "projects": []})
    info = {}
    for a in d.resources:
        if a.vacant or a.month not in months:
            continue
        r = rows[(a.person, a.month)]
        r["total"] += a.allocation
        r["projects"].append((a.project, a.allocation))
        info.setdefault(a.person, (a.role, a.team))
    out = []
    for (person, month), r in sorted(rows.items()):
        ps = sorted(r["projects"], key=lambda x: (-x[1], x[0]))
        out.append({"person": person, "role": info[person][0], "team": info[person][1], "month": month, "total": r["total"],
                    "projects": ps, "critical": sorted({x for x, _ in ps if x in crit}),
                    "over": r["total"] > d.settings.over_allocation_pct})
    return out


def check_resources(d: Data, load: list[dict]) -> list[Finding]:
    s = d.settings
    out = []
    by_person = defaultdict(list)
    for r in load:
        by_person[r["person"]].append(r)
    for person in sorted(by_person):
        rs = by_person[person]
        over = [r for r in rs if r["over"]]
        role = rs[0]["role"]
        if over:
            peak = max(over, key=lambda r: (r["total"], r["month"]))
            projects = sorted({x for r in over for x, _ in r["projects"]})
            out.append(Finding("RES-OVER", RED if peak["total"] >= s.over_allocation_red_pct else AMBER, projects, f"{person} ({role})",
                               f"allocated {peak['total']:.0f} % in {peak['month']} ("
                               + ", ".join(f"{x} {a:.0f} %" for x, a in peak["projects"]) + f"); over {s.over_allocation_pct:.0f} % in "
                               + ", ".join(r["month"] for r in over),
                               "Agree the priority between the projects, move work or bring in a backfill; plans built on 180 % of a "
                               "person slip together.", reason=f"{person} at {peak['total']:.0f} %"))
        crit = sorted({x for r in rs for x in r["critical"]})
        if len(crit) >= s.key_person_critical_projects:
            out.append(Finding("RES-KEYPERSON", AMBER, crit, f"{person} ({role})",
                               f"{role or 'person'} named on {_n(len(crit), 'critical project')} in the same months: {', '.join(crit)}",
                               "Name a deputy or second person for the role on the critical projects and share the knowledge.",
                               reason=f"key person {person}"))
    if d.resources is not None:
        months = sorted({a.month for a in d.resources if a.month >= f"{d.today:%Y-%m}"})[:s.resource_months]
        vac = defaultdict(list)
        for a in d.resources:
            if a.vacant and a.month in months:
                vac[(a.project, a.role or "role")].append(a)
        for (pid, role), xs in sorted(vac.items()):
            out.append(Finding("RES-UNSTAFFED", AMBER, [pid], f"{pid}: {role}",
                               f"{role} planned at {max(x.allocation for x in xs):.0f} % in {', '.join(sorted({x.month for x in xs}))} with nobody named",
                               "Staff the role or move the work that depends on it in the plan.", reason=f"{role} not staffed"))
    return out


def check_releases(d: Data) -> list[Finding]:
    if d.releases is None:
        return []
    s = d.settings
    t = d.today
    names = {p.id: p.name for p in d.projects}
    out = []
    for r in sorted(d.releases, key=lambda r: (r.planned or date.max, r.project, r.release)):
        if not r.planned or r.planned < t:
            continue
        for name, a, b in s.freezes:
            if a <= r.planned <= b:
                out.append(Finding("DLV-FREEZE", AMBER, [r.project], f"{names.get(r.project, r.project)}: {r.release}",
                                   f"{r.release} planned on {r.planned:%a %d %b %Y}, inside the {name} ({a:%d %b} to {b:%d %b %Y})"
                                   + (f"; {r.change} is {r.cab or 'not raised'}" if r.change else ""),
                                   "Move the release out of the freeze, or ask for a freeze exception with the business case and the "
                                   "rollback plan.", reason=f"release in the {name.lower()}"))
        left = working_days(t, r.planned, s.holiday_set)
        if not r.approved and left <= s.cab_working_days:
            state = f"{r.change} is {r.cab or 'not approved'}" if r.change else "no change ticket raised"
            out.append(Finding("DLV-CAB", RED, [r.project], f"{names.get(r.project, r.project)}: {r.release}",
                               f"go-live {r.planned:%a %d %b} in {_n(left, 'working day')} and {state}",
                               "Get the CAB decision (or an emergency CAB) before the go-live, or move the date; no go-live without an "
                               "approved change.", due=max(t, add_working(r.planned, -1, s.holiday_set)),
                               reason=f"CAB pending {left} days before go-live"))
    return out


# ---------------------------------------------------------------- everything

def _owner(d: Data, f: Finding, projects: dict) -> str:
    kind = CHECKS[f.code][2]
    p = projects.get(f.projects[0]) if f.projects else None
    if kind == "pm":
        return (p.pm if p and p.pm else d.settings.owner("pmo"))
    if kind == "sponsor":
        return (p.sponsor if p and p.sponsor else d.settings.owner("pmo"))
    return d.settings.owner(kind)


def review(d: Data) -> dict:
    s = d.settings
    hol = s.holiday_set
    projects = {p.id: p for p in d.projects}
    health = {p.id: check_project(d, p) for p in d.projects}
    load = resource_load(d)
    shared = check_resources(d, load) + check_releases(d)
    for f in shared:
        for pid in f.projects:
            if pid in health:
                health[pid].findings.append(f)
    # RAG per project from the metric findings, then the watermelon and the stop candidates on top
    for h in health.values():
        _rag(h)
        p = h.project
        if h.status == RED and p.rag == GREEN:
            h.watermelon = True
            reds = [x.reason for x in h.findings if x.severity == RED and CHECKS[x.code][3]][:3]
            h.findings.append(Finding("GOV-WATERMELON", RED, [p.id], p.name, f"the PM reports GREEN; the metrics say RED: {', '.join(reds)}",
                                      "Reset the status to RED in the pack and agree a recovery plan; ask what the GREEN was based on, "
                                      "without blame.", reason="reported GREEN"))
        if h.status == RED and p.priority >= s.stop_priority:
            h.findings.append(Finding("VAL-STOP", RED, [p.id], p.name,
                                      f"priority {p.priority} and RED ({h.reason}); {money((p.eac or 0) - (p.actual or 0), s.currency)} still to "
                                      f"spend", "Decide at the SteerCo: continue with a re-plan, pause or stop, and where the money and the "
                                      "people go.", reason="pause or stop candidate"))
        _rag(h)
    # portfolio envelope
    portfolio = []
    total_eac = sum((p.eac if p.eac is not None else p.budget or 0) for p in d.projects)
    total_budget = sum(p.budget or 0 for p in d.projects)
    env = s.portfolio_envelope
    over_pct = 100 * (total_eac - env) / env if env else None
    if env and total_eac > env:
        portfolio.append(Finding("PRT-ENVELOPE", RED if over_pct > s.envelope_red_pct else AMBER, [], "Portfolio",
                                 f"forecast at completion {money(total_eac, s.currency)} against an approved envelope of "
                                 f"{money(env, s.currency)}: +{over_pct:.1f} % ({money(total_eac - env, s.currency)})",
                                 "Decide at the SteerCo how to close the gap: more funding, pausing or stopping projects, or reducing scope.",
                                 reason=f"portfolio +{over_pct:.1f} %"))
    findings = _unique([f for h in health.values() for f in h.findings] + portfolio)
    for f in findings:
        f.owner = _owner(d, f, projects)
        days = s.action_working_days.get("red" if f.severity == RED else "amber", 10)
        due = add_working(d.today, int(days), hol)
        f.due = min(due, f.due) if f.due else due
    findings.sort(key=lambda f: (RAG_ORDER[f.severity], list(CHECKS).index(f.code), f.projects[:1], f.subject))
    hs = sorted(health.values(), key=lambda h: h.project.id)
    progs = programmes(d, hs)
    status = worst([x["status"] for x in progs] + [f.severity for f in portfolio])
    return {"health": hs, "findings": findings, "load": load, "programmes": progs, "status": status, "total_eac": total_eac,
            "total_budget": total_budget, "envelope": env, "over_pct": over_pct, "decisions": decisions(d, hs, findings)}


def _unique(fs: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in fs:
        if id(f) not in seen:
            seen.add(id(f))
            out.append(f)
    return out


def _eff(f: Finding) -> str:
    """The severity a finding gives the project (resource findings count as AMBER at most)."""
    return AMBER if f.severity == RED and DIM_CAP.get(f.dimension) == AMBER else f.severity


def _rag(h: Health) -> None:
    dims = {}
    for dim in DIMENSIONS:
        sevs = [f.severity for f in h.findings if f.dimension == dim and CHECKS[f.code][3]]
        st = worst(sevs)
        if dim in DIM_CAP and st == RED:
            st = DIM_CAP[dim]
        dims[dim] = st
    if h.watermelon:
        dims["governance"] = RED
    h.dims = dims
    h.status = worst(dims.values())
    top = sorted([f for f in h.findings if CHECKS[f.code][3]], key=lambda f: (RAG_ORDER[_eff(f)], list(CHECKS).index(f.code)))
    reasons = list(dict.fromkeys(f.reason for f in top if f.reason))
    h.reason = "; ".join(reasons) if reasons else "on track against the plan and the budget"
    h.reason = "; ".join(h.reason.split("; ")[:3])


def programmes(d: Data, hs: list[Health]) -> list[dict]:
    s = d.settings
    out = []
    for prog in sorted({h.project.programme for h in hs}, key=lambda g: min(h.project.id for h in hs if h.project.programme == g)):
        xs = [h for h in hs if h.project.programme == prog]
        st = Counter(h.status for h in xs)
        budget = sum(h.project.budget or 0 for h in xs)
        eac = sum((h.project.eac if h.project.eac is not None else h.project.budget or 0) for h in xs)
        crit_red = [h for h in xs if h.status == RED and h.project.priority <= s.critical_priority]
        if crit_red or st[RED] * 3 >= len(xs):
            status = RED
        elif st[RED] or st[AMBER]:
            status = AMBER
        else:
            status = GREEN
        out.append({"programme": prog or "(none)", "projects": len(xs), GREEN: st[GREEN], AMBER: st[AMBER], RED: st[RED],
                    "watermelons": sum(h.watermelon for h in xs), "budget": budget, "eac": eac,
                    "var_pct": 100 * (eac - budget) / budget if budget else None, "status": status,
                    "benefit": sum(h.project.benefit or 0 for h in xs), "critical_red": [h.project.id for h in crit_red]})
    return out


# ---------------------------------------------------------------- decisions for the steering committee

@dataclass
class Decision:
    id: str
    kind: str
    project: Project | None
    decision: str
    why: str
    options: str
    proposed: str
    impact: str
    owner: str
    needed_by: date | None


def decisions(d: Data, hs: list[Health], findings: list[Finding]) -> list[Decision]:
    s = d.settings
    cur = s.currency
    by = {h.project.id: h for h in hs}
    out = []

    def add(kind, p, decision, why, options, proposed, impact, owner=""):
        out.append(Decision("", kind, p, decision, why, options, proposed, impact, owner or (p.sponsor if p and p.sponsor else s.owner("pmo")),
                            s.steerco))

    env = next((f for f in findings if f.code == "PRT-ENVELOPE"), None)
    stops = [h for h in hs if any(f.code == "VAL-STOP" for f in h.findings)]
    if env:
        saving = sum((h.project.eac or 0) - (h.project.actual or 0) for h in stops)
        add("funding", None, "Close the gap between the portfolio forecast and the approved envelope", env.detail,
            "Increase the envelope / pause or stop low-priority projects / reduce scope in the overrunning projects",
            ("Review the pause and stop candidates first" + (f" ({money(saving, cur)} still to spend on "
                                                            f"{', '.join(h.project.id for h in stops)})" if stops else "")
             + ", then fund the remainder or cut scope"),
            f"{money(sum((p.eac if p.eac is not None else p.budget or 0) for p in d.projects) - (s.portfolio_envelope or 0), cur)} "
            "to find", s.owner("pmo"))
    for h in stops:
        p = h.project
        add("stop", p, f"Continue, re-plan, pause or stop {p.id} {p.name}",
            f"Priority {p.priority} and RED: {h.reason}",
            "Continue as is / re-plan with a new baseline / pause until the overrun is explained / stop",
            "Pause and review the business case; stop if the benefit no longer covers the cost to complete",
            f"{money((p.eac or 0) - (p.actual or 0), cur)} still to spend; benefit {money(p.benefit, cur)} a year; frees the time of "
            + (", ".join(sorted({a.person for a in d.resources or [] if a.project == p.id and not a.vacant})[:3]) or "its team"))
    for h in hs:
        p = h.project
        if h in stops or h.status != RED:
            continue
        if h.watermelon:
            add("watermelon", p, f"Reset {p.id} {p.name} to RED and agree the recovery plan",
                f"Reported GREEN; {h.reason}", "Re-plan with a new baseline / continue with a recovery plan and a checkpoint in a month / "
                "reduce scope", "Recovery plan from the PM for the next SteerCo, with a forecast based on the CPI",
                _impact(h, cur))
            continue
        codes = {f.code for f in h.findings if f.severity == RED}
        if codes & {"SCH-SLIP", "SCH-MILESTONE", "CST-CPI", "CST-SPI", "CST-EAC", "AGL-SCOPE", "AGL-VELOCITY"}:
            scope = "AGL-SCOPE" in codes
            add("replan", p, f"{'Re-scope' if scope else 'Re-plan'} {p.id} {p.name}", h.reason,
                ("Fix the scope for the plan (out for in) / extend the date / add capacity" if scope else
                 "Approve a new baseline (date and cost) / recover with more capacity / reduce scope"),
                ("Fix the scope with the product owner at the next PI planning; keep the date" if scope else
                 "Approve a new baseline only with a recovery plan and the cost of the change"), _impact(h, cur))
    for f in findings:
        if f.code == "RES-KEYPERSON":
            add("people", by[f.projects[0]].project if f.projects and f.projects[0] in by else None,
                f"Set the priority of {f.subject.split(' (')[0]} across {', '.join(f.projects)}", f.detail,
                "Rank the projects for this person / bring in a second person or a contractor / move milestones",
                "Rank the projects and fund a second person for the role",
                "; ".join(x.detail for x in findings if x.code == "RES-OVER" and x.subject == f.subject)[:200] or "risk on every project named",
                s.owner("resources"))
        elif f.code == "DLV-FREEZE":
            p = by[f.projects[0]].project
            add("freeze", p, f"{f.subject}: move it or approve a freeze exception", f.detail,
                "Move before or after the freeze / approve an exception with a rollback plan", "Move it after the freeze unless the "
                "business case needs the date", "a cutover inside the freeze needs an exception under the change policy", s.owner("change"))
        elif f.code == "VAL-NOOWNER":
            p = by[f.projects[0]].project
            add("benefit", p, f"Name the benefit owner of {p.id} {p.name}", f.detail, "Name an owner in the business / reduce the "
                "benefit in the business case", "Name the owner at the SteerCo", f"{money(p.benefit, cur)} a year without anyone "
                "accountable")
    order = {"funding": 0, "stop": 1, "watermelon": 2, "replan": 3, "people": 4, "freeze": 5, "benefit": 6}
    out.sort(key=lambda x: (order[x.kind], x.project.id if x.project else ""))
    for i, x in enumerate(out, 1):
        x.id = f"D-{i:02d}"
    return out


def _impact(h: Health, cur: str) -> str:
    p = h.project
    bits = []
    if h.slip_days and h.slip_days > 0:
        bits.append(f"end +{h.slip_days} days")
    if p.eac and p.budget and p.eac > p.budget:
        bits.append(f"+{money(p.eac - p.budget, cur)} over budget")
    if h.cpi_eac and p.budget and h.cpi_eac > (p.eac or p.budget):
        bits.append(f"{money(h.cpi_eac, cur)} at the current CPI")
    if p.benefit:
        bits.append(f"benefit {money(p.benefit, cur)} a year at stake")
    return "; ".join(bits) or "date and benefit at risk"


def summary(d: Data, rv: dict) -> dict:
    hs = rv["health"]
    st = Counter(h.status for h in hs)
    return dict(projects=len(hs), status=st, overall=rv["status"], red=sum(f.severity == RED for f in rv["findings"]),
                amber=sum(f.severity == AMBER for f in rv["findings"]), findings=len(rv["findings"]),
                watermelons=sum(h.watermelon for h in hs), decisions=len(rv["decisions"]),
                over_people=len({r["person"] for r in rv["load"] if r["over"]}), programmes=len(rv["programmes"]),
                total_eac=rv["total_eac"], total_budget=rv["total_budget"], envelope=rv["envelope"], over_pct=rv["over_pct"],
                stale=sum(any(f.code == "GOV-STALE" for f in h.findings) for h in hs),
                stop=[h.project.id for h in hs if any(f.code == "VAL-STOP" for f in h.findings)])


__all__ = ["GREEN", "AMBER", "RED", "DIMENSIONS", "DIM_LABEL", "CHECKS", "Finding", "Health", "Decision", "metrics", "check_project",
           "resource_load", "check_resources", "check_releases", "review", "programmes", "decisions", "summary", "money", "worst"]
