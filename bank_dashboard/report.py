"""
HTML email and plain-text rendering.

Email clients ignore most modern CSS, so the layout is table-based with
inline styles; a single <style> block adds the mobile breakpoint (supported
by Gmail, Apple Mail, Outlook.com/iOS/Android).
"""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Callable

from .analytics import Metric, RelativePerf, display_name, find_metric
from .config import SUBJECT_TICKER
from .theme import BAD, GOOD, INK, INK_2, MUTED

C = dict(page="#f4f4f1", card="#ffffff", ink=INK, ink2=INK_2, muted=MUTED,
         line="#e6e5df", brand="#00573f", good=GOOD, bad=BAD)


def _fmt_val(m: Metric) -> str:
    if m.kind == "level":
        return f"${m.value / 1000:,.2f}tn"
    if "Spread" in m.label or "SOFR - EFFR" in m.label:
        return f"{m.value * 100:+.0f} bp"
    return f"{m.value:.2f}%"


def _fmt_delta(m: Metric, which: str, color_sense: int = 0) -> str:
    """
    Arrow + number. color_sense: +1 => up is good (green), -1 => up is bad,
    0 => neutral ink (rates: direction isn't inherently good or bad for a bank).
    """
    v = m.wow if which == "wow" else m.qoq
    pct = m.wow_pct if which == "wow" else m.qoq_pct
    if v != v:  # NaN
        return f'<span style="color:{C["muted"]}">n/a</span>'
    if m.kind == "level":
        txt = f"{v:+,.0f}bn ({pct:+.2f}%)"
    elif m.kind == "ratio":
        txt = f"{v:+.2f} pts"
    else:
        txt = f"{v:+.0f} bp"
    arrow = "&#9650;" if v > 0 else "&#9660;" if v < 0 else "&#9644;"
    color = C["ink2"]
    if color_sense and abs(v) > 1e-9:
        color = C["good"] if v * color_sense > 0 else C["bad"]
    return f'<span style="color:{color};white-space:nowrap">{arrow} {escape(txt)}</span>'


def _pct_cell(v: float) -> str:
    if v != v:
        return f'<td class="num" style="color:{C["muted"]}">n/a</td>'
    color = C["good"] if v > 0 else C["bad"] if v < 0 else C["ink2"]
    arrow = "&#9650;" if v > 0 else "&#9660;" if v < 0 else ""
    return f'<td class="num" style="color:{color}">{arrow} {v:+.1f}%</td>'


def _kpi(label: str, value: str, sub: str) -> str:
    return f"""
      <td class="kpi" width="33%" valign="top" style="padding:6px">
        <div style="background:{C['card']};border:1px solid {C['line']};border-radius:8px;padding:12px 14px">
          <div style="font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:{C['muted']}">{escape(label)}</div>
          <div style="font-size:24px;font-weight:700;color:{C['ink']};margin:4px 0 2px">{value}</div>
          <div style="font-size:12px">{sub}</div>
        </div>
      </td>"""


def _section(title: str, body: str, note: str = "") -> str:
    note_html = (f'<div style="font-size:11px;color:{C["muted"]};margin-top:8px">{note}</div>'
                 if note else "")
    return f"""
  <tr><td style="padding:18px 22px 4px">
    <div style="font-size:15px;font-weight:700;color:{C['ink']};border-bottom:2px solid {C['brand']};padding-bottom:6px;margin-bottom:10px">{escape(title)}</div>
    {body}{note_html}
  </td></tr>"""


