"""
Matplotlib PNG charts.

Light, recessive chrome; thin 2px lines; categorical colors assigned in a
fixed order so the same entity keeps the same color across every chart.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend: no display needed for scheduled runs
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .analytics import RelativePerf, display_name, value_asof
from .config import (BENCHMARK_TICKER, CURVE_TENORS, FRED_SERIES, INDEX_TICKER,
                     QUARTER, SUBJECT_TICKER, TENOR_YEARS, WEEK)
from .fomc import FomcOutlook
from .theme import AXIS, GRID, INK, INK_2, MUTED, S1, S2, S3, S4, SURFACE

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"],
    "font.size": 10, "axes.edgecolor": AXIS, "axes.labelcolor": INK_2,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.titlelocation": "left", "axes.titlepad": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2, "ytick.left": False,
    "legend.frameon": False, "legend.fontsize": 9, "lines.linewidth": 2,
})

FIG_W = 7.2  # inches; rendered at 2x DPI so it stays crisp at ~600px in email


def _finish(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path


def _date_axis(ax, years: float):
    if years > 1.2:
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))


def _end_label(ax, s: pd.Series, text: str, color: str, dy: float = 0):
    """Direct label at the right end of a line (selective labeling)."""
    ax.annotate(text, xy=(s.index[-1], s.iloc[-1]), xytext=(6, dy),
                textcoords="offset points", va="center", fontsize=9, color=INK_2,
                fontweight="bold")
    ax.plot([s.index[-1]], [s.iloc[-1]], "o", ms=5, color=color,
            markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=5)


def chart_treasuries(fred: dict[str, pd.Series], path: Path, years: int) -> Path | None:
    """Top: 2Y/10Y/30Y yields. Bottom: 2s10s spread (separate axis, no dual-y)."""
    need = ["DGS2", "DGS10", "DGS30"]
    if any(k not in fred for k in need):
        return None
    start = pd.Timestamp.today() - pd.DateOffset(years=years)
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(FIG_W, 5.4), sharex=True,
                                  gridspec_kw={"height_ratios": [2.2, 1]})
    for sid, lbl, c, dy in [("DGS30", "30Y", S4, 4), ("DGS10", "10Y", S1, -4), ("DGS2", "2Y", S2, 0)]:
        s = fred[sid][fred[sid].index >= start]
        ax.plot(s.index, s.values, color=c, label=lbl)
        _end_label(ax, s, f"{lbl} {s.iloc[-1]:.2f}%", c, dy)
    ax.set_title("US Treasury yields (%)")
    ax.legend(loc="upper left", ncol=3)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.1f}%")

    spread = ((fred["DGS10"] - fred["DGS2"]).dropna() * 100)
    spread = spread[spread.index >= start]
    ax2.axhline(0, color=AXIS, lw=1)
    ax2.fill_between(spread.index, spread.values, 0, where=spread.values >= 0,
                     color=S1, alpha=0.15, lw=0)
    ax2.fill_between(spread.index, spread.values, 0, where=spread.values < 0,
                     color=S2, alpha=0.15, lw=0)
    ax2.plot(spread.index, spread.values, color=INK_2, lw=1.5)
    _end_label(ax2, spread, f"{spread.iloc[-1]:+.0f} bp", INK_2)
    ax2.set_title("2s10s slope (bp)  -  positive = upward-sloping", fontsize=10)
    _date_axis(ax2, years)
    ax.margins(x=0.01)
    fig.subplots_adjust(right=0.86)
    return _finish(fig, path)


def chart_curve_snapshot(fred: dict[str, pd.Series], path: Path) -> Path | None:
    """Yield curve today vs one week and one quarter ago."""
    avail = [(sid, yrs) for sid, yrs in zip(CURVE_TENORS, TENOR_YEARS) if sid in fred]
    if len(avail) < 5:
        return None
    last = min(fred[sid].index[-1] for sid, _ in avail)
    fig, ax = plt.subplots(figsize=(FIG_W, 3.6))
    for when, lbl, c, lw in [(last - QUARTER, "1 quarter ago", S3, 1.6),
                             (last - WEEK, "1 week ago", S2, 1.6),
                             (last, f"Latest ({last:%b %d})", S1, 2.4)]:
        x = [yrs for _, yrs in avail]
        y = [value_asof(fred[sid], when) for sid, _ in avail]
        ax.plot(x, y, color=c, lw=lw, marker="o", ms=4.5, label=lbl,
                markeredgecolor=SURFACE, markeredgewidth=1)
    ax.set_xscale("log")
    ax.set_xticks([yrs for _, yrs in avail])
    ax.set_xticklabels([FRED_SERIES[sid] for sid, _ in avail])
    ax.minorticks_off()
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.2f}%")
    ax.set_title("Treasury yield curve")
    ax.legend(loc="best")
    return _finish(fig, path)


def chart_deposits_loans(fred: dict[str, pd.Series], path: Path, years: int) -> Path | None:
    """Deposits vs loans ($tn, same units => one axis) + loan-to-deposit ratio."""
    dep, ln = fred.get("DPSACBW027SBOG"), fred.get("TOTLL")
    if dep is None or ln is None:
        return None
    start = pd.Timestamp.today() - pd.DateOffset(years=years)
    dep, ln = dep[dep.index >= start] / 1000, ln[ln.index >= start] / 1000
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(FIG_W, 5.0), sharex=True,
                                  gridspec_kw={"height_ratios": [2, 1]})
    ax.plot(dep.index, dep.values, color=S1, label="Deposits")
    ax.plot(ln.index, ln.values, color=S2, label="Loans & leases")
    _end_label(ax, dep, f"${dep.iloc[-1]:.2f}tn", S1)
    _end_label(ax, ln, f"${ln.iloc[-1]:.2f}tn", S2)
    ax.set_title("All commercial banks: deposits vs loans ($ trillions, SA)")
    ax.legend(loc="center left")
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:.1f}tn")

    ldr = (ln / dep * 100).dropna()
    ax2.plot(ldr.index, ldr.values, color=INK_2, lw=1.5)
    _end_label(ax2, ldr, f"{ldr.iloc[-1]:.1f}%", INK_2)
    ax2.set_title("Loan-to-deposit ratio (%)", fontsize=10)
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.1f}%")
    _date_axis(ax2, years)
    ax.margins(x=0.01)
    fig.subplots_adjust(right=0.86)
    return _finish(fig, path)


def chart_equities(px: pd.DataFrame, path: Path) -> Path | None:
    """1-year price return, indexed to 100. Subject bank emphasized; SPY muted."""
    series = [(SUBJECT_TICKER, S1, 2.6), (INDEX_TICKER, S2, 1.8), ("XLF", S3, 1.8),
              (BENCHMARK_TICKER, MUTED, 1.4)]
    series = [x for x in series if x[0] in px.columns]
    if not series:
        return None
    start = px.index[-1] - pd.Timedelta(days=365)
    sub = px[px.index >= start]
    fig, ax = plt.subplots(figsize=(FIG_W, 3.8))
    ax.axhline(100, color=AXIS, lw=1)
    ends = []
    for t, c, lw in series:
        s = sub[t].dropna()
        s = s / s.iloc[0] * 100
        ax.plot(s.index, s.values, color=c, lw=lw, label=display_name(t))
        ends.append((s, display_name(t), c))
    # stagger end labels to avoid collisions
    ends.sort(key=lambda e: e[0].iloc[-1])
    prev = None
    for s, t, c in ends:
        dy = 0
        if prev is not None and abs(s.iloc[-1] - prev) < 2.5:
            dy = 8
        _end_label(ax, s, f"{t} {s.iloc[-1] - 100:+.0f}%", c, dy)
        prev = s.iloc[-1]
    ax.set_title("Bank equities: 1-year price return (indexed to 100)")
    ax.legend(loc="upper left", ncol=len(series))
    _date_axis(ax, 1)
    ax.margins(x=0.01)
    fig.subplots_adjust(right=0.84)
    return _finish(fig, path)


def chart_subject_vs_index(px: pd.DataFrame, rel: RelativePerf | None, path: Path) -> Path | None:
    """Top: EBC and KRX indexed to 100 (1Y). Bottom: EBC relative to KRX, %."""
    if rel is None:
        return None
    df = px[[SUBJECT_TICKER, INDEX_TICKER]].dropna()
    df = df[df.index >= rel.rel_series.index[0]]
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(FIG_W, 5.0), sharex=True,
                                  gridspec_kw={"height_ratios": [2, 1.1]})
    ax.axhline(100, color=AXIS, lw=1)
    ends = []
    for t, c, lw in [(SUBJECT_TICKER, S1, 2.4), (INDEX_TICKER, S2, 1.8)]:
        s = df[t] / df[t].iloc[0] * 100
        ax.plot(s.index, s.values, color=c, lw=lw, label=display_name(t))
        ends.append((s, display_name(t), c))
    gap = ends[0][0].iloc[-1] - ends[1][0].iloc[-1]
    for (s, name, c), sign in zip(ends, (1, -1)):
        dy = 7 * sign * (1 if gap >= 0 else -1) if abs(gap) < 4 else 0
        _end_label(ax, s, f"{name} {s.iloc[-1] - 100:+.1f}%", c, dy)
    ax.set_title(f"{SUBJECT_TICKER} vs KBW Nasdaq Regional Bank Index (KRX), 1Y, indexed to 100")
    ax.legend(loc="upper left", ncol=2)

    r = rel.rel_series
    ax2.axhline(0, color=AXIS, lw=1)
    ax2.fill_between(r.index, r.values, 0, where=r.values >= 0, color=S1, alpha=0.15, lw=0)
    ax2.fill_between(r.index, r.values, 0, where=r.values < 0, color=S2, alpha=0.15, lw=0)
    ax2.plot(r.index, r.values, color=INK_2, lw=1.5)
    _end_label(ax2, r, f"{r.iloc[-1]:+.1f} pts", INK_2)
    ax2.set_title(f"{SUBJECT_TICKER} minus KRX cumulative return (pts)  -  above 0 = outperforming", fontsize=10)
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:+.0f}")
    _date_axis(ax2, 1)
    ax.margins(x=0.01)
    fig.subplots_adjust(right=0.84)
    return _finish(fig, path)


def chart_fomc(outlook: list[FomcOutlook], path: Path) -> Path | None:
    """Market-implied cumulative change in fed funds by meeting (bp)."""
    if not outlook:
        return None
    fig, ax = plt.subplots(figsize=(FIG_W, 2.8))
    labels = [o.meeting.strftime("%b %d\n%Y") for o in outlook]
    vals = [o.cumulative_bp for o in outlook]
    bars = ax.bar(labels, vals, width=0.5, color=S1, edgecolor=SURFACE, linewidth=2)
    ax.axhline(0, color=AXIS, lw=1)
    for b, v in zip(bars, vals):
        ax.annotate(f"{v:+.0f} bp", (b.get_x() + b.get_width() / 2, v),
                    xytext=(0, 4 if v >= 0 else -12), textcoords="offset points",
                    ha="center", fontsize=9, color=INK_2, fontweight="bold")
    lo, hi = min(vals + [0]), max(vals + [0])
    pad = max(8, (hi - lo) * 0.25)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_title("Implied cumulative change in fed funds by FOMC meeting (bp)")
    return _finish(fig, path)
