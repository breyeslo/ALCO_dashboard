"""
Weekly Economic & Banking Dashboard
===================================

Builds a weekly rates / liquidity / bank-sector briefing for a US regional
bank (EBC, NASDAQ, is used as the sample subject) and emails it as a
responsive HTML report with inline charts.

Pipeline
--------
    1. Fetch    FRED (Treasuries, SOFR, EFFR, H.8 deposits & loans)     sources.py
                Yahoo Finance (bank equities/ETFs, 30-Day Fed Funds     sources.py,
                futures)                                                fomc.py
    2. Compute  levels, week-over-week (WoW) and quarter-over-quarter   analytics.py
                (QoQ) changes, curve spreads,
                FOMC probabilities implied by Fed Funds futures         fomc.py
    3. Render   Matplotlib PNG charts + table-based HTML email          charts.py,
                                                                        report.py
    4. Deliver  smtplib / email.mime (charts embedded inline via        mailer.py
                Content-ID)

Usage
-----
    python -m bank_dashboard                # build + send
    python -m bank_dashboard --dry-run      # build + save HTML, no email
    python -m bank_dashboard --out reports  # change the archive folder

Configuration is read from environment variables (or a .env file in the
project root). See README.md / .env.example.
"""
