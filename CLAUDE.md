# Personal Finance Dashboard

A local-first personal finance dashboard that replaces my Google Sheets. Built incrementally, one
milestone at a time — see **`docs/roadmap.md`** (M0–M6). M0 (scaffold & privacy) and M1 (Income
import, ported from the first prototype) are done. Next: M2 (Assets + Costs import).

## Commands

```sh
uv sync                                        # install deps into .venv
git config core.hooksPath .githooks            # enable the privacy pre-commit guard (once per clone)
uv run finance                                 # real data  → http://127.0.0.1:8000 (data/finance.db)
FINANCE_MODE=demo uv run finance               # fake data  → data/demo.db, auto-imports demo/Financial 2026.xlsx
uv run pytest                                  # all tests
uv run pytest tests/test_importer.py::test_demo_workbook_parses_to_expected   # single test
uv run python scripts/make_demo_data.py [--seed N] [--out PATH]              # regenerate demo workbook
```

`FINANCE_DB=/path/x.db` overrides the database location.

**Local config** — `finance.local.toml` (gitignored, blocked by the hook; template:
`finance.local.example.toml`) holds personal settings the public code must not contain:
`[income.header_aliases]` maps the real sheet's header names onto the generic ones in `sources.py`,
and `[goals] brutto_monthly_kr` is the real goal (real mode only; demo mode always shows the
placeholder). `FINANCE_LOCAL_CONFIG` overrides its path; tests point it at a missing file.

## Architecture

Pure importer → pure calculations → store (transactions) → web app. All money is **integer øre**.

- `sources.py` is the single registry of income columns (sheet header → key, label, in_netto, order).
  A new sheet column = one line there; `income_source` table is seeded from it; storage is long-format
  `income_entry(year, month, source_key, …)` so no schema change is needed.
- `importers/income.py`: xlsx bytes → `ParsedIncome` (no DB/web). Fatal problems raise
  `IncomeImportError`; everything else becomes a warning that names cells, never amounts.
  Estimates are decided at import time from an injected `today`.
- `income.py`: netto / total pay / year summary / netto check against the sheet's column B.
- `store.py`: `save_income_import` replaces a year atomically, logs the import (warnings, mismatches,
  changes vs. previous import as JSON) and skips identical re-uploads (same SHA-256).
- `app.py`: `create_app(db_path, mode, today)` factory; one SQLite connection per request.
  `demo.py` builds the fake workbook plus the exact expected values used by tests.

## Working agreement

- Build one milestone at a time (`docs/roadmap.md`); don't start other pages until asked.
- Visualization is first-class: dark card-based UI, one big number per card, colour only for
  meaning (green = ahead/in, red = behind/out). Chart data is built server-side as plain dicts
  (testable), rendered client-side with ECharts.
- Plan first, confirm with me, then build.

## Stack (decided — don't re-litigate)

- Python, managed with `uv`
- FastAPI + Jinja2 templates (server-rendered HTML) + HTMX for interactivity
- Apache ECharts for charts, vendored as a static file (no Node build step)
- SQLite (stdlib `sqlite3`)
- `openpyxl` for reading .xlsx, `pytest` for tests
- Runs locally only, bound to `127.0.0.1`. Not hosted online.

## Privacy & security — this repo is PUBLIC

Real salary data must never reach git.

- `data/` (real DB), every `.db`, and every `.xlsx`/`.csv` outside `demo/` are gitignored.
- A pre-commit guard (`.githooks/pre-commit`) refuses spreadsheets/databases outside `demo/`, anything
  in `data/`, `CLAUDE.local.md`, and staged text matching the gitignored `.private-patterns` file.
- Uploaded files are parsed in memory and not stored — only the parsed numbers and a SHA-256 of the file.
- Tests, screenshots and any online showcase use **generated fake demo data** (`demo/`). Fake data
  is random-but-plausible, never derived or scaled from real numbers.
- `FINANCE_MODE=demo` runs the app against the demo data.
- Never paste real figures — or employer/bank names — into commits, docs, test fixtures or issues.
  Personal values belong in `finance.local.toml` / `CLAUDE.local.md` (both gitignored).

## Data source: Google Sheet "Financial <year>" → downloaded as .xlsx

One workbook per year (2024, 2025, 2026 exist; start with **2026 only**). Sheet `Income`:

| Col | Header | Meaning | In netto? |
|---|---|---|---|
| A1 | `2026` | The year (text). A2:A13 are English month names — may have trailing spaces. | — |
| B | Total Income (Netto) | Sheet formula `=SUM(E:K)`. Recompute and compare, don't trust blindly. | total |
| C | *(empty — user is adding "Pension" here)* | Employer pension contribution | **no** |
| D | Salary (Brutto) | Salary before tax — used for the monthly brutto goal | **no** |
| E | Salary (Netto)¹ | Salary paid out | yes |
| F | Stock program¹ | Employee stock programme deduction | yes |
| G | Interest | Interest | yes |
| H | Tax¹ | Annual tax settlement — can be positive or negative | yes |
| I | Side income¹ | Selling used things etc. | yes |
| J | Stocks Realization | Proceeds from selling stocks | yes |
| K | Bank benefits¹ | Bank benefits | yes |
| L | Income avg. | My own ad-hoc calculations — **skip, don't import** | — |

¹ Generic names. The real sheet uses different (identifying) headers for E, F, H, I and K; they
are mapped via `[income.header_aliases]` in `finance.local.toml` and must never be written into
tracked files. Same rule for every future sheet: public code uses generic names only.

- Row 14 is a `Total` row — skip it.
- Blank cells = 0. Cells may contain formulas; read cached values (`data_only=True`).
- Match columns **by header name**, not position. Unknown headers → warning, not crash.
- **Netto = every income column except Salary (Brutto) and Pension.**
- **Pension** (employer contribution) is not spendable: excluded from netto, included in
  "Total pay" (= Brutto + Pension), and later counted as savings / net worth.
- **Estimates:** the sheet has forecasts for future months. Rule: months after the month of the
  import are estimates; the next monthly re-upload turns them into actuals.
- I re-upload the whole year's file every month → re-import replaces that year atomically (no
  double counting), logs the import and shows what changed vs. the previous import.
- Overtime lives in a separate sheet with a different layout — later module.
- Currency DKK, display in Danish format (`55.000,00 kr.`).

## Roadmap & design context (outside this repo)

- Things 3 project **"💰 Personal Finance Dashboard"** — 30 tasks in 5 phases (Things MCP available).
- Obsidian design notes (goal tracking design, Fisker Finance inspiration) — path in
  `CLAUDE.local.md` (gitignored, local only).
- Key goal related to income: a monthly **brutto goal** (the amount lives in the gitignored local config).
- Later: bank CSV importer, goals engine, other pages, MCP server over the data, demo mode for a
  portfolio write-up on leventkurtis.com.
