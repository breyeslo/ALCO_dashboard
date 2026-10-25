"""Orchestration: fetch -> compute -> render -> deliver."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from .analytics import (build_bank_metrics, build_equity_table, build_rate_metrics,
                        build_relative)
from .charts import (chart_curve_snapshot, chart_deposits_loans, chart_equities,
                     chart_fomc, chart_subject_vs_index, chart_treasuries)
from .config import (BENCHMARK_TICKER, FRED_SERIES, INDEX_TICKER, SECTOR_TICKERS,
                     SUBJECT_TICKER, Config)
from .fomc import FomcOutlook, compute_fomc_outlook, fetch_zq_curve
from .mailer import send_email
from .narrative import build_highlights
from .report import render_html, render_text
from .sources import FredClient, fetch_prices

log = logging.getLogger(__name__)


def run(cfg: Config, out_root: Path, dry_run: bool) -> int:
    report_date = date.today()
    out_dir = out_root / report_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    start = report_date - timedelta(days=365 * cfg.lookback_years + 120)  # +buffer for QoQ

    # ---- 1. Fetch ---------------------------------------------------------
    if not cfg.fred_api_key:
        log.critical("FRED_API_KEY is not set. Get a free key at "
                     "https://fred.stlouisfed.org/docs/api/api_key.html and add it to .env")
        return 2
    log.info("Fetching %d FRED series...", len(FRED_SERIES))
    fred = FredClient(cfg.fred_api_key).many(FRED_SERIES.keys(), start)
    log.info("FRED: %d/%d series loaded.", len(fred), len(FRED_SERIES))

    tickers = [SUBJECT_TICKER, INDEX_TICKER, *SECTOR_TICKERS, BENCHMARK_TICKER,
               *[p for p in cfg.peers if p not in {SUBJECT_TICKER, *SECTOR_TICKERS}]]
    log.info("Fetching prices for %s...", ", ".join(tickers))
    px = fetch_prices(tickers, report_date - timedelta(days=400))

    if not fred and px.empty:
        log.critical("All data sources failed; aborting without sending.")
        return 2

    # ---- 2. Compute -------------------------------------------------------
    rates = build_rate_metrics(fred)
    banks = build_bank_metrics(fred)
    eq = build_equity_table(px, tickers) if not px.empty else []
    rel = build_relative(px, SUBJECT_TICKER, INDEX_TICKER) if not px.empty else None

    fomc: list[FomcOutlook] = []
    fomc_note = ("Probabilities derived from CBOT 30-Day Fed Funds futures (CME FedWatch "
                 "methodology, two-outcome approximation). Indicative only.")
    if "EFFR" in fred and "DFEDTARL" in fred:
        zq = fetch_zq_curve()
        if zq:
            fomc = compute_fomc_outlook(zq, float(fred["EFFR"].iloc[-1]),
                                        float(fred["DFEDTARL"].iloc[-1]), cfg.fomc_meetings_shown)
        if not fomc and "DGS2" in fred:
            # Fallback proxy: 2Y yield vs EFFR approximates the policy path over 2 years.
            gap = (fred["DGS2"].iloc[-1] - fred["EFFR"].iloc[-1]) * 100
            fomc_note = (f"Futures unavailable; proxy: 2Y Treasury trades {gap:+.0f} bp vs EFFR "
                         f"({'cuts' if gap < 0 else 'hikes'} priced over 2 years).")

    highlights = build_highlights(rates, banks, eq, fomc, rel)

    # ---- 3. Render charts ---------------------------------------------------
    builders = {
        "treasuries": lambda p: chart_treasuries(fred, p, cfg.lookback_years),
        "curve": lambda p: chart_curve_snapshot(fred, p),
        "deposits_loans": lambda p: chart_deposits_loans(fred, p, cfg.lookback_years),
        "subject_vs_index": lambda p: chart_subject_vs_index(px, rel, p),
        "equities": lambda p: chart_equities(px, p) if not px.empty else None,
        "fomc": lambda p: chart_fomc(fomc, p),
    }
    charts: dict[str, Path | None] = {}
    for name, fn in builders.items():
        try:
            charts[name] = fn(out_dir / f"{name}.png")
        except Exception:  # noqa: BLE001
            log.exception("Chart '%s' failed; continuing without it.", name)
            charts[name] = None
    charts_ok = {k: v for k, v in charts.items() if v}

    common = dict(rates=rates, banks=banks, eq=eq, fomc=fomc, fomc_note=fomc_note,
                  highlights=highlights, rel=rel, charts=charts, report_date=report_date)

    # Local archive copy references PNGs by relative path (viewable in a browser);
    # the email copy references them by Content-ID.
    preview = render_html(**common, img_src=lambda k: charts_ok[k].name if k in charts_ok else None)
    (out_dir / "dashboard.html").write_text(preview, encoding="utf-8")
    log.info("Saved %s", out_dir / "dashboard.html")

    if dry_run:
        log.info("Dry run: email not sent.")
        return 0

    # ---- 4. Deliver ---------------------------------------------------------
    cids = {k: f"{k}.{report_date:%Y%m%d}@bank-dashboard" for k in charts_ok}
    email_html = render_html(**common, img_src=lambda k: f"cid:{cids[k]}" if k in cids else None)
    subject = f"Weekly Rates & Banking Dashboard - {report_date:%b %d, %Y}"
    send_email(cfg, subject, email_html, render_text(highlights, report_date),
               {cids[k]: p for k, p in charts_ok.items()})
    return 0
