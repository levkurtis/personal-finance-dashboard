"""Entry point for `uv run finance`. Always bound to 127.0.0.1: this app is local-only."""

import uvicorn

from finance.app import create_app


def main() -> None:
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
