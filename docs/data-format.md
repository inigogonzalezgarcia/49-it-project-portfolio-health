# Data format

Put the files in one folder and run `python -m portfoliohealth review <folder>`. Only `projects.csv` is required; every other file adds its checks (a check without its file is skipped, not passed). Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the alternatives below are accepted. Dates as ISO 8601 (`2026-11-17`, `2026-11-02T10:15:00Z`), `dd/mm/yyyy`, `MM/dd/yyyy` or `17 Nov 2026`; the time zone suffix is ignored. Amounts may carry a currency sign and thousands separators (`€ 1,200,000`, `1.200.000,00`).

`projects.csv` and `milestones.csv` usually come from the PPM tool (or the portfolio sheet), `raid.csv` from the RAID log, `resources.csv` from the resource plan, `releases.csv` from the release calendar and the ITSM change records, and `sprints.csv` from Jira or Azure DevOps with `scripts/export_agile.py`.

## How the check works

| Step | Rule |
|---|---|
| Progress | `PercentComplete` as reported; when it is empty, `PointsDone / PointsTotal` (agile projects) |
| Elapsed | Share of the planned duration that has passed: (today − `Start`) / (`PlannedEnd` − `Start`), between 0 and 1 |
| EVM-light | EV (earned value: what the work done is worth) = budget × progress. PV (planned value: what should be done by today) = budget × elapsed, on a straight line. CPI = EV / actual cost: 0.80 means each euro spent bought 80 cents of the planned work. SPI = EV / PV: 0.80 means 80 % of the work planned by today is done. Both are left out while progress or elapsed is under `evm_min_progress` (10 %), when they mean little |
| Forecast at the CPI | budget / CPI: where the cost lands if the rest of the work costs what the work so far did. A reported forecast well below it is `CST-FORECAST` |
| Project RAG | The worst severity of the project's findings, per dimension (schedule, cost, governance, agile, resources, delivery, value) and overall. Resource findings count as AMBER at most for a project (an over-allocated person is a portfolio problem). The reason is the top three findings |
| Watermelon | The PM reports GREEN and the computed RAG is RED (`GOV-WATERMELON`) |
| Stop candidate | Priority `stop_priority` (3) or lower and RED (`VAL-STOP`): a decision for the SteerCo, not a verdict |
| Programme RAG | RED when a project with priority `critical_priority` (1) is RED, or a third or more of the projects are RED; AMBER with any RED or AMBER project; else GREEN |
| Portfolio | The worst programme status, and the forecast at completion of all projects against `portfolio_envelope` (`PRT-ENVELOPE`) |
| Due dates | Actions for RED findings are due `action_working_days.red` (4) working days from today, AMBER ones `action_working_days.amber` (10); a change not approved is due the working day before its go-live |
| Decisions | Built from the findings: the envelope gap, each stop candidate, each watermelon, each other RED project with schedule, cost or scope findings, a key person, a release in a freeze and a benefit with no owner. Each has options, a proposal, the impact and the owner, needed by `steerco_date` |

## projects.csv

One row per project.

| Column | Alternatives | Notes |
|---|---|---|
| ProjectId | Project ID, code, key | Required; the key used by every other file |
| Name | Project, Project name | |
| Programme | Program, Department, portfolio | Projects are grouped by it |
| Sponsor | Executive sponsor | Owner of gate, watermelon, benefit and stop decisions |
| ProjectManager | PM, owner, release train engineer | Owner of the project's actions |
| Methodology | Method, approach, framework | `Waterfall`, `Agile` (Scrum, Kanban) or `SAFe ART`; agile checks only run for agile and SAFe projects |
| Phase | Gate, Stage | Informational |
| Start | StartDate, baseline start | |
| PlannedEnd | baseline end, baseline finish | |
| ForecastEnd | expected end, estimated end | Against `PlannedEnd`: `SCH-SLIP` |
| BudgetApproved | approved budget, bac | |
| ActualToDate | actual cost, spend to date | |
| ForecastAtCompletion | eac, fac, estimate at completion | Against the budget: `CST-EAC`; summed against the envelope |
| PercentComplete | % complete, progress | `45`, `45 %` or `0.45` |
| PointsDone, PointsTotal | story points done / total | Progress for agile projects when `PercentComplete` is empty; `PointsTotal` is the current scope (used for scope growth) |
| BenefitAnnual | benefit, business case benefit | Yearly benefit in the business case |
| BenefitOwner | benefits owner | Empty with a benefit: `VAL-NOOWNER` |
| Priority | Strategic priority, tier | 1 (highest) to 3; 1 is critical (`critical_priority`) |
| RagReported | RAG, status, pm rag | `Green`, `Amber`, `Red` (`G`/`A`/`R`, `on track`, `at risk`, `off track` work too) |
| LastStatusUpdate | status date, last updated | Older than `stale_status_days`: `GOV-STALE` |

