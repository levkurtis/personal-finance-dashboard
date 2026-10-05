# Personal Finance Dashboard

A local-first personal finance dashboard that replaces a spreadsheet. Upload the yearly workbook
(`.xlsx`), get charts and — the main point — **goal tracking**: are you on track, and if not, what
does it take from here?

Runs on your own machine only (bound to `127.0.0.1`). Real data never leaves it; everything in this
repo — tests, screenshots, demo — uses generated fake data.

## Run

```sh
uv sync
git config core.hooksPath .githooks        # privacy guard (once per clone)
FINANCE_MODE=demo uv run finance           # fake demo data → http://127.0.0.1:8000
uv run finance                             # your own data (data/finance.db, gitignored)
uv run pytest
```

Personal settings (your sheet's header names) go in `finance.local.toml` — copy
`finance.local.example.toml`.

## Stack

Python · FastAPI · Jinja2 + HTMX · Apache ECharts · SQLite · openpyxl · uv · pytest

See [`docs/roadmap.md`](docs/roadmap.md) for the architecture and milestones.
