"""SMTP delivery with charts embedded inline via Content-ID."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)


def send_email(cfg: Config, subject: str, html: str, text: str,
               images: dict[str, Path]) -> None:
    """
    Builds multipart/related > multipart/alternative (text + html) + inline
    PNGs referenced by Content-ID, the most broadly compatible structure for
    inline images (Gmail and Outlook block base64 data: URIs).
    """
    if not (cfg.email_from and cfg.email_to):
        raise ValueError("EMAIL_FROM/SMTP_USER and EMAIL_TO must be set to send email.")

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = cfg.email_from
    msg["To"] = ", ".join(cfg.email_to)
    if cfg.email_cc:
        msg["Cc"] = ", ".join(cfg.email_cc)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=cfg.email_from.split("@")[-1])

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)

    for cid, path in images.items():
        img = MIMEImage(path.read_bytes(), _subtype="png")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=path.name)
        msg.attach(img)

    ctx = ssl.create_default_context()
    recipients = cfg.email_to + cfg.email_cc
    try:
        if cfg.smtp_use_ssl:
            server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=ctx, timeout=60)
        else:
            server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=60)
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
        with server:
            if cfg.smtp_user and cfg.smtp_password:
                server.login(cfg.smtp_user, cfg.smtp_password)
            refused = server.sendmail(cfg.email_from, recipients, msg.as_string())
        if refused:
            log.warning("Some recipients were refused: %s", refused)
        log.info("Email sent to %d recipient(s).", len(recipients) - len(refused))
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError("SMTP authentication failed - check SMTP_USER/SMTP_PASSWORD "
                           "(Gmail/O365 usually require an app password).") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(f"SMTP delivery failed: {exc}") from exc