## milestones.csv

| Column | Alternatives | Notes |
|---|---|---|
| ProjectId | project | |
| Milestone | Name, title | |
| BaselineDate | Baseline, planned date | |
| ForecastDate | Forecast, expected date | Later than the baseline by more than `milestone_late_days`: `SCH-MILESTONE` |
| ActualDate | Actual, completed | Done; a baseline in the past with no actual and no forecast is `SCH-NOFORECAST` |
| Gate | is gate, stage gate | `Yes` for a stage gate |
| GateApproval | Approval, approved by | Who approved the gate and when (`SteerCo 2026-06-16`); a gate with an actual date and no approval is `SCH-GATE` |

## raid.csv

| Column | Alternatives | Notes |
|---|---|---|
| ProjectId | project | |
| Id | Key, reference | |
| Type | category | `Risk`, `Issue`, `Dependency`, `Assumption` (anything else is kept as is) |
| Title | Summary, description | |
| Probability | likelihood | 1-5 or `Low` (2), `Medium` (3), `High` (4), `Very high` (5); an issue counts as 5 |
| Impact | severity | Same scale. Score = probability × impact; 12 or more is high |
| Owner | Assignee | Empty, `TBD` or `Unassigned` is no owner: `RAID-UNOWNED` |
| DueDate | Due date, target date | Open and past: `RAID-OVERDUE` (RED when a high-score item is overdue) |
| Status | state | `Closed`, `Done`, `Resolved`, `Mitigated`, `Retired`, `Accepted` or `Cancelled` close an item; anything else is open |
| LastReviewed | reviewed, updated | Informational |

## resources.csv

Long format (one row per person, project and month) or wide format (one column per month named `YYYY-MM`).

| Column | Alternatives | Notes |
|---|---|---|
| Person | Name, Resource | Empty, `TBD`, `Vacant` or `Unfilled` is a role nobody fills: `RES-UNSTAFFED` |
| Role | skill, position | |
| Team | resource pool | |
| ProjectId | project | |
| Month | period | `2026-11`, `Nov 2026`, `11/2026` or a date |
| Allocation | Allocation %, fte % | `60`, `60%` or `0.6`. Only the next `resource_months` months from today are used |

A person whose allocations add up to more than `over_allocation_pct` (100) in a month is `RES-OVER` (RED from `over_allocation_red_pct`, 150); a person on `key_person_critical_projects` (2) or more critical projects is `RES-KEYPERSON`.

## releases.csv (optional)

| Column | Alternatives | Notes |
|---|---|---|
| ProjectId | project | |
| Release | Name, go-live | |
| PlannedDate | release date, go live date | Inside a `freeze_windows` window: `DLV-FREEZE` |
| ChangeTicket | Change, rfc, change number | |
| CabStatus | CAB status, change status | `Approved`, `Authorised`, `Scheduled`, `Implemented` or `Closed` count as approved; anything else, or no ticket, with the go-live within `cab_working_days` (5) working days is `DLV-CAB` |

## sprints.csv (optional)

One row per sprint (or iteration) of an agile project, written by `scripts/export_agile.py`.

| Column | Alternatives | Notes |
|---|---|---|
| ProjectId | project | |
| Team | board | |
| Sprint | Iteration, pi | |
| StartDate, EndDate | start, finish date | Only sprints ended by today count |
| CommittedPoints | Committed, planned points | |
| CompletedPoints | Completed, done points | Velocity: the average of the last `velocity_window` (3) sprints against the three before; a fall beyond `velocity_drop_pct` is `AGL-VELOCITY` |
| AddedPoints | Added, scope added | Points added after the sprint started. Scope growth = added / (`PointsTotal` − added); beyond `scope_growth_pct` is `AGL-SCOPE` |

## settings.json

