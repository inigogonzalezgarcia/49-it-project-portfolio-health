"""Outputs: report.html (portfolio heat map, a card per project with the computed RAG and the reason, the cost and schedule scatter,
the programmes, the resource load and the decisions needed), steerco-pack.md (one page for the steering committee), and the CSVs:
project-health, findings, resource-load, decisions and actions."""
from __future__ import annotations

import csv
import html
from pathlib import Path

from .checks import AMBER, DIM_LABEL, DIMENSIONS, GREEN, RED, Finding, money, summary
from .model import FILES, Data

e = html.escape
TODO = "**[TO COMPLETE]**"


def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _d(x) -> str:
    return "" if x is None else x.isoformat()


def _day(x) -> str:
    return "–" if x is None else f"{x:%d %b %Y}"


def _f(x, nd: int = 2) -> str:
    return "" if x is None else f"{x:.{nd}f}"


def _pct(x) -> str:
    return "" if x is None else f"{100 * x:.0f}"


# ---------------------------------------------------------------- csv

def write_health(d: Data, rv: dict, path: Path) -> None:
    head = ["project_id", "name", "programme", "sponsor", "project_manager", "methodology", "phase", "priority", "rag_reported",
            "rag_computed", "watermelon", "reason", "start", "planned_end", "forecast_end", "slip_days", "slip_pct", "progress_pct",
            "progress_source", "elapsed_pct", "budget", "actual_to_date", "forecast_at_completion", "forecast_var_pct", "cpi", "spi",
            "forecast_at_cpi", "benefit_annual", "benefit_owner", "last_status_update", "days_since_update", "velocity_change_pct",
            "scope_growth_pct", "raid_open", "raid_overdue", "findings_red", "findings_amber"] + DIMENSIONS
    rows = []
    for h in rv["health"]:
        p = h.project
        rows.append([p.id, p.name, p.programme, p.sponsor, p.pm, p.methodology, p.phase, p.priority, p.rag, h.status,
                     "yes" if h.watermelon else "no", h.reason, _d(p.start), _d(p.planned_end), _d(p.forecast_end),
                     "" if h.slip_days is None else h.slip_days, _f(h.slip_pct, 1), _pct(h.progress), p.progress_source, _pct(h.elapsed),
                     _f(p.budget, 0), _f(p.actual, 0), _f(p.eac, 0), _f(h.eac_var_pct, 1), _f(h.cpi), _f(h.spi), _f(h.cpi_eac, 0),
                     _f(p.benefit, 0), p.benefit_owner, _d(p.last_update), "" if h.days_since_update is None else h.days_since_update,
                     _f(h.velocity_change, 0), _f(h.scope_growth, 0), h.raid_open, h.raid_overdue,
                     sum(f.severity == RED for f in h.findings), sum(f.severity == AMBER for f in h.findings)] + [h.dims[x] for x in DIMENSIONS])
    _w(path, head, rows)


def _names(rv: dict) -> dict:
    return {h.project.id: h.project for h in rv["health"]}


def write_findings(rv: dict, path: Path) -> None:
    ps = _names(rv)
    _w(path, ["severity", "dimension", "code", "check", "projects", "programmes", "subject", "detail", "action", "owner", "due"],
       [[f.severity, f.dimension, f.code, f.title, "; ".join(f.projects), "; ".join(sorted({ps[x].programme for x in f.projects if x in ps})),
         f.subject, f.detail, f.action, f.owner, _d(f.due)] for f in rv["findings"]])


def write_load(rv: dict, path: Path) -> None:
    _w(path, ["person", "role", "team", "month", "allocation_pct", "over", "projects", "critical_projects"],
       [[r["person"], r["role"], r["team"], r["month"], f"{r['total']:.0f}", "yes" if r["over"] else "no",
         "; ".join(f"{x} {a:.0f}%" for x, a in r["projects"]), "; ".join(r["critical"])] for r in rv["load"]])


def write_decisions(rv: dict, path: Path) -> None:
    _w(path, ["id", "project_id", "project", "programme", "decision", "why", "options", "proposed", "impact", "decision_owner", "needed_by",
              "outcome"],
       [[x.id, x.project.id if x.project else "", x.project.name if x.project else "Portfolio", x.project.programme if x.project else "",
         x.decision, x.why, x.options, x.proposed, x.impact, x.owner, _d(x.needed_by), ""] for x in rv["decisions"]])


