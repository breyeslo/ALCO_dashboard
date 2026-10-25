"""Command-line entry point: argument parsing, logging setup, exit codes."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from .config import PROJECT_ROOT, Config
from .pipeline import run

log = logging.getLogger(__name__)


class _RedactFilter(logging.Filter):
    """Replaces a secret in log messages before they are written."""

    def __init__(self, secret: str):
        super().__init__()
        self.secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if self.secret in msg:
            record.msg, record.args = msg.replace(self.secret, "***"), None
        return True


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m bank_dashboard",
                                 description="Weekly Economic & Banking Dashboard")
    ap.add_argument("--dry-run", action="store_true", help="build the report but do not email it")
    ap.add_argument("--out", type=Path, default=PROJECT_ROOT / "reports",
                    help="archive folder for HTML/PNG output (default: ./reports)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # noisy per-ticker errors
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    # urllib3 logs request URLs (DEBUG, and WARNING on connection retries),
    # which include the FRED api_key query parameter.
    if key := os.getenv("FRED_API_KEY"):
        for h in logging.getLogger().handlers:
            h.addFilter(_RedactFilter(key))

    try:
        return run(Config.from_env(), args.out, args.dry_run)
    except Exception:  # noqa: BLE001 - top-level guard so schedulers see a clean exit code
        log.exception("Dashboard run failed.")
        return 1
