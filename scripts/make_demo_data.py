"""Write a fake "Financial <year>.xlsx" to demo/. Usage: uv run python scripts/make_demo_data.py [--seed N]"""

import argparse
from pathlib import Path

from finance.demo import build_demo_workbook

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, help="default: demo/Financial <year>.xlsx")
    args = parser.parse_args()

    out = args.out or ROOT / "demo" / f"Financial {args.year}.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb, _ = build_demo_workbook(args.year, args.seed)
    wb.save(out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
