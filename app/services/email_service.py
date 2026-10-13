"""Sends email. This is the only place that talks to the outside world for email.

EMAIL_BACKEND=console  only writes the email to the server log (safe for trying things out; nothing is delivered).
EMAIL_BACKEND=smtp     really sends through your SMTP server (for example Gmail with an app password).
Later phases can add another backend (for example an MCP email tool) here without touching anything else.
"""
import logging
import smtplib
from email.message import EmailMessage

from fastapi import HTTPException, status

from app.core.config import get_settings

log = logging.getLogger(__name__)


def send_email(*, to: str, subject: str, body: str, reply_to: str | None = None) -> str:
    """Send one email. Returns the backend used ("console" or "smtp"). Raises a readable error on failure."""
    settings = get_settings()
    if settings.email_backend == "console":
        log.warning("EMAIL (console backend, NOT delivered)\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return "console"
    if settings.email_backend != "smtp":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"Unknown EMAIL_BACKEND '{settings.email_backend}'. Use console or smtp.")
    if not settings.smtp_host:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Email sending is not set up. Add SMTP_HOST (and the other SMTP_ settings) to .env.")
    try:
        message = EmailMessage()
        message["From"] = settings.email_from
        message["To"] = to
        message["Subject"] = subject
        if reply_to:
            message["Reply-To"] = reply_to
        message.set_content(body)
    except ValueError as exc:  # for example line breaks inside the subject
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The email has an invalid address or subject.") from exc
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "The email server rejected the username or password (SMTP_USER / SMTP_PASSWORD).") from exc
    except (smtplib.SMTPException, OSError) as exc:
        log.exception("SMTP send failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "The email could not be sent. Check the SMTP settings and your internet connection.") from exc
    return "smtp"
