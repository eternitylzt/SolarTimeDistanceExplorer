"""Allow ``python -m app`` and source-mode automatic restarts."""

from app.bootstrap import run


if __name__ == "__main__":
    raise SystemExit(run())