def _metric_table(ms: list[Metric], color_sense: Callable[[Metric], int]) -> str:
    rows = "".join(f"""
      <tr>
        <td style="padding:7px 6px;border-bottom:1px solid {C['line']}">{escape(m.label)}
          <div style="font-size:10px;color:{C['muted']}">as of {m.asof:%b %d, %Y}</div></td>
        <td class="num" style="font-weight:600">{_fmt_val(m)}</td>
        <td class="num">{_fmt_delta(m, 'wow', color_sense(m))}</td>
        <td class="num">{_fmt_delta(m, 'qoq', color_sense(m))}</td>
      </tr>""" for m in ms)
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="data" style="font-size:13px;color:{C['ink']}">
      <tr style="color:{C['muted']};font-size:11px;text-transform:uppercase;letter-spacing:.04em">
        <th align="left" style="padding:4px 6px">Metric</th><th class="num">Latest</th>
        <th class="num">WoW</th><th class="num">QoQ</th></tr>{rows}
    </table>"""


def _img(src: str | None, alt: str) -> str:
    if not src:
        return ""
    return (f'<img src="{src}" alt="{escape(alt)}" width="596" '
            f'style="display:block;width:100%;max-width:596px;height:auto;border:0;margin:6px 0 4px">')


def _relative_body(rel: RelativePerf | None, img_src: Callable[[str], str | None]) -> str:
    """EBC vs KRX: returns by horizon, relative spread, and 1Y risk stats."""
    if rel is None:
        return (f'<div style="font-size:13px;color:{C["ink2"]}">{SUBJECT_TICKER} / KRX price '
                f'data unavailable this run.</div>')
    rows = "".join(f"""
      <tr><td style="padding:7px 6px;border-bottom:1px solid {C['line']}">{escape(lbl)}</td>
        {_pct_cell(s)}{_pct_cell(b)}
        <td class="num" style="font-weight:700;color:{C['good'] if s - b > 0 else C['bad']}">
          {'&#9650;' if s - b > 0 else '&#9660;'} {s - b:+.1f} pts</td></tr>""" for lbl, s, b in rel.horizons)
    stat = (lambda k, v: f'<td style="padding:8px 6px;text-align:center"><div style="font-size:11px;'
            f'color:{C["muted"]};text-transform:uppercase;letter-spacing:.04em">{k}</div>'
            f'<div style="font-size:17px;font-weight:700;color:{C["ink"]}">{v}</div></td>')
    stats = "".join([stat("Beta vs KRX", f"{rel.beta_1y:.2f}"),
                     stat("Correlation", f"{rel.corr_1y:.2f}"),
                     stat(f"{rel.subject} vol", f"{rel.vol_1y_subject:.0f}%"),
                     stat("KRX vol", f"{rel.vol_1y_bench:.0f}%")])
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="data" style="font-size:13px;color:{C['ink']}">
      <tr style="color:{C['muted']};font-size:11px;text-transform:uppercase;letter-spacing:.04em">
        <th align="left" style="padding:4px 6px">Horizon</th><th class="num">{escape(rel.subject)}</th>
        <th class="num">KRX</th><th class="num">Relative</th></tr>{rows}
    </table>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="margin-top:10px;background:#f7f7f4;border-radius:8px"><tr>{stats}</tr></table>
    {_img(img_src('subject_vs_index'), f'{rel.subject} vs KRX relative performance')}"""


