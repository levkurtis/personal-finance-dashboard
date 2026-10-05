"""FastAPI app: Income page, import upload, import results. Server-rendered, deliberately bare."""

import hashlib
from collections.abc import Callable, Iterator
from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from finance import config, store
from finance.db import connect, init_schema
from finance.importers.income import IncomeImportError, parse_income_workbook
from finance.income import year_summary
from finance.money import format_dkk
from finance.sources import SOURCES_BY_KEY

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["dkk"] = format_dkk
templates.env.filters["month"] = lambda m: MONTH_ABBR[m - 1]
templates.env.globals["source_label"] = lambda key: SOURCES_BY_KEY[key].label if key in SOURCES_BY_KEY else key


def import_file(
    conn, data: bytes, filename: str, today: date, header_aliases: dict[str, list[str]] | None = None
) -> store.ImportOutcome:
    """Parse and store an uploaded workbook. Raises IncomeImportError on fatal problems and
    ValueError on invalid header aliases."""
    sha256 = hashlib.sha256(data).hexdigest()
    parsed = parse_income_workbook(data, filename, today, header_aliases)
    return store.save_income_import(conn, parsed, filename, sha256, datetime.now())


def create_app(
    db_path: str | Path | None = None,
    mode: str | None = None,
    today: Callable[[], date] = date.today,
) -> FastAPI:
    app = FastAPI(title="Personal Finance Dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db_path = Path(db_path) if db_path else config.db_path()
    app.state.mode = mode or config.mode()
    app.state.today = today

    conn = connect(app.state.db_path)
    try:
        init_schema(conn)
        if app.state.mode == "demo" and not store.has_imports(conn):
            import_file(conn, config.DEMO_XLSX.read_bytes(), config.DEMO_XLSX.name, today())
    finally:
        conn.close()

    def get_conn() -> Iterator:
        c = connect(app.state.db_path)
        try:
            yield c
        finally:
            c.close()

    def render(request: Request, name: str, status_code: int = 200, **context):
        context["demo_mode"] = app.state.mode == "demo"
        return templates.TemplateResponse(request, name, context, status_code=status_code)

    @app.get("/")
    def index():
        return RedirectResponse("/income", status_code=303)

    @app.get("/income")
    def income_page(request: Request, year: int | None = None, conn=Depends(get_conn)):
        all_years = store.years(conn)
        if year is None and all_years:
            year = all_years[0]
        rows = store.load_year(conn, year) if year is not None else []
        try:
            goal_ore, config_error = config.goal_brutto_monthly_ore(app.state.mode), None
        except ValueError as e:
            goal_ore, config_error = config.DEFAULT_GOAL_BRUTTO_MONTHLY_ORE, str(e)
        summary = year_summary(rows, goal_ore) if rows else None
        return render(
            request, "income.html", year=year, years=all_years, summary=summary, config_error=config_error
        )

    def render_import(request: Request, conn, error: str | None = None, status_code: int = 200):
        return render(
            request, "import.html", status_code=status_code,
            error=error, imports=store.list_imports(conn),
        )

    @app.get("/import")
    def import_form(request: Request, conn=Depends(get_conn)):
        return render_import(request, conn)

    @app.post("/import")
    async def import_upload(request: Request, file: UploadFile | None = None, conn=Depends(get_conn)):
        if file is None or not file.filename:
            return render_import(request, conn, "Choose a file to upload.", 400)
        filename = Path(file.filename).name
        if not filename.lower().endswith(".xlsx"):
            return render_import(request, conn, "Only .xlsx files can be imported.", 400)
        data = await file.read(config.MAX_UPLOAD_BYTES + 1)  # kept in memory only, never written to disk
        if len(data) > config.MAX_UPLOAD_BYTES:
            return render_import(request, conn, "File is larger than 5 MB.", 400)
        try:
            outcome = import_file(conn, data, filename, app.state.today(), config.header_aliases())
        except (IncomeImportError, ValueError) as e:
            return render_import(request, conn, str(e), 400)
        suffix = "?identical=1" if outcome.identical else ""
        return RedirectResponse(f"/imports/{outcome.import_id}{suffix}", status_code=303)

    @app.get("/imports/{import_id}")
    def import_result(request: Request, import_id: int, identical: bool = False, conn=Depends(get_conn)):
        info = store.get_import(conn, import_id)
        if info is None:
            raise HTTPException(status_code=404, detail="Import not found")
        return render(request, "import_result.html", info=info, identical=identical)

    return app
