from datetime import date

import pytest
from fastapi.testclient import TestClient

from finance.app import create_app
from finance.demo import build_demo_workbook, workbook_to_bytes
from finance.money import format_dkk

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TODAY = date(2026, 9, 15)


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=tmp_path / "t.db", mode="real", today=lambda: TODAY)
    return TestClient(app)


def upload(client, data, filename="Financial 2026.xlsx"):
    return client.post("/import", files={"file": (filename, data, XLSX)}, follow_redirects=False)


def test_root_redirects_to_income(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/income"


def test_empty_state(client):
    r = client.get("/income")
    assert r.status_code == 200
    assert "No income imported yet" in r.text
    assert "DEMO DATA" not in r.text


def test_upload_demo_then_income_page(client):
    wb, expected = build_demo_workbook(2026, seed=11)
    r = upload(client, workbook_to_bytes(wb))
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith("/imports/")

    result = client.get(location)
    assert "12 months" in result.text
    assert "First import for 2026" in result.text
    assert "All months match" in result.text

    page = client.get("/income").text
    assert "Income 2026" in page
    assert format_dkk(expected["months"][1]["salary_netto"]) in page
    assert "Sep (est.)" not in page and "Sep" in page
    for m in ("Oct", "Nov", "Dec"):
        assert f"{m} (est.)" in page
    assert "Average brutto (actual months, n=9)" in page
    assert "Goal 55.000,00 kr." in page
    assert "Total (actual)" in page and "Total (incl. est.)" in page
    # Brutto and pension have their own columns; they are not repeated as source columns.
    assert '<th class="num">Salary (brutto)</th>' not in page
    assert page.count('<th class="num">Pension</th>') == 1


def test_reupload_identical_and_changed(client):
    wb, _ = build_demo_workbook(2026, seed=1)
    data = workbook_to_bytes(wb)
    first = upload(client, data).headers["location"]
    again = upload(client, data)
    assert again.headers["location"] == first + "?identical=1"
    assert "identical" in client.get(again.headers["location"]).text

    wb2, _ = build_demo_workbook(2026, seed=2)
    changed = client.get(upload(client, workbook_to_bytes(wb2)).headers["location"]).text
    assert "Changes vs. previous import" in changed and "Salary (brutto)" in changed

    listing = client.get("/import").text
    assert listing.count("details</a>") == 2


@pytest.mark.parametrize(
    "filename, data, message",
    [
        ("notes.txt", b"hello", "Only .xlsx files"),
        ("Financial 2026.xlsx", b"garbage", "Not a valid .xlsx file"),
    ],
)
def test_bad_uploads_rejected(client, filename, data, message):
    r = upload(client, data, filename)
    assert r.status_code == 400
    assert message in r.text
    assert "No imports yet" in r.text


def test_too_large_upload_rejected(client, monkeypatch):
    monkeypatch.setattr("finance.config.MAX_UPLOAD_BYTES", 10)
    r = upload(client, b"x" * 11)
    assert r.status_code == 400 and "larger than 5 MB" in r.text


def test_missing_import_is_404(client):
    assert client.get("/imports/999").status_code == 404


def test_html_is_escaped(client):
    wb, _ = build_demo_workbook(2026)
    r = upload(client, workbook_to_bytes(wb), filename="<script>x</script> 2026.xlsx")
    assert "<script>x" not in client.get(r.headers["location"]).text


def test_demo_mode_auto_imports(tmp_path):
    client = TestClient(create_app(db_path=tmp_path / "demo.db", mode="demo", today=lambda: TODAY))
    page = client.get("/income").text
    assert "DEMO DATA" in page
    assert "Income 2026" in page and "Oct (est.)" in page
    # Restarting doesn't import again.
    create_app(db_path=tmp_path / "demo.db", mode="demo", today=lambda: TODAY)
    assert client.get("/import").text.count("details</a>") == 1


def test_env_config(monkeypatch, tmp_path):
    from finance import config

    monkeypatch.setenv("FINANCE_MODE", "demo")
    monkeypatch.delenv("FINANCE_DB", raising=False)
    assert config.mode() == "demo" and config.db_path().name == "demo.db"
    monkeypatch.setenv("FINANCE_MODE", "")
    assert config.mode() == "real" and config.db_path().name == "finance.db"
    monkeypatch.setenv("FINANCE_DB", str(tmp_path / "x.db"))
    assert config.db_path() == tmp_path / "x.db"


def test_real_mode_uses_local_aliases_and_goal(client, local_config):
    from helpers import make_income_xlsx

    local_config('[income.header_aliases]\nsalary_netto = "Example Corp Pay"\n[goals]\nbrutto_monthly_kr = 61000\n')
    data = make_income_xlsx("2026", ["Salary (Brutto)", "Example Corp Pay"], [["January", 50000, 30000]])
    r = upload(client, data)
    assert r.status_code == 303
    page = client.get("/income").text
    assert "30.000,00 kr." in page
    assert "Goal 61.000,00 kr." in page


def test_invalid_local_config_is_reported_not_crashing(client, local_config):
    wb, _ = build_demo_workbook(2026)
    upload(client, workbook_to_bytes(wb))
    local_config("not = [valid")
    page = client.get("/income")
    assert page.status_code == 200 and "Local config problem" in page.text
    r = upload(client, workbook_to_bytes(build_demo_workbook(2026, seed=5)[0]))
    assert r.status_code == 400 and "not valid TOML" in r.text


def test_demo_mode_ignores_local_config(tmp_path, local_config):
    local_config("not = [valid")  # a broken local file must not break demo mode
    client = TestClient(create_app(db_path=tmp_path / "d.db", mode="demo", today=lambda: TODAY))
    page = client.get("/income").text
    assert "Goal 55.000,00 kr." in page and "Local config problem" not in page