def render_html(*, rates, banks, eq, fomc, fomc_note, highlights, rel,
                charts: dict[str, Path | None], img_src: Callable[[str], str | None],
                report_date: date) -> str:
    g = lambda lbl, ms: find_metric(ms, lbl)  # noqa: E731

    # --- KPI strip --------------------------------------------------------
    kpis = []
    for lbl, ms, sense in [("10Y Treasury", rates, 0), ("2s10s Spread", rates, 0),
                           ("SOFR", rates, 0)]:
        m = g(lbl, ms)
        if m:
            kpis.append(_kpi(lbl, _fmt_val(m), _fmt_delta(m, "wow", sense) +
                             f' <span style="color:{C["muted"]}">WoW</span>'))
    for lbl, ms in [("Deposits - All Banks", banks), ("Loans & Leases - All Banks", banks),
                    ("LDR - All Banks", banks)]:
        m = g(lbl, ms)
        if m:
            short = lbl.replace(" - All Banks", "").replace(" & Leases", "")
            value = _fmt_val(m) if m.kind == "level" else f"{m.value:.1f}%"
            kpis.append(_kpi(f"Bank {short}", value, _fmt_delta(m, "wow", 1 if m.kind == "level" else 0)
                             + f' <span style="color:{C["muted"]}">WoW</span>'))
    byt = {r.ticker: r for r in eq}
    if SUBJECT_TICKER in byt:
        r = byt[SUBJECT_TICKER]
        col = C["good"] if r.ret_1w > 0 else C["bad"]
        arrow = "&#9650;" if r.ret_1w > 0 else "&#9660;"
        kpis.append(_kpi(f"{SUBJECT_TICKER} 1-week", f"${r.price:,.2f}",
                         f'<span style="color:{col}">{arrow} {r.ret_1w:+.1f}%</span>'))
    if rel is not None:
        _, s, b = next(h for h in rel.horizons if h[0] == "YTD")
        _, s1, b1 = rel.horizons[0]
        col = C["good"] if s1 - b1 > 0 else C["bad"]
        arrow = "&#9650;" if s1 - b1 > 0 else "&#9660;"
        kpis.append(_kpi(f"{SUBJECT_TICKER} vs KRX YTD", f"{s - b:+.1f} pts",
                         f'<span style="color:{col}">{arrow} {s1 - b1:+.1f} pts</span>'
                         f' <span style="color:{C["muted"]}">this week</span>'))
    if fomc:
        n = fomc[0]
        lead, p = max([("Cut", n.p_cut), ("Hold", n.p_hold), ("Hike", n.p_hike)], key=lambda x: x[1])
        kpis.append(_kpi(f"FOMC {n.meeting:%b %d}", f"{p:.0%} {lead}",
                         f'<span style="color:{C["ink2"]}">Implied: {escape(n.likely_range)}</span>'))
    kpi_rows = "".join("<tr>" + "".join(kpis[i:i + 3]) + "</tr>" for i in range(0, len(kpis), 3))

    # --- Highlights -------------------------------------------------------
    bullets = "".join(f'<li style="margin:0 0 6px">{h}</li>' for h in highlights) or \
        "<li>No data available this week.</li>"

    # --- FOMC table -------------------------------------------------------
    if fomc:
        frows = "".join(f"""
          <tr><td style="padding:7px 6px;border-bottom:1px solid {C['line']}">{o.meeting:%b %d, %Y}</td>
            <td class="num">{o.p_cut:.0%}</td><td class="num">{o.p_hold:.0%}</td>
            <td class="num">{o.p_hike:.0%}</td><td class="num">{o.rate_post:.3f}%</td>
            <td class="num">{o.cumulative_bp:+.0f} bp</td></tr>""" for o in fomc)
        fomc_body = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="data" style="font-size:13px;color:{C['ink']}">
          <tr style="color:{C['muted']};font-size:11px;text-transform:uppercase;letter-spacing:.04em">
            <th align="left" style="padding:4px 6px">Meeting</th><th class="num">P(cut)</th>
            <th class="num">P(hold)</th><th class="num">P(hike)</th>
            <th class="num">Implied EFFR</th><th class="num">Cum. vs today</th></tr>{frows}
        </table>{_img(img_src('fomc'), 'Implied fed funds path by meeting')}"""
    else:
        fomc_body = (f'<div style="font-size:13px;color:{C["ink2"]}">Fed Funds futures were '
                     f'unavailable this run. See CME FedWatch for live probabilities.</div>')

    # --- Equities table ---------------------------------------------------
    erows = "".join(f"""
      <tr{' style="background:#f1f7f4"' if r.ticker == SUBJECT_TICKER else ''}>
        <td style="padding:7px 6px;border-bottom:1px solid {C['line']};font-weight:{700 if r.ticker == SUBJECT_TICKER else 400}">{escape(display_name(r.ticker))}</td>
        <td class="num">{'' if r.ticker.startswith('^') else '$'}{r.price:,.2f}</td>{_pct_cell(r.ret_1w)}{_pct_cell(r.ret_qoq)}
        {_pct_cell(r.ret_ytd)}{_pct_cell(r.off_52w_high)}</tr>""" for r in eq)
    eq_body = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="data" style="font-size:13px;color:{C['ink']}">
      <tr style="color:{C['muted']};font-size:11px;text-transform:uppercase;letter-spacing:.04em">
        <th align="left" style="padding:4px 6px">Ticker</th><th class="num">Price</th>
        <th class="num">1W</th><th class="num">QoQ</th><th class="num">YTD</th>
        <th class="num">vs 52w high</th></tr>{erows}
    </table>{_img(img_src('equities'), 'Bank equities indexed performance')}""" if eq else \
        f'<div style="font-size:13px;color:{C["ink2"]}">Equity data unavailable this run.</div>'

    rate_sense = lambda m: 0  # noqa: E731
    bank_sense = lambda m: 1 if m.kind == "level" else 0  # noqa: E731

    sections = "".join([
        _section("This week at a glance",
                 f'<ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.5;color:{C["ink"]}">{bullets}</ul>'),
        _section(f"{SUBJECT_TICKER} vs KBW Regional Bank Index (KRX)",
                 _relative_body(rel, img_src),
                 "Price returns (excl. dividends) so EBC is comparable with KRX, a price index of ~50 US "
                 "regional banks. Beta, correlation and annualized volatility from 1Y daily returns. "
                 "Relative = EBC return minus KRX return, in percentage points."),
        _section("Rates & yield curve",
                 _metric_table(rates, rate_sense) + _img(img_src("treasuries"), "Treasury yields and 2s10s")
                 + _img(img_src("curve"), "Yield curve snapshot"),
                 "Source: FRED (H.15 constant-maturity Treasuries, NY Fed SOFR/EFFR). WoW/QoQ in basis points."),
        _section("FOMC expectations", fomc_body, fomc_note),
        _section("Bank balance sheets (Fed H.8)",
                 _metric_table(banks, bank_sense) + _img(img_src("deposits_loans"), "Deposits vs loans"),
                 "Source: Federal Reserve H.8, seasonally adjusted weekly levels; released Fridays with ~9-day lag. "
                 "'Small banks' = domestically chartered banks outside the top 25 by assets."),
        _section("Bank equities & sentiment", eq_body,
                 "Price return via Yahoo Finance. KRX = KBW Nasdaq Regional Banking Index; KRE = SPDR S&amp;P Regional Banking; "
                 "KBE = SPDR S&amp;P Bank; XLF = Financial Select Sector."),
    ])

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Rates &amp; Banking Dashboard - {report_date:%b %d, %Y}</title>
<style>
  .num {{ text-align:right; padding:7px 6px; border-bottom:1px solid {C['line']}; white-space:nowrap; font-variant-numeric:tabular-nums; }}
  .data th.num {{ border-bottom:0; padding:4px 6px; }}
  @media only screen and (max-width:620px) {{
    .container {{ width:100% !important; }}
    .kpi {{ display:block !important; width:100% !important; box-sizing:border-box; }}
    .data {{ font-size:12px !important; }}
  }}
