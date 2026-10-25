"""Data access: FRED JSON API and Yahoo Finance daily closes."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Iterable

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import STALE_PRICE_DAYS

try:
    import yfinance as yf
except ImportError:  # equities/futures sections degrade gracefully
    yf = None

log = logging.getLogger(__name__)


def _http_session() -> requests.Session:
    """requests session with retry/backoff for transient 429/5xx errors."""
    retry = Retry(total=4, backoff_factor=1.0,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = "bank-dashboard/1.0 (+weekly research report)"
    return s


class FredClient:
    """Minimal client for the official FRED JSON API (free key required)."""

    API_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str, session: requests.Session | None = None):
        self.api_key = api_key
        self.session = session or _http_session()

    def series(self, series_id: str, start: date) -> pd.Series:
        try:
            r = self.session.get(self.API_URL, timeout=30, params={
                "series_id": series_id, "api_key": self.api_key,
                "file_type": "json", "observation_start": start.isoformat(),
            })
            if r.status_code == 400:
                # FRED returns 400 with a JSON error_message for bad keys / unknown series
                raise ValueError(r.json().get("error_message", r.text))
            r.raise_for_status()
        except requests.RequestException as exc:
            # requests puts the full URL (including api_key) in its error messages;
            # re-raise without the original so the key never reaches the logs.
            raise RuntimeError(str(exc).replace(self.api_key, "***")) from None
        # During outages FRED answers 200 with an HTML maintenance page instead of JSON
        if "json" not in r.headers.get("content-type", ""):
            raise ValueError("FRED returned HTML instead of JSON (likely site maintenance); "
                             "check https://fred.stlouisfed.org and retry later")
        df = pd.DataFrame(r.json().get("observations", []), columns=["date", "value"])

        # FRED encodes missing observations (holidays etc.) as "."
        s = pd.Series(pd.to_numeric(df["value"], errors="coerce").values,
                      index=pd.to_datetime(df["date"]), name=series_id)
        s = s.dropna().sort_index()
        s = s[~s.index.duplicated(keep="last")]
        if s.empty:
            raise ValueError(f"FRED returned no data for {series_id}")
        return s

    def many(self, series_ids: Iterable[str], start: date) -> dict[str, pd.Series]:
        """Fetch several series concurrently; failures are logged and skipped."""
        def _one(sid: str) -> tuple[str, pd.Series | None]:
            try:
                return sid, self.series(sid, start)
            except Exception as exc:  # noqa: BLE001 - one bad series must not kill the report
                log.error("FRED %s failed: %s", sid, exc)
                return sid, None

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = dict(pool.map(_one, series_ids))
        return {k: v for k, v in results.items() if v is not None}


def fetch_prices(tickers: list[str], start: date) -> pd.DataFrame:
    """
    Daily closes from Yahoo Finance, split-adjusted but NOT dividend-adjusted.
    Price returns keep stocks/ETFs comparable with ^KRX, which is a price index.
    """
    if yf is None:
        log.error("yfinance not installed; skipping equities.")
        return pd.DataFrame()
    try:
        data = yf.download(tickers, start=start.isoformat(), auto_adjust=False,
                           progress=False, group_by="column", threads=True)
    except Exception as exc:  # noqa: BLE001
        log.error("Yahoo Finance download failed: %s", exc)
        return pd.DataFrame()
    if data is None or data.empty:
        return pd.DataFrame()
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close.index = pd.to_datetime(close.index).tz_localize(None)
    missing = [t for t in tickers if t not in close.columns or close[t].dropna().empty]
    if missing:
        log.warning("No price data for: %s", ", ".join(missing))
    close = close.dropna(axis=1, how="all")

    # Drop tickers whose last real print lags the freshest ticker by more than
    # a few days (delisted / halted / feed gap); ffill would otherwise present
    # an old price as current with a 0% weekly move.
    last_seen = close.apply(lambda c: c.last_valid_index())
    stale = last_seen[last_seen < last_seen.max() - STALE_PRICE_DAYS]
    if not stale.empty:
        log.warning("Dropping stale tickers (no recent prices): %s", ", ".join(
            f"{t} (last {d:%Y-%m-%d})" for t, d in stale.items()))
        close = close.drop(columns=stale.index)
    return close.ffill()
