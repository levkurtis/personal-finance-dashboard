"""App configuration, read from the environment at call time so tests can override it.

Personal settings (real sheet header names, the real brutto goal) live in the gitignored
`finance.local.toml` — see `finance.local.example.toml`. The public code only has placeholders.
"""

import os
import tomllib
from pathlib import Path

from finance.money import to_ore

ROOT = Path(__file__).resolve().parents[2]
DEMO_XLSX = ROOT / "demo" / "Financial 2026.xlsx"

# Placeholder brutto goal per month (øre). Always used in demo mode; the real goal is local config.
DEFAULT_GOAL_BRUTTO_MONTHLY_ORE = 5_500_000

# Uploads larger than this are rejected before parsing.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def mode() -> str:
    """'demo' (fake data) or 'real'. Set with FINANCE_MODE=demo."""
    return "demo" if os.environ.get("FINANCE_MODE", "").strip().lower() == "demo" else "real"


def db_path() -> Path:
    """FINANCE_DB overrides; otherwise data/demo.db or data/finance.db (data/ is gitignored)."""
    if override := os.environ.get("FINANCE_DB"):
        return Path(override)
    return ROOT / "data" / ("demo.db" if mode() == "demo" else "finance.db")


def local_config_path() -> Path:
    """FINANCE_LOCAL_CONFIG overrides; otherwise finance.local.toml in the repo root."""
    return Path(os.environ.get("FINANCE_LOCAL_CONFIG") or ROOT / "finance.local.toml")


def local_settings() -> dict:
    """The local config as a dict ({} if the file doesn't exist). Raises ValueError if invalid."""
    path = local_config_path()
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{path.name} is not valid TOML: {e}") from None


def header_aliases() -> dict[str, list[str]]:
    """Source key -> extra sheet headers, from [income.header_aliases] in the local config."""
    raw = local_settings().get("income", {}).get("header_aliases", {})
    if not isinstance(raw, dict):
        raise ValueError("[income.header_aliases] must be a table of key = [\"header\", ...].")
    aliases = {}
    for key, value in raw.items():
        headers = [value] if isinstance(value, str) else value
        if not isinstance(headers, list) or not all(isinstance(h, str) for h in headers):
            raise ValueError(f'Header aliases for "{key}" must be a string or a list of strings.')
        aliases[key] = headers
    return aliases


def goal_brutto_monthly_ore(app_mode: str) -> int:
    """The monthly brutto goal. Demo mode always uses the placeholder so screenshots never show
    the real goal; real mode uses [goals] brutto_monthly_kr from the local config if set."""
    if app_mode == "demo":
        return DEFAULT_GOAL_BRUTTO_MONTHLY_ORE
    value = local_settings().get("goals", {}).get("brutto_monthly_kr")
    if value is None:
        return DEFAULT_GOAL_BRUTTO_MONTHLY_ORE
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("[goals] brutto_monthly_kr must be a number (kroner).")
    return to_ore(value)
