# Roadmap

A local-first dashboard that replaces a yearly "Financial <year>" spreadsheet. The spreadsheet stays
the place where numbers are entered; it is downloaded as `.xlsx` and uploaded into the app, which
stores, visualizes and — above all — **tracks goals**: for every goal, *actual* vs. *expected now*
vs. *required run-rate from here*.

## Architecture

```
xlsx bytes ─► importers/<sheet>.py   pure: bytes → Parsed*, warnings (cells, never amounts)
          ─► store.py               one atomic import per workbook-year, import log, change diff
          ─► metrics/               pure: netto, savings rate, net worth, …
          ─► goals/                 pure evaluators: trajectory, rate, ceiling, streak
          ─► web/                   FastAPI → Jinja pages; /api/chart/* returns ECharts option JSON
```

- Money is integer øre; displayed Danish style (`55.000,00 kr.`).
- One upload imports every supported sheet of the workbook in one transaction.
- Columns are matched by header name via registries, plus private aliases in `finance.local.toml`.
- Months after the import month are estimates; charts draw them faded/dashed.

## Workbook sheets

| Sheet | Shape | Used for |
|---|---|---|
| Income | months × sources | Income page, brutto goal, savings rate |
| Assets | point-in-time snapshot (account balances, investments, loan, equity) | net worth, emergency fund |
| Costs | months × categories | savings rate, spending ceilings |
| Budgetting | months × 50/30/20 buckets | later |
| Overtime, Shareholder program, Loan costs | own layouts | later |

The Assets sheet is a snapshot, so **net worth history accumulates**: each import stores a dated
snapshot. Older yearly workbooks can backfill it.

## Goals engine

```
expected_now = baseline + (target − baseline) × elapsed / total
pace         = actual / expected_now          (inverted for ceiling goals)
projected    = actual + run_rate × remaining
required     = (target − actual) / remaining
```

Status: ≥ 105 % ahead · 95–105 % on track · 85–95 % slightly behind · < 85 % behind · missed.
Every status is shown together with the action ("you need X kr./month for the remaining N months").
Target changes are kept in an audit trail. Goal targets are entered in the app (stored in the
gitignored database), never in code.

## Milestones

- [x] **M0 – Scaffold & privacy** — uv project, privacy pre-commit guard, gitignore, local config.
- [x] **M1 – Income import** — importer, store with atomic re-import and change log, demo generator.
- [ ] **M2 – Assets + Costs import** — snapshot + grid parsers, demo data for both, net worth and
      savings-rate metrics.
- [ ] **M3 – App shell & visual system** — sidebar layout, dark/light tokens, vendored ECharts +
      HTMX, upload page with import diff, demo/real badge.
- [ ] **M4 – Income page** — KPI tiles, stacked monthly bars by source, brutto vs. goal line, year
      table, year selector.
- [ ] **M5 – Goals** — evaluators, snapshots on import, goal CRUD, cards (actual + expected-now on
      one bar), detail chart (actual vs. target trajectory), archive with hit/miss.
- [ ] **M6 – Overview** — net worth hero chart, pinned goals strip, month at a glance, savings-rate
      sparkline.

## Later

Bank CSV importer with rule-based categorisation (LLM fallback) → Spending & Budgets page (radial
gauges, month projection, spending calendar/heatmap) → Overtime & shareholder programme →
Investments → multi-year backfill → read-only MCP server over the data → AI insights.
