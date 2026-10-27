"""Static settings (series, tickers, FOMC calendar) and env-driven runtime config."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


# FRED series used by the dashboard. Daily series are business-day data;
# H.8 series are weekly (Wednesday), seasonally adjusted (SA), in $ billions
FRED_SERIES: dict[str, str] = {
    # Treasury constant-maturity curve (daily, %)
    "DGS1MO": "1M", "DGS3MO": "3M", "DGS6MO": "6M", "DGS1": "1Y",
    "DGS2": "2Y", "DGS3": "3Y", "DGS5": "5Y", "DGS7": "7Y",
    "DGS10": "10Y", "DGS20": "20Y", "DGS30": "30Y",
    # Funding / policy rates (daily, %)
    "SOFR": "SOFR",
    "EFFR": "Effective Fed Funds",
    "DFEDTARL": "Fed Funds Target (Lower)",
    "DFEDTARU": "Fed Funds Target (Upper)",
    # Mortgage rate (weekly, %) 
    "MORTGAGE30US": "30Y Mortgage (Freddie Mac PMMS)",
    # H.8 Assets & Liabilities of Commercial Banks (weekly, SA, $bn)
    "DPSACBW027SBOG": "Deposits, All Commercial Banks",
    "TOTLL": "Loans & Leases in Bank Credit, All Commercial Banks",
    "DPSSCBW027SBOG": "Deposits, Small Domestic Banks",
    "LLBSCBW027SBOG": "Loans & Leases, Small Domestic Banks",
}

CURVE_TENORS = ["DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2", "DGS3",
                "DGS5", "DGS7", "DGS10", "DGS20", "DGS30"]
TENOR_YEARS = [1 / 12, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]

# Equities: subject bank, sector ETFs, broad-market benchmark, peers.
SUBJECT_TICKER = (os.getenv("SUBJECT_TICKER") or "EBC").strip().upper()  # override via SUBJECT_TICKER
INDEX_TICKER = "^KRX"                          # KBW Nasdaq Regional Banking Index (primary benchmark)
SECTOR_TICKERS = ["KRE", "KBE", "XLF"]         # regional banks, banks, financials
BENCHMARK_TICKER = "SPY"
DEFAULT_PEERS = ["INDB", "WBS", "CFG"]         # Peers (override via PEER_TICKERS)

# Scheduled FOMC meetings, as (first day, decision day). Need to update this list each year. 
# See https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_MEETINGS: list[tuple[date, date]] = [
    (date(2026, 1, 27), date(2026, 1, 28)), (date(2026, 3, 17), date(2026, 3, 18)),
    (date(2026, 4, 28), date(2026, 4, 29)), (date(2026, 6, 16), date(2026, 6, 17)),
    (date(2026, 7, 28), date(2026, 7, 29)), (date(2026, 9, 15), date(2026, 9, 16)),
    (date(2026, 10, 27), date(2026, 10, 28)), (date(2026, 12, 8), date(2026, 12, 9)),
    (date(2027, 1, 26), date(2027, 1, 27)), (date(2027, 3, 16), date(2027, 3, 17)),
    (date(2027, 4, 27), date(2027, 4, 28)), (date(2027, 6, 8), date(2027, 6, 9)),
    (date(2027, 7, 27), date(2027, 7, 28)), (date(2027, 9, 14), date(2027, 9, 15)),
    (date(2027, 10, 26), date(2027, 10, 27)), (date(2027, 12, 7), date(2027, 12, 8)),
]

WEEK = pd.Timedelta(days=7)
QUARTER = pd.Timedelta(days=91)
STALE_PRICE_DAYS = pd.Timedelta(days=5) 


@dataclass
class Config:
    """Runtime configuration, sourced from environment variables."""

    fred_api_key: str | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_ssl: bool = False              # True => implicit TLS (port 465); else STARTTLS
    email_from: str | None = None
    email_to: list[str] = field(default_factory=list)
    email_cc: list[str] = field(default_factory=list)
    peers: list[str] = field(default_factory=lambda: list(DEFAULT_PEERS))
    lookback_years: int = 2
    fomc_meetings_shown: int = 4

    @classmethod
    def from_env(cls) -> "Config":
        def _list(name: str, default: Iterable[str] = ()) -> list[str]:
            raw = os.getenv(name)
            if raw is None:
                return list(default)
            return [x.strip() for x in raw.split(",") if x.strip()]

        return cls(
            fred_api_key=os.getenv("FRED_API_KEY") or None,
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER") or None,
            smtp_password=os.getenv("SMTP_PASSWORD") or None,
            smtp_use_ssl=os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"},
            email_from=os.getenv("EMAIL_FROM") or os.getenv("SMTP_USER") or None,
            email_to=_list("EMAIL_TO"),
            email_cc=_list("EMAIL_CC"),
            peers=_list("PEER_TICKERS", DEFAULT_PEERS),
            lookback_years=int(os.getenv("LOOKBACK_YEARS", "2")),
        )
