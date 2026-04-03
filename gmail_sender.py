"""Gmail SMTP email sender using App Password.

Sends emails from insidertraderagent@gmail.com via Gmail SMTP
with an app password. No GCP SDK dependencies required.
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from . import config
from .logger import log_system, log_error

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _get_credentials() -> tuple:
    """Get SMTP credentials from config or environment."""
    sender = os.environ.get("GMAIL_SENDER", config.GMAIL_SENDER)
    password = os.environ.get("GMAIL_APP_PASSWORD", config.GMAIL_APP_PASSWORD)
    return sender, password


def send_email(to: str, subject: str, body_text: str,
               body_html: Optional[str] = None) -> bool:
    """Send an email via Gmail SMTP.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body_text: Plain text body.
        body_html: Optional HTML body.

    Returns:
        True if sent successfully, False otherwise.
    """
    sender, password = _get_credentials()

    if not password:
        log_error("GMAIL_APP_PASSWORD not configured — email not sent",
                  {"subject": subject})
        return False

    try:
        if body_html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))
        else:
            msg = MIMEText(body_text, "plain")

        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)
            server.sendmail(sender, to, msg.as_string())

        log_system(f"Email sent: {subject}", {"to": to, "from": sender})
        return True

    except smtplib.SMTPAuthenticationError as e:
        log_error(f"SMTP auth failed — check app password: {e}",
                  {"sender": sender})
        return False
    except Exception as e:
        log_error(f"Failed to send email: {e}", {"to": to, "subject": subject})
        return False


def send_signal_alert(alert: dict) -> bool:
    """Send a trade signal alert email."""
    return send_email(
        to=config.EMAIL,
        subject=alert.get("subject", "Trade Signal Alert"),
        body_text=alert.get("body_text", ""),
        body_html=alert.get("body_html"),
    )


def send_digest(digest: dict) -> bool:
    """Send a daily digest or weekly summary email."""
    return send_email(
        to=config.EMAIL,
        subject=digest.get("subject", "Trade Monitor Digest"),
        body_text=digest.get("body_text", ""),
        body_html=digest.get("body_html"),
    )