def _ref(f: Finding, n: int) -> str:
    return (f"{f.projects[0]}-" if f.projects else "") + f"{f.code}-{n:02d}"


def actions(rv: dict) -> list[tuple[str, Finding]]:
    out = []
    count = {}
    for f in sorted(rv["findings"], key=lambda f: (f.due, f.severity != RED, f.projects[:1], f.code, f.subject)):
        k = (f.projects[0] if f.projects else "PRT", f.code)
        count[k] = count.get(k, 0) + 1
        out.append((_ref(f, count[k]), f))
    return out


def write_actions(rv: dict, path: Path) -> None:
    ps = _names(rv)
    _w(path, ["ref", "project_id", "project", "severity", "code", "action", "detail", "owner", "due", "done"],
       [[ref, "; ".join(f.projects), "; ".join(ps[x].name for x in f.projects if x in ps) or "Portfolio", f.severity, f.code, f.action,
         f.detail, f.owner, _d(f.due), ""] for ref, f in actions(rv)])


# ---------------------------------------------------------------- the SteerCo pack

def _md(x) -> str:
    return str(x).replace("|", "/").replace("\n", " ")


def pack_md(d: Data, rv: dict, title: str) -> str:
    s = d.settings
    sm = summary(d, rv)
    st = sm["status"]
    cur = s.currency
    hs = rv["health"]
    out = [f"# {title}", "",
           f"> Prepared on {d.as_of:%a %d %b %Y} from the exports listed at the end, for the steering committee on "
           f"{_day(s.steerco)}. Read-only: nothing was changed in any tool. RAG is computed from the data against the thresholds in "
           f"settings.json; the RAG the project manager reported is shown next to it. Sections marked {TODO} are for the meeting.", "",
           f"**Portfolio: {sm['overall']}. {sm['projects']} projects: {st.get(GREEN, 0)} green, {st.get(AMBER, 0)} amber, {st.get(RED, 0)} red"
           + (f"; {sm['watermelons']} reported GREEN with RED metrics" if sm["watermelons"] else "") + ".**", "",
           "## Headlines", ""]
    if sm["envelope"]:
        out.append(f"- Forecast at completion {money(sm['total_eac'], cur)} against an approved envelope of {money(sm['envelope'], cur)}"
                   + (f": **{sm['over_pct']:+.1f} %**." if sm["over_pct"] is not None else "."))
    for x in rv["programmes"]:
        out.append(f"- {x['programme']}: **{x['status']}**, {x['projects']} projects ({x[RED]} red, {x[AMBER]} amber), forecast "
                   f"{money(x['eac'], cur)} against {money(x['budget'], cur)} approved"
                   + (f" ({x['var_pct']:+.1f} %)" if x["var_pct"] is not None else "") + ".")
    for h in hs:
        if h.watermelon:
            out.append(f"- **{h.project.id} {_md(h.project.name)}** is reported GREEN; the metrics say RED: {_md(h.reason)}.")
    over = sorted({r["person"] for r in rv["load"] if r["over"]})
    if over:
        out.append(f"- Over-allocated: {', '.join(over)}.")
    out += ["", "## Decisions needed", "", "| # | Decision | Options | Proposed | Impact | Owner | Outcome |", "|---|---|---|---|---|---|---|"]
    out += [f"| {x.id} | **{_md(x.decision)}**<br>{_md(x.why)} | {_md(x.options)} | {_md(x.proposed)} | {_md(x.impact)} | {_md(x.owner)} | |"
            for x in rv["decisions"]] or ["| – | No decisions needed | | | | | |"]
    out += ["", "## Red and amber projects", "", "| Project | Programme | Priority | PM says | Computed | Why | Forecast vs budget | PM |",
            "|---|---|---|---|---|---|---|---|"]
    attn = sorted([h for h in hs if h.status != GREEN], key=lambda h: ({RED: 0, AMBER: 1}[h.status], h.project.priority, h.project.id))
    for h in attn:
        p = h.project
        var = f"{h.eac_var_pct:+.0f} %" if h.eac_var_pct is not None else "–"
        out.append(f"| {p.id} {_md(p.name)} | {_md(p.programme)} | {p.priority} | {p.rag or '–'} | **{h.status}**"
                   f"{' (watermelon)' if h.watermelon else ''} | {_md(h.reason)} | {var} | {_md(p.pm)} |")
    green = [h.project.id for h in hs if h.status == GREEN]
    out += ["", f"Green: {', '.join(green) if green else 'none'}.", "",
            "## Portfolio", "", "| Programme | Status | Projects | Green | Amber | Red | Approved | Forecast | Variance | Annual benefit |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    out += [f"| {_md(x['programme'])} | **{x['status']}** | {x['projects']} | {x[GREEN]} | {x[AMBER]} | {x[RED]} | {money(x['budget'], cur)} | "
            f"{money(x['eac'], cur)} | {'–' if x['var_pct'] is None else format(x['var_pct'], '+.1f') + ' %'} | {money(x['benefit'], cur)} |"
            for x in rv["programmes"]]
    out.append(f"| **Total** | **{sm['overall']}** | {sm['projects']} | {st.get(GREEN, 0)} | {st.get(AMBER, 0)} | {st.get(RED, 0)} | "
               f"{money(sm['total_budget'], cur)} | {money(sm['total_eac'], cur)} | "
               + (f"envelope {money(sm['envelope'], cur)} ({sm['over_pct']:+.1f} %)" if sm["envelope"] else "–") + " | |")
    groups = {}
    for f in rv["findings"]:
        if f.severity == RED:
            groups.setdefault(f.projects[0] if len(f.projects) == 1 else f.subject, []).append(f)
    out += ["", "## Before the meeting", "", "The red findings, one line per project: the owner brings the answer to the SteerCo.", "",
            "| Project | Red findings | Owners | Due | Done |", "|---|---|---|---|---|"]
    for k, fs in sorted(groups.items(), key=lambda x: (min(f.due for f in x[1]), x[0] == "Portfolio", x[0])):
        name = _names(rv)[k].name if k in _names(rv) else ""
        out.append(f"| {_md((k + ' ' + name).strip())} | {_md('; '.join(dict.fromkeys(f.title for f in fs)))} | "
                   f"{_md(', '.join(dict.fromkeys(f.owner for f in fs)))} | {_day(min(f.due for f in fs))} | |")
    out += ["", f"All {len(rv['findings'])} findings with detail are in `findings.csv`, and every action with owner and due date in "
            "`actions.csv`.", "",
            "## Scope and evidence", "", f"- Organisation: {s.organisation}", f"- Reference date: {d.as_of:%a %d %b %Y %H:%M}",
            "- Progress: % complete as reported, or story points done over total for agile projects. CPI = value of the work done "
            "(budget × % complete) / actual cost; SPI = value of the work done / value planned by today on a straight line from start to "
            "planned end.", "", "| Source | File | Records |", "|---|---|---|"]
    out += [f"| {FILES.get(k, k)} | `{k}` | {v:,} |" for k, v in d.sources.items()]
    out += ["", "## Minutes", "", f"- Decisions taken: {TODO}", f"- Actions agreed: {TODO}", f"- Next SteerCo: {TODO}", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb;
--g:#cfeedd;--a:#fbe6bd;--r:#f8d2cd;--n:#eef0f2}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;
--bad:#f2685c;--info:#5aa9f0;--g:#173527;--a:#3d2f12;--r:#45201d;--n:#232a31}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}h3{font-size:15px;margin:0}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:24px}
.overall{display:inline-block;margin-top:14px;padding:6px 14px;border-radius:99px;font-weight:700;border:2px solid currentColor}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.red{color:var(--bad)}.amber{color:var(--warn)}.green{color:var(--ok)}
.heat td.c{text-align:center;font-size:12px;font-weight:700;min-width:38px}.heat th{padding:8px 6px}.heat td.c.green{background:var(--g);color:inherit}
.heat td.c.amber{background:var(--a);color:inherit}.heat td.c.red{background:var(--r);color:inherit}.heat tr.prog td{background:var(--n);font-weight:700}
.board{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-top:5px solid var(--ok);border-radius:10px;padding:12px 14px;color:inherit}
.card.red{border-top-color:var(--bad)}.card.amber{border-top-color:var(--warn)}.card .kv{font-size:12px;color:var(--muted);margin-top:6px}
.card p{margin:8px 0 0;font-size:13px}.wm{font-size:11px;font-weight:700;color:var(--bad);margin-left:6px}
svg text{fill:var(--ink);font-size:11px}svg .ax{stroke:var(--line)}svg .ref{stroke:var(--muted);stroke-dasharray:4 4}
svg circle.green{fill:var(--ok)}svg circle.amber{fill:var(--warn)}svg circle.red{fill:var(--bad)}svg .lbl{fill:var(--muted)}
td.subj{min-width:150px}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);min-width:200px;max-width:340px}td.sm{font-size:13px}
td.over{color:var(--bad);font-weight:700}.brk{overflow-wrap:anywhere;word-break:break-word}
footer{margin-top:40px;font-size:13px}
"""


SHORT = {"schedule": "Sched.", "cost": "Cost", "governance": "Gov.", "agile": "Agile", "resources": "Res.", "delivery": "Deliv.",
         "value": "Value"}


def _cls(x: str) -> str:
    return x.lower()


def _pill(x: str) -> str:
    return f"<span class='pill {_cls(x)}'>{e(x)}</span>"


def _table(head: list[str], rows: list[str], cls: str = "") -> str:
    return (f"<div class='wrap'><table class='{cls}'><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" + "".join(rows)
            + "</table></div>")


def scatter(hs: list) -> str:
    """CPI (up) against SPI (right): below 1 is worse. Values are clipped to the 0.5 to 1.2 window."""
    w, hgt, pad = 640, 380, 44
    lo, hi = 0.5, 1.2

    def x(v):
        return pad + (min(hi, max(lo, v)) - lo) / (hi - lo) * (w - 2 * pad)

    def y(v):
        return hgt - pad - (min(hi, max(lo, v)) - lo) / (hi - lo) * (hgt - 2 * pad)

    g = [f"<svg viewBox='0 0 {w} {hgt}' width='100%' role='img' aria-label='CPI against SPI per project'>",
         f"<line class='ax' x1='{pad}' y1='{hgt - pad}' x2='{w - pad}' y2='{hgt - pad}'/>",
         f"<line class='ax' x1='{pad}' y1='{pad}' x2='{pad}' y2='{hgt - pad}'/>",
         f"<line class='ref' x1='{x(1):.1f}' y1='{pad}' x2='{x(1):.1f}' y2='{hgt - pad}'/>",
         f"<line class='ref' x1='{pad}' y1='{y(1):.1f}' x2='{w - pad}' y2='{y(1):.1f}'/>"]
    for v in (0.6, 0.8, 1.0, 1.2):
        g.append(f"<text x='{x(v):.1f}' y='{hgt - pad + 16}' text-anchor='middle'>{v:.1f}</text>")
        g.append(f"<text x='{pad - 6}' y='{y(v) + 4:.1f}' text-anchor='end'>{v:.1f}</text>")
    g += [f"<text x='{w / 2:.0f}' y='{hgt - 6}' text-anchor='middle'>SPI: schedule performance (right is ahead)</text>",
          f"<text x='12' y='{hgt / 2:.0f}' transform='rotate(-90 12 {hgt / 2:.0f})' text-anchor='middle'>CPI: cost performance (up is under cost)</text>",
          f"<text class='lbl' x='{pad + 6}' y='{hgt - pad - 8}'>late and over cost</text>",
          f"<text class='lbl' x='{w - pad - 6}' y='{pad + 12}' text-anchor='end'>ahead and under cost</text>"]
    placed = []
    for h in sorted(hs, key=lambda h: (h.status != RED, h.project.id)):
        if h.cpi is None or h.spi is None:
            continue
        cx, cy = x(h.spi), y(h.cpi)
        g.append(f"<circle class='{_cls(h.status)}' cx='{cx:.1f}' cy='{cy:.1f}' r='5'><title>{e(h.project.id)} {e(h.project.name)}: SPI "
                 f"{h.spi:.2f}, CPI {h.cpi:.2f}</title></circle>")
        if h.status != RED and h.spi >= 0.95 and h.cpi >= 0.95:
            continue                                   # the cluster around 1.0 is named on hover, not labelled
        dy = 4
        while any(abs(cx - a) < 40 and abs(cy + dy - b) < 12 for a, b in placed):
            dy += 12
        placed.append((cx, cy + dy))
        g.append(f"<text x='{cx + 8:.1f}' y='{cy + dy:.1f}'>{e(h.project.id)}</text>")
    g.append("</svg>")
    return "".join(g)


def render_html(d: Data, rv: dict, title: str) -> str:
    s = d.settings
    sm = summary(d, rv)
    st = sm["status"]
    cur = s.currency
    hs = rv["health"]
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>{e(s.organisation)} · {sm['projects']} projects in {sm['programmes']} programmes · "
         f"steering committee {e(_day(s.steerco))} · run on {d.as_of:%a %d %b %Y %H:%M}</p>",
         f"<span class='overall {_cls(sm['overall'])}'>Portfolio: {e(sm['overall'])} · {st.get(RED, 0)} red, {st.get(AMBER, 0)} amber, "
         f"{st.get(GREEN, 0)} green</span>", "<div class='tiles'>"]
    env = (f"{sm['over_pct']:+.1f} %" if sm["over_pct"] is not None else "–")
    tiles = [("Projects", str(sm["projects"]), f"{sm['programmes']} programmes"),
             ("Red", str(st.get(RED, 0)), f"{len(sm['stop'])} pause or stop candidates"),
             ("Amber", str(st.get(AMBER, 0)), "drifting"),
             ("Green", str(st.get(GREEN, 0)), "on track"),
             ("Watermelons", str(sm["watermelons"]), "reported GREEN, metrics RED"),
             ("Decisions", str(sm["decisions"]), f"for {_day(s.steerco)}"),
             ("Forecast vs envelope", env, f"{money(sm['total_eac'], cur)} of {money(sm['envelope'], cur)}" if sm["envelope"] else "no envelope given"),
             ("Over-allocated", str(sm["over_people"]), f"people over {s.over_allocation_pct:.0f} %")]
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(b)}</b><span class='muted'>{e(c)}</span></div>" for a, b, c in tiles]
    h.append("</div><h2>Decisions needed</h2><p class='muted'>For the steering committee: each with options, a proposal and the impact. "
             "The outcome column of decisions.csv is filled in the meeting.</p>")
    h.append(_table(["#", "Decision", "Options", "Proposed", "Impact", "Owner"],
                    [f"<tr><td class='nw'>{e(x.id)}</td><td class='subj'><b>{e(x.decision)}</b><br><span class='sm muted'>{e(x.why)}</span></td>"
                     f"<td class='sm'>{e(x.options)}</td><td class='fix'>{e(x.proposed)}</td><td class='sm'>{e(x.impact)}</td>"
                     f"<td class='sm'>{e(x.owner)}</td></tr>" for x in rv["decisions"]] or ["<tr><td colspan='6'>No decisions needed.</td></tr>"]))
    h.append("<h2>Heat map</h2><p class='muted'>Computed RAG per project and dimension. Resource findings count as amber at most for a "
             "project: an over-allocated person is a portfolio problem.</p>")
    rows = []
    for x in rv["programmes"]:
        rows.append(f"<tr class='prog'><td>{e(x['programme'])}</td><td>{_pill(x['status'])}</td><td colspan='{len(DIMENSIONS) + 1}' class='sm'>"
                    f"{money(x['eac'], cur)} forecast of {money(x['budget'], cur)} approved</td></tr>")
        for hh in [hh for hh in hs if (hh.project.programme or "(none)") == x["programme"]]:
            p = hh.project
            rows.append(f"<tr><td class='nw'><b>{e(p.id)}</b> {e(p.name)}</td><td>{_pill(hh.status)}</td>"
                        f"<td class='sm muted'>{e(p.rag or '–')}</td>"
                        + "".join(f"<td class='c {_cls(hh.dims[k])}' title='{e(DIM_LABEL[k])}: {e(hh.dims[k])}'>{e(hh.dims[k][0])}</td>" for k in DIMENSIONS)
                        + "</tr>")
    h.append(_table(["Project", "Computed", "PM"] + [SHORT[k] for k in DIMENSIONS], rows, "heat"))
    h.append("<h2>Projects</h2><div class='board'>")
    for hh in sorted(hs, key=lambda hh: ({RED: 0, AMBER: 1, GREEN: 2}[hh.status], hh.project.id)):
        p = hh.project
        kv = [f"{p.methodology or 'n/a'} · priority {p.priority} · PM {p.pm or '–'}",
              f"{_pct(hh.progress) or '–'} % done · {_pct(hh.elapsed) or '–'} % of time · CPI {_f(hh.cpi) or '–'} · SPI {_f(hh.spi) or '–'}",
              f"{money(p.eac, cur)} forecast of {money(p.budget, cur)} · end {_day(p.forecast_end)}"]
        h.append(f"<div class='card {_cls(hh.status)}'><h3>{e(p.id)} {e(p.name)}</h3><span class='muted sm'>{e(p.programme)}</span><br>"
                 f"{_pill(hh.status)} <span class='muted sm'>PM: {e(p.rag or '–')}</span>"
                 + ("<span class='wm'>WATERMELON</span>" if hh.watermelon else "")
                 + "".join(f"<div class='kv'>{e(k)}</div>" for k in kv) + f"<p>{e(hh.reason)}</p></div>")
    h.append("</div><h2>Cost and schedule</h2><p class='muted'>CPI = value of the work done (budget × % complete) / actual cost. "
             "SPI = value of the work done / value planned by today on a straight line from start to planned end. Below 1 is worse. Red projects and those below 0.95 are labelled; hover a dot for the others.</p>")
    h.append(f"<div class='tile'>{scatter(hs)}</div>")
    h.append("<h2>Programmes</h2>")
    h.append(_table(["Programme", "Status", "Projects", "Green", "Amber", "Red", "Approved", "Forecast", "Variance", "Annual benefit"],
                    [f"<tr><td><b>{e(x['programme'])}</b></td><td>{_pill(x['status'])}</td><td class='num'>{x['projects']}</td>"
                     f"<td class='num green'>{x[GREEN]}</td><td class='num amber'>{x[AMBER]}</td><td class='num red'>{x[RED]}</td>"
                     f"<td class='num'>{money(x['budget'], cur)}</td><td class='num'>{money(x['eac'], cur)}</td>"
                     f"<td class='num'>{'–' if x['var_pct'] is None else format(x['var_pct'], '+.1f') + ' %'}</td>"
                     f"<td class='num'>{money(x['benefit'], cur)}</td></tr>" for x in rv["programmes"]]))
    h.append("<h2>Resource load</h2>")
    months = sorted({r["month"] for r in rv["load"]})
    people = sorted({r["person"] for r in rv["load"]}, key=lambda n: (-max(r["total"] for r in rv["load"] if r["person"] == n), n))
    cell = {(r["person"], r["month"]): r for r in rv["load"]}
    rrows = []
    for n in people:
        role = next(r["role"] for r in rv["load"] if r["person"] == n)
        tds = []
        for m in months:
            r = cell.get((n, m))
            if r:
                tip = ", ".join(f"{x} {a:.0f}%" for x, a in r["projects"])
                tds.append(f"<td class='num{' over' if r['over'] else ''}' title='{e(tip)}'>{r['total']:.0f} %</td>")
            else:
                tds.append("<td class='num muted'>–</td>")
        crit = sorted({x for m in months for x in (cell[(n, m)]["critical"] if (n, m) in cell else [])})
        rrows.append(f"<tr><td class='nw'><b>{e(n)}</b><br><span class='muted sm'>{e(role)}</span></td>{''.join(tds)}"
                     f"<td class='sm'>{e(', '.join(crit) or '–')}</td></tr>")
    h.append(_table(["Person"] + months + ["Critical projects"], rrows or ["<tr><td>No resources.csv</td></tr>"]))
    h.append("<h2>All findings</h2>")
    h.append(_table(["Severity", "Projects", "Check", "Detail", "Owner", "Due"],
                    [f"<tr><td>{_pill(f.severity)}</td><td class='nw'>{e(', '.join(f.projects) or 'Portfolio')}</td>"
                     f"<td class='subj'>{e(f.title)}</td><td class='sm brk'>{e(f.detail)}</td><td class='sm'>{e(f.owner)}</td>"
                     f"<td class='nw'>{e(_day(f.due))}</td></tr>" for f in rv["findings"]]))
    h.append("<footer class='muted'>Generated by portfoliohealth. Fictional demo data unless you ran it on your own exports. The one-page "
             "pack for the steering committee is steerco-pack.md.</footer></main></body></html>")
    return "".join(h)


__all__ = ["render_html", "pack_md", "write_health", "write_findings", "write_load", "write_decisions", "write_actions", "actions", "scatter"]
