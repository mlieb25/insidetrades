"""Gmail API email sender using GCP service account with domain-wide delegation.

Uses the Google Cloud service account credentials to send emails
via the Gmail API on behalf of insidertraderagent@gmail.com.

Requires: google-auth, google-auth-httplib2, google-api-python-client
"""
import base64
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from . import config
from .logger import log_system, log_error

# Lazy imports — these libraries are only needed at runtime
_service = None


def _get_gmail_service():
    """Build and cache the Gmail API service using service account credentials."""
    global _service
    if _service is not None:
        return _service

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_path = os.path.join(config.BASE_DIR, "credentials",
                                  "service_account.json")

        # Fall back to environment variable path
        if not os.path.exists(creds_path):
            creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

        if not creds_path or not os.path.exists(creds_path):
            log_error("Gmail service account credentials not found",
                      {"searched": creds_path})
            return None

        SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES
        )

        # Delegate to the Gmail account
        sender_email = os.environ.get("GMAIL_SENDER",
                                      config.GMAIL_SENDER)
        delegated = credentials.with_subject(sender_email)

        _service = build("gmail", "v1", credentials=delegated)
        log_system(f"Gmail API service initialized for {sender_email}")
        return _service

    except Exception as e:
        log_error(f"Failed to initialize Gmail API: {e}")
        return None


def send_email(to: str, subject: str, body_text: str,
               body_html: Optional[str] = None) -> bool:
    """Send an email via Gmail API.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body_text: Plain text body.
        body_html: Optional HTML body.

    Returns:
        True if sent successfully, False otherwise.
    """
    service = _get_gmail_service()
    if service is None:
        log_error("Gmail service not available — falling back to log-only")
        return False

    try:
        if body_html:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body_text, "plain"))
            message.attach(MIMEText(body_html, "html"))
        else:
            message = MIMEText(body_text, "plain")

        sender = os.environ.get("GMAIL_SENDER", config.GMAIL_SENDER)
        message["to"] = to
        message["from"] = sender
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        body = {"raw": raw}

        sent = (service.users().messages()
                .send(userId="me", body=body).execute())

        log_system(f"Email sent: {subject}", {"message_id": sent.get("id"),
                                               "to": to})
        return True

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
