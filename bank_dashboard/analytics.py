"""
Metrics: WoW / QoQ changes, H.8 levels, equity returns, subject-vs-index stats.

WoW / QoQ are measured from the latest observation back 7 / 91 calendar
days using as-of lookups, so daily, weekly and holiday-gapped series are
all handled the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import INDEX_TICKER, QUARTER, WEEK


def value_asof(s: pd.Series, when: pd.Timestamp) -> float:
    """Last observation on or before `when` (NaN if none)."""
    s = s.dropna()
    if s.empty or when < s.index[0]:
        return float("nan")
    return float(s.asof(when))


@dataclass
class Metric:
    """A single dashboard line item with WoW / QoQ comparisons."""

    label: str
    value: float
    asof: pd.Timestamp
    wow: float          
    qoq: float
    wow_pct: float = float("nan")
    qoq_pct: float = float("nan")
    kind: str = "rate"  


def make_metric(label: str, s: pd.Series | None, kind: str = "rate") -> Metric | None:
    if s is None or s.dropna().empty:
        return None
    s = s.dropna()
    t, v = s.index[-1], float(s.iloc[-1])
    w, q = value_asof(s, t - WEEK), value_asof(s, t - QUARTER)
    scale = 100.0 if kind == "rate" else 1.0  # rates: report changes in bp
    m = Metric(label, v, t, (v - w) * scale, (v - q) * scale, kind=kind)
    if kind == "level":
        m.wow_pct = (v / w - 1) * 100 if w else float("nan")
        m.qoq_pct = (v / q - 1) * 100 if q else float("nan")
    return m


def find_metric(ms: list[Metric], label: str) -> Metric | None:
    return next((m for m in ms if m.label == label), None)


def build_rate_metrics(fred: dict[str, pd.Series]) -> list[Metric]:
    g = fred.get
    out = [
        make_metric("2Y Treasury", g("DGS2")),
        make_metric("10Y Treasury", g("DGS10")),
        make_metric("30Y Treasury", g("DGS30")),
        make_metric("SOFR", g("SOFR")),
        make_metric("Effective Fed Funds", g("EFFR")),
        make_metric("30Y Mortgage", g("MORTGAGE30US")),
    ]
    # Curve spreads: computed on aligned dates so holidays don't create gaps
    if g("DGS10") is not None and g("DGS2") is not None:
        out.append(make_metric("2s10s Spread", (g("DGS10") - g("DGS2")).dropna()))
    if g("DGS10") is not None and g("DGS3MO") is not None:
        out.append(make_metric("3m10y Spread", (g("DGS10") - g("DGS3MO")).dropna()))
    if g("SOFR") is not None and g("EFFR") is not None:
        out.append(make_metric("SOFR - EFFR", (g("SOFR") - g("EFFR")).dropna()))
    return [m for m in out if m]


def build_bank_metrics(fred: dict[str, pd.Series]) -> list[Metric]:
    g = fred.get
    out = [
        make_metric("Deposits - All Banks", g("DPSACBW027SBOG"), "level"),
        make_metric("Loans & Leases - All Banks", g("TOTLL"), "level"),
        make_metric("Deposits - Small Banks", g("DPSSCBW027SBOG"), "level"),
        make_metric("Loans & Leases - Small Banks", g("LLBSCBW027SBOG"), "level"),
    ]
    return [m for m in out if m]


@dataclass
class EquityRow:
    ticker: str
    price: float
    ret_1w: float
    ret_qoq: float
    ret_ytd: float
    off_52w_high: float


def build_equity_table(px: pd.DataFrame, tickers: list[str]) -> list[EquityRow]:
    rows = []
    for t in tickers:
        if t not in px.columns:
            continue
        s = px[t].dropna()
        if len(s) < 5:
            continue
        last_t, last = s.index[-1], float(s.iloc[-1])
        ytd_base = value_asof(s, pd.Timestamp(last_t.year - 1, 12, 31))
        hi = float(s[s.index >= last_t - pd.Timedelta(days=365)].max())
        rows.append(EquityRow(
            ticker=t, price=last,
            ret_1w=(last / value_asof(s, last_t - WEEK) - 1) * 100,
            ret_qoq=(last / value_asof(s, last_t - QUARTER) - 1) * 100,
            ret_ytd=(last / ytd_base - 1) * 100,
            off_52w_high=(last / hi - 1) * 100,
        ))
    return rows


def display_name(ticker: str) -> str:
    return "KRX" if ticker == INDEX_TICKER else ticker


@dataclass
class RelativePerf:
    """Subject bank vs benchmark index across standard horizons."""

    subject: str
    bench: str
    horizons: list[tuple[str, float, float]]  # (label, subject %, bench %)
    beta_1y: float         
    corr_1y: float
    vol_1y_subject: float   # annualized realized volatility
    vol_1y_bench: float
    rel_series: pd.Series   


def build_relative(px: pd.DataFrame, subject: str, bench: str) -> RelativePerf | None:
    if subject not in px.columns or bench not in px.columns:
        return None
    df = px[[subject, bench]].dropna()
    if len(df) < 60:
        return None
    t = df.index[-1]

    def ret(col: str, since: pd.Timestamp) -> float:
        return (df[col].iloc[-1] / value_asof(df[col], since) - 1) * 100

    marks = [("1 week", t - WEEK), ("1 month", t - pd.Timedelta(days=30)),
             ("QoQ (3 months)", t - QUARTER), ("YTD", pd.Timestamp(t.year - 1, 12, 31)),
             ("1 year", t - pd.Timedelta(days=365))]
    horizons = [(lbl, ret(subject, ts), ret(bench, ts)) for lbl, ts in marks]

    yr = df[df.index >= t - pd.Timedelta(days=365)]
    r = yr.pct_change().dropna()
    beta = r[subject].cov(r[bench]) / r[bench].var()
    rel = (yr[subject] / yr[subject].iloc[0] - yr[bench] / yr[bench].iloc[0]) * 100
    return RelativePerf(subject, display_name(bench), horizons, beta,
                        r[subject].corr(r[bench]),
                        r[subject].std() * np.sqrt(252) * 100,
                        r[bench].std() * np.sqrt(252) * 100, rel)
