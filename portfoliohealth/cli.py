"""Command line: `demo` writes the fictional Fabrikam Insurance exports to sample_data/ and builds the outputs; `review` runs on your own
exports."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import report, simulate
from .checks import AMBER, GREEN, RED, money, review, summary
from .model import load, parse_dt

OUTPUTS = ("report.html", "steerco-pack.md", "project-health.csv", "findings.csv", "resource-load.csv", "decisions.csv", "actions.csv")


def run(data: Path, out: Path, title: str | None = None, as_of: datetime | None = None) -> dict:
    d = load(data, as_of)
    rv = review(d)
    title = title or f"{d.settings.organisation} · IT portfolio health, {d.as_of:%d %B %Y}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, rv, title), encoding="utf-8")
    (out / "steerco-pack.md").write_text(report.pack_md(d, rv, title), encoding="utf-8")
    report.write_health(d, rv, out / "project-health.csv")
    report.write_findings(rv, out / "findings.csv")
    report.write_load(rv, out / "resource-load.csv")
    report.write_decisions(rv, out / "decisions.csv")
    report.write_actions(rv, out / "actions.csv")
    sm = summary(d, rv)
    sm["currency"] = d.settings.currency
    return sm


def _when(value: str) -> datetime:
    d = parse_dt(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD or 'YYYY-MM-DD HH:MM'): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="portfoliohealth", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional exports to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own exports")
    rv.add_argument("data", type=Path, nargs="?", help="folder with projects.csv and the other exports")
    rv.add_argument("--data", dest="data_opt", type=Path, help="same as the positional folder")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", help="title of the report and the pack")
    rv.add_argument("--as-of", type=_when, help="reference date (default: settings.json, or now)")
    a = p.parse_args(argv)
    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, f"{simulate.ORG} · IT portfolio health, 10 November 2026")
    else:
        folder = a.data or a.data_opt
        if not folder:
            print("error: give the folder with projects.csv", file=sys.stderr)
            return 2
        try:
            sm = run(folder, a.out, a.title, a.as_of)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    st = sm["status"]
    env = (f"forecast {money(sm['total_eac'], sm['currency'])} vs envelope {money(sm['envelope'], sm['currency'])} ({sm['over_pct']:+.1f} %)"
           if sm["envelope"] else f"forecast {money(sm['total_eac'], sm['currency'])}, no envelope given")
    print(f"portfolio {sm['overall']} · {sm['projects']} projects: {st.get(RED, 0)} red, {st.get(AMBER, 0)} amber, {st.get(GREEN, 0)} green · "
          f"{sm['watermelons']} watermelon{'' if sm['watermelons'] == 1 else 's'} · {sm['red']} red and {sm['amber']} amber findings · "
          f"{sm['decisions']} decisions for the SteerCo · {sm['over_people']} {'person' if sm['over_people'] == 1 else 'people'} "
          f"over-allocated · {env}")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
