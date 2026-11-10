# Monthly SteerCo with the pack

How to prepare the monthly IT steering committee with `portfoliohealth`. The tool only reads exports; plans, budgets, RAID logs and changes are updated by their owners in their own tools.

## Who is involved

| Role | Part |
|---|---|
| Portfolio office (PMO), chair's secretary | Collects the exports, runs the check, sends the pack, keeps the decisions and actions log |
| SteerCo chair (CIO or business executive) | Takes the decisions, keeps the meeting to decisions rather than status |
| Sponsors | Own the decisions on their projects: re-plan, pause, stop, benefits |
| Project managers, release train engineers | Answer for their RED and AMBER projects, bring the recovery plans |
| Finance (IT finance) | Confirms actuals and the envelope |
| Resource managers, architecture | Answer for over-allocated people and key-person risks |
| Change manager | Releases in a freeze, changes not approved near a go-live |

## The month

| When | What | Output |
|---|---|---|
| SteerCo − 10 working days | Remind PMs: status updated, forecast and % complete current, RAID reviewed | |
| SteerCo − 7 days | Export projects, milestones, RAID and resources from the PPM tool; releases and change records; sprints with `scripts/export_agile.py` | `data/` |
| SteerCo − 7 days | Run the check; send each PM their project's findings, ask for corrections and the reason behind every RED | `output/` |
| SteerCo − 5 days | PMs answer; re-run with corrected data (only corrected data, not adjusted thresholds) | updated `output/` |
| SteerCo − 3 days | Send the pack (`steerco-pack.md`) and the report to the members, with the decisions needed listed first | the pack |
| SteerCo | 60 minutes, decisions first (agenda below) | `decisions.csv` outcome column, `actions.csv` |
| SteerCo + 2 days | Send the minutes: decisions taken, actions with owner and date | minutes |
| Every week until the next one | Follow the actions; re-run for the RED projects | |

```bash
python scripts/export_agile.py jira --site https://contoso.atlassian.net --board 42 --project-id P-201 --out data/sprints.csv
python -m portfoliohealth review data/
```

## What to send before the meeting

- The pack, one page: headlines, decisions needed with options and impact, the red and amber projects with the reason, the portfolio against the envelope, and what each owner brings to the meeting.
- The report for anyone who wants the detail: the heat map, the project cards, the cost and schedule scatter and the resource load.
- For each decision, a short paper from the sponsor or PM when the impact is large: the options, the cost of each, the recommendation. The pack's "proposed" column is a starting point from the rules, not the recommendation.

Send it three working days before. A decision read for the first time in the meeting turns into a request for more information.

## Agenda (60 minutes)

| Minutes | Topic | Section | Who |
|---|---|---|---|
| 5 | Portfolio: status, forecast against the envelope, what changed since last month | Headlines, Portfolio | PMO |
| 30 | Decisions needed, in the order of the pack | Decisions needed | Sponsors, PMs |
| 15 | Red and amber projects not covered by a decision: is the reason clear, is the plan credible | Red and amber projects | PMs |
| 5 | People and delivery: over-allocation, key people, freeze and CAB | Decisions needed, report | Resource manager, change manager |
| 5 | Actions and next SteerCo | Minutes | PMO |

Green projects are not discussed unless someone asks.

## Framing decisions

Every decision has four standard options; the pack lists the ones that fit:

- **Continue**: the plan still holds; the finding is noted and watched. Only with a reason the data does not show.
- **Re-plan**: a new baseline (date, cost or scope) approved with a recovery plan. A new baseline without a reason for the slip is the same slip next month.
- **Pause**: stop spending until a condition is met (the overrun explained, a person available, a dependency delivered). Name the condition and the date to look again.
- **Stop**: close the project, release the money and the people, keep what has value. Stopping a low-priority RED project is a good outcome, not a failure.

For each one write down the cost of the option, the effect on the benefit and on the people, and who decides. When the portfolio is over the envelope, look at the pause and stop candidates before asking for more money.

## Watermelon projects

A watermelon is green outside and red inside: the PM reports GREEN and the numbers say RED. It is almost never dishonesty; it is optimism, a status nobody asked to justify, or a culture where RED is punished.

- Show the computed RAG next to the reported one, always, for every project; the difference is the conversation.
- Ask what the GREEN was based on before the meeting, privately. Often there is an explanation the data does not have (a contract credit, a re-baselined plan not yet in the tool).
- Reset the status to RED in the pack without blame, and ask for the recovery plan. Thank the PM who reports RED early: a RED in month two is cheaper than a RED in month nine.
- Use the forecast at the current CPI as the honest number when the reported forecast is lower, until the PM explains what changes.

## Following up

- Every decision leaves the meeting with an owner and a date, in `decisions.csv` (outcome column) and in the minutes.
- Every RED finding has an action in `actions.csv` with an owner and a due date; the PMO checks them weekly and re-runs the check for the RED projects.
- At the next SteerCo, start with the actions of the last one: done, late, or no longer needed.
- Keep the thresholds in `settings.json` stable from month to month. Changing them to make the portfolio look better hides the trend.

## Keeping it useful

- The data is only as good as the status updates: the stale-status check is there to make the cadence visible, not to chase PMs.
- Agree the thresholds once with the SteerCo and publish them with the pack.
- Use the heat map to see patterns: several projects red on resources is a capacity problem, not several project problems.
- Do not rank PMs by RAG. A RED with a credible plan is better than a GREEN nobody checked.
