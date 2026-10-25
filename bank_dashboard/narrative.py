"""Rule-based, plain-English trend summaries for the top of the report."""

from __future__ import annotations

from html import escape

from .analytics import EquityRow, Metric, RelativePerf, find_metric
from .config import SUBJECT_TICKER
from .fomc import FomcOutlook


def build_highlights(rates: list[Metric], banks: list[Metric], eq: list[EquityRow],
                     fomc: list[FomcOutlook], rel: RelativePerf | None = None) -> list[str]:
    """Plain-English bullets on what moved this week (HTML-safe strings)."""
    out = []
    ten, two, s210 = (find_metric(rates, "10Y Treasury"), find_metric(rates, "2Y Treasury"),
                      find_metric(rates, "2s10s Spread"))
    if ten and two and s210:
        shape = "steepened" if s210.wow > 0.5 else "flattened" if s210.wow < -0.5 else "was little changed"
        out.append(f"Curve {shape}: 2Y {two.wow:+.0f} bp to {two.value:.2f}%, 10Y {ten.wow:+.0f} bp "
                   f"to {ten.value:.2f}%; 2s10s at {s210.value * 100:+.0f} bp ({s210.wow:+.0f} bp WoW, "
                   f"{s210.qoq:+.0f} bp QoQ).")
    sofr, effr = find_metric(rates, "SOFR"), find_metric(rates, "Effective Fed Funds")
    if sofr and effr:
        gap = (sofr.value - effr.value) * 100
        tone = ("elevated - watch repo/funding pressure" if gap > 5
                else "contained" if gap > -5 else "soft")
        out.append(f"Funding: SOFR {sofr.value:.2f}% vs EFFR {effr.value:.2f}% "
                   f"({gap:+.0f} bp spread, {tone}).")
    dep, ln = find_metric(banks, "Deposits - All Banks"), find_metric(banks, "Loans & Leases - All Banks")
    if dep and ln:
        out.append(f"H.8 (week of {dep.asof:%b %d}): deposits {dep.wow:+,.0f}bn WoW "
                   f"({dep.wow_pct:+.2f}%), {dep.qoq_pct:+.2f}% QoQ; loans {ln.wow:+,.0f}bn WoW "
                   f"({ln.wow_pct:+.2f}%), {ln.qoq_pct:+.2f}% QoQ.")
    sdep = find_metric(banks, "Deposits - Small Banks")
    if sdep:
        out.append(f"Small-bank deposits ({SUBJECT_TICKER}'s peer cohort) {sdep.wow_pct:+.2f}% WoW, "
                   f"{sdep.qoq_pct:+.2f}% QoQ.")
    if rel is not None:
        h = {lbl: (s, b) for lbl, s, b in rel.horizons}
        (s1w, b1w), (sytd, bytd) = h["1 week"], h["YTD"]
        verb = "outperformed" if s1w > b1w else "underperformed"
        out.append(f"{rel.subject} {s1w:+.1f}% on the week, {verb} the KRX regional bank "
                   f"index ({b1w:+.1f}%) by {abs(s1w - b1w):.1f} pts; YTD {sytd:+.1f}% vs "
                   f"KRX {bytd:+.1f}% ({sytd - bytd:+.1f} pts). 1Y beta to KRX {rel.beta_1y:.2f}.")
    if fomc:
        n = fomc[0]
        lead = ("cut" if n.p_cut >= max(n.p_hold, n.p_hike)
                else "hike" if n.p_hike > n.p_hold else "hold")
        p = {"cut": n.p_cut, "hold": n.p_hold, "hike": n.p_hike}[lead]
        tail = (f"; {fomc[-1].cumulative_bp:+.0f} bp cumulative priced through "
                f"{fomc[-1].meeting:%b %Y}") if len(fomc) > 1 else ""
        out.append(f"FOMC {n.meeting:%b %d}: futures imply {p:.0%} probability of a "
                   f"{lead}{tail}.")
    return [escape(x) for x in out]