</style></head>
<body style="margin:0;padding:0;background:{C['page']};font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{C['page']}">
<tr><td align="center" style="padding:20px 10px">
<table role="presentation" class="container" width="640" cellpadding="0" cellspacing="0"
       style="width:640px;max-width:640px;background:{C['card']};border-radius:10px;overflow:hidden;border:1px solid {C['line']}">
  <tr><td style="background:{C['brand']};padding:20px 22px;color:#ffffff">
    <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.85">Weekly briefing &middot; {report_date:%B %d, %Y}</div>
    <div style="font-size:22px;font-weight:700;margin-top:4px">Rates, Liquidity &amp; Bank Sector Dashboard</div>
    <div style="font-size:13px;opacity:.85;margin-top:2px">Sample analysis &middot; subject bank: {SUBJECT_TICKER}</div>
  </td></tr>
  <tr><td style="padding:14px 16px 0">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{kpi_rows}</table>
  </td></tr>
  {sections}
  <tr><td style="padding:18px 22px 22px;font-size:11px;color:{C['muted']};line-height:1.5">
    Generated automatically {datetime.now():%Y-%m-%d %H:%M}. Public-data sources (FRED, Federal Reserve,
    Yahoo Finance, CBOT futures); figures may be revised. For internal discussion only. Not investment advice.
  </td></tr>
</table></td></tr></table></body></html>"""


def render_text(highlights: list[str], report_date: date) -> str:
    """Plain-text fallback part for clients that block HTML."""
    from html import unescape
    lines = [f"Weekly Rates & Banking Dashboard - {report_date:%B %d, %Y}", ""]
    lines += [f"- {unescape(h)}" for h in highlights]
    lines += ["", "Open this email in an HTML-capable client for tables and charts."]
    return "\n".join(lines)