| Setting | Default | Notes |
|---|---|---|
| `organisation` | | Shown in the report |
| `as_of` | now | Reference date and time (fixed in the demo so the output is the same every run) |
| `steerco_date` | | Date of the steering committee; decisions are needed by it |
| `currency` | EUR | Shown with the amounts |
| `portfolio_envelope` | | Approved envelope for the portfolio; the sum of the forecasts is compared with it |
| `envelope_red_pct` | 5 | Over the envelope by more than this is RED, by less AMBER |
| `schedule_slip_pct` | amber 10, red 20 | Slip of the end date as % of the planned duration |
| `milestone_late_days` | amber 14, red 30 | Days a milestone forecast is past its baseline |
| `cost_variance_pct` | amber 5, red 10 | Forecast at completion over budget, and reported forecast under the CPI forecast |
| `cpi`, `spi` | amber 0.95, red 0.85 | Below these |
| `evm_min_progress` | 0.1 | Minimum progress and elapsed share for CPI and SPI |
| `burn_tolerance_pct` | 15 | Budget spent minus time elapsed, in points, before `CST-BURN` |
| `stale_status_days` | 21 | Days since the last status update |
| `over_allocation_pct`, `over_allocation_red_pct` | 100, 150 | Total allocation of a person in a month |
| `key_person_critical_projects` | 2 | Critical projects one person can be on before it is a key-person risk |
| `critical_priority`, `stop_priority` | 1, 3 | Priority of the critical projects; priority from which a RED project is a stop candidate |
| `resource_months` | 3 | Months of the resource plan checked, from the current one |
| `velocity_drop_pct` | amber 15, red 30 | Fall of the average velocity |
| `velocity_window` | 3 | Sprints in each average |
| `scope_growth_pct` | amber 20, red 35 | Points added against the original scope |
| `cab_working_days` | 5 | Working days before the go-live by which the change must be approved |
| `freeze_windows` | [] | `[{"name": "Year-end change freeze", "start": "2026-12-14", "end": "2027-01-08"}]` |
| `holidays` | [] | Dates that are not working days |
| `action_working_days` | red 4, amber 10 | When actions are due |
| `owners` | | Owner per kind: `pmo`, `resources`, `change`, `architecture`, `finance` |

## Checks

| Code | Dimension | Severity | Finding |
|---|---|---|---|
| SCH-SLIP | Schedule | AMBER / RED | Forecast end later than planned, as % of the planned duration |
| SCH-MILESTONE | Schedule | AMBER / RED | Milestone forecast later than its baseline |
| SCH-NOFORECAST | Schedule | AMBER | Milestone baseline passed with no actual and no forecast |
| SCH-GATE | Schedule | RED | Gate passed (actual date) with no approval recorded |
| CST-SPI | Schedule | AMBER / RED | SPI below the thresholds |
| CST-CPI | Cost | AMBER / RED | CPI below the thresholds |
| CST-EAC | Cost | AMBER / RED | Forecast at completion over budget |
| CST-FORECAST | Cost | AMBER / RED | Reported forecast below budget / CPI |
| CST-BURN | Cost | AMBER | Share of budget spent ahead of the share of time elapsed |
| GOV-STALE | Governance | AMBER | Status not updated within `stale_status_days` |
| GOV-WATERMELON | Governance | RED | Reported GREEN, computed RED |
| RAID-OVERDUE | Governance | AMBER / RED | Open RAID items past their due date (RED with a high-score item) |
| RAID-UNOWNED | Governance | AMBER / RED | Open RAID items with no owner (RED when a high-score one is also overdue) |
| AGL-VELOCITY | Agile | AMBER / RED | Velocity falling |
| AGL-SCOPE | Agile | AMBER / RED | Scope growth |
| RES-OVER | Resources | AMBER / RED (AMBER for the project) | Person allocated over 100 % in a month |
| RES-KEYPERSON | Resources | AMBER | One person on several critical projects |
| RES-UNSTAFFED | Resources | AMBER | Role in the plan with nobody named |
| DLV-FREEZE | Delivery | AMBER | Release planned inside a change freeze |
| DLV-CAB | Delivery | RED | Change not approved (or not raised) with the go-live within `cab_working_days` |
| VAL-NOOWNER | Value | AMBER | Benefit in the business case with no owner |
| VAL-STOP | Value | decision | Low-priority project that is RED: continue, re-plan, pause or stop |
| PRT-ENVELOPE | Portfolio | AMBER / RED | Sum of the forecasts over the approved envelope |

## Outputs

| File | Columns |
|---|---|
| `project-health.csv` | project, programme, sponsor, PM, methodology, phase, priority, RAG reported and computed, watermelon, reason, dates, slip, progress and its source, elapsed, budget, actual, forecast, variance, CPI, SPI, forecast at the CPI, benefit and owner, last update, velocity change, scope growth, RAID open and overdue, findings, and the RAG per dimension |
| `findings.csv` | severity, dimension, code, check, projects, programmes, subject, detail, action, owner, due |
| `resource-load.csv` | person, role, team, month, allocation %, over, projects with their allocation, critical projects |
| `decisions.csv` | id, project, programme, decision, why, options, proposed, impact, decision owner, needed by, outcome (empty, for the meeting) |
| `actions.csv` | ref, project, severity, code, action, detail, owner, due, done (empty) |
