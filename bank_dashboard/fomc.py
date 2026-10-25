"""
FOMC expectations from 30-Day Fed Funds futures (CBOT: ZQ).

A ZQ contract settles to 100 - (average daily EFFR over the contract month),
so each month's price gives the market's expected average rate for that
month. This mirrors the CME FedWatch methodology (CME's own data feed is
a paid product):

  * If the month after a meeting has no meeting, that whole month is
    "post-meeting", so its contract gives the post-meeting rate directly.
  * Otherwise, split the meeting month's average into pre/post pieces:
        avg = (d/N)*r_pre + ((N-d)/N)*r_post
    where d = days in the month before the new rate takes effect and N =
    days in the month. Solve for r_post.
  * r_pre for each meeting is the previous meeting's r_post (chained),
    starting from the current EFFR.
  * The expected move (r_post - r_pre) in 25bp units gives the probability
    split between the two nearest outcomes (e.g. -0.6 => 60% cut / 40% hold).
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .config import FOMC_MEETINGS

try:
    import yfinance as yf
except ImportError:  # FOMC section falls back to a 2Y-vs-EFFR proxy
    yf = None

log = logging.getLogger(__name__)

ZQ_MONTH_CODES = "FGHJKMNQUVXZ"


def zq_ticker(year: int, month: int) -> str:
    return f"ZQ{ZQ_MONTH_CODES[month - 1]}{year % 100:02d}.CBT"


@dataclass
class FomcOutlook:
    meeting: date                # decision day
    rate_pre: float              # expected EFFR going into the meeting
    rate_post: float             # expected EFFR after the meeting
    p_cut: float                 # probability of a cut (any size)
    p_hold: float
    p_hike: float
    cumulative_bp: float         # expected change vs today's EFFR
    likely_range: str            # most likely target range after the meeting


def _month_iter(start: date, n: int):
    y, m = start.year, start.month
    for _ in range(n):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def fetch_zq_curve(n_months: int = 10) -> dict[tuple[int, int], float]:
    """Implied average EFFR (%) for the next `n_months` contract months."""
    if yf is None:
        return {}
    months = list(_month_iter(date.today(), n_months))
    tickers = [zq_ticker(y, m) for y, m in months]
    try:
        data = yf.download(tickers, period="10d", progress=False,
                           auto_adjust=False, group_by="column", threads=True)
    except Exception as exc:  # noqa: BLE001
        log.error("Fed Funds futures download failed: %s", exc)
        return {}
    if data is None or data.empty:
        return {}
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    out = {}
    for (y, m), t in zip(months, tickers):
        if t in close.columns and close[t].dropna().size:
            out[(y, m)] = 100.0 - float(close[t].dropna().iloc[-1])
    if len(out) < n_months:
        log.warning("Fed Funds futures: got %d/%d contract months", len(out), n_months)
    return out


def _split_move(x: float) -> tuple[float, float, float]:
    """Expected move in 25bp steps -> (p_cut, p_hold, p_hike) across two outcomes."""
    if abs(x) < 1e-9:
        return 0.0, 1.0, 0.0
    mag = min(abs(x), 1.0)  # >=1 step means a move is fully priced (possibly 50bp)
    return (mag, 1 - mag, 0.0) if x < 0 else (0.0, 1 - mag, mag)


def compute_fomc_outlook(zq: dict[tuple[int, int], float], effr: float,
                         target_lo: float, n_meetings: int) -> list[FomcOutlook]:
    today = date.today()
    meetings = [d for _, d in FOMC_MEETINGS if d >= today][:n_meetings]
    meeting_months = {(d.year, d.month) for _, d in FOMC_MEETINGS}
    out: list[FomcOutlook] = []
    r_pre = effr
    for d in meetings:
        ym = (d.year, d.month)
        nxt = (d.year + (d.month == 12), d.month % 12 + 1)
        N = calendar.monthrange(d.year, d.month)[1]
        days_pre = d.day  # new rate is effective the day after the decision
        if nxt in zq and nxt not in meeting_months:
            r_post = zq[nxt]
        elif ym in zq and N - days_pre > 0:
            r_post = (zq[ym] - r_pre * days_pre / N) / ((N - days_pre) / N)
        else:
            log.warning("No futures data to price the %s meeting; stopping.", d)
            break
        steps = (r_post - r_pre) / 0.25
        p_cut, p_hold, p_hike = _split_move(steps)
        cum_steps = (r_post - effr) / 0.25
        lo = target_lo + 0.25 * round(cum_steps)
        out.append(FomcOutlook(d, r_pre, r_post, p_cut, p_hold, p_hike,
                               (r_post - effr) * 100, f"{lo:.2f}-{lo + 0.25:.2f}%"))
        r_pre = r_post
    return out
