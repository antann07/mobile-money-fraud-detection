"""Email service — SMTP-based email delivery with dev/prod modes.

Sends transactional emails (welcome, password reset) via SMTP.
Falls back to console logging in development when SMTP is not configured.

Environment variables:
  MAIL_SERVER        — SMTP host (e.g. smtp.gmail.com)
  MAIL_PORT          — SMTP port (default: 587 for STARTTLS)
  MAIL_USE_TLS       — "1" to enable STARTTLS (default: "1")
  MAIL_USERNAME      — SMTP login username
  MAIL_PASSWORD      — SMTP login password (app password for Gmail)
  MAIL_DEFAULT_FROM  — Sender address (default: MAIL_USERNAME)
  FRONTEND_URL       — Base URL for links in emails (default: http://localhost:3000)
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _get_mail_config() -> dict:
    return {
        "server": os.environ.get("MAIL_SERVER", ""),
        "port": int(os.environ.get("MAIL_PORT", "587")),
        "use_tls": os.environ.get("MAIL_USE_TLS", "1") == "1",
        "username": os.environ.get("MAIL_USERNAME", ""),
        "password": os.environ.get("MAIL_PASSWORD", ""),
        "default_from": os.environ.get(
            "MAIL_DEFAULT_FROM",
            os.environ.get("MAIL_USERNAME", "noreply@mtnfrauddetection.local"),
        ),
        "frontend_url": os.environ.get("FRONTEND_URL", "http://localhost:3000"),
    }


def _is_configured() -> bool:
    """Return True if SMTP credentials are present."""
    cfg = _get_mail_config()
    return bool(cfg["server"] and cfg["username"] and cfg["password"])


def _send_smtp(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SMTP. Returns True on success, False on failure."""
    cfg = _get_mail_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["default_from"]
    msg["To"] = to

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if cfg["use_tls"]:
            server = smtplib.SMTP(cfg["server"], cfg["port"], timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP(cfg["server"], cfg["port"], timeout=15)
            server.ehlo()

        server.login(cfg["username"], cfg["password"])
        server.sendmail(cfg["default_from"], [to], msg.as_string())
        server.quit()
        logger.info("Email sent to %s subject='%s'", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s subject='%s'", to, subject)
        return False


# ── Public API ────────────────────────────────────────────────

def send_welcome_email(email: str, full_name: str) -> bool:
    """Send a welcome / account-created email after registration."""
    cfg = _get_mail_config()
    frontend_url = cfg["frontend_url"]
    subject = "Welcome to MTN MoMo Fraud Detection"

    html_body = f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
  <div style="background: #ffcc00; padding: 20px; text-align: center;">
    <h1 style="margin: 0; color: #333;">🛡️ MTN MoMo Fraud Detection</h1>
  </div>
  <div style="padding: 20px;">
    <h2>Welcome, {full_name}!</h2>
    <p>Your account has been created successfully. You can now:</p>
    <ul>
      <li>Monitor your mobile money wallets for fraud</li>
      <li>Check suspicious SMS messages for authenticity</li>
      <li>Upload screenshots for AI-powered analysis</li>
    </ul>
    <p style="text-align: center; margin: 30px 0;">
      <a href="{frontend_url}/login"
         style="background: #ffcc00; color: #333; padding: 12px 30px;
                text-decoration: none; border-radius: 5px; font-weight: bold;">
        Sign In to Your Dashboard
      </a>
    </p>
    <p style="color: #666; font-size: 0.85em;">
      If you did not create this account, please ignore this email.
    </p>
  </div>
  <div style="background: #f5f5f5; padding: 15px; text-align: center; font-size: 0.8em; color: #999;">
    MTN MoMo Fraud Detection System &mdash; Protecting Your Mobile Money
  </div>
</body>
</html>"""

    text_body = f"""\
Welcome to MTN MoMo Fraud Detection, {full_name}!

Your account has been created successfully.

Sign in at: {frontend_url}/login

If you did not create this account, please ignore this email.
"""

    if not _is_configured():
        logger.info(
            "[DEV] Welcome email (not sent — SMTP not configured):\n"
            "  To: %s\n  Subject: %s",
            email, subject,
        )
        return False

    return _send_smtp(email, subject, html_body, text_body)


def send_password_reset_email(email: str, token: str) -> bool:
    """Send a password reset link email."""
    cfg = _get_mail_config()
    frontend_url = cfg["frontend_url"]
    from urllib.parse import quote
    reset_url = f"{frontend_url}/reset-password?email={quote(email, safe='')}&token={quote(token, safe='')}"
    subject = "Password Reset — MTN MoMo Fraud Detection"

    html_body = f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
  <div style="background: #ffcc00; padding: 20px; text-align: center;">
    <h1 style="margin: 0; color: #333;">🛡️ MTN MoMo Fraud Detection</h1>
  </div>
  <div style="padding: 20px;">
    <h2>Password Reset Request</h2>
    <p>We received a request to reset your password. Click the button below to set a new password:</p>
    <p style="text-align: center; margin: 30px 0;">
      <a href="{reset_url}"
         style="background: #ffcc00; color: #333; padding: 12px 30px;
                text-decoration: none; border-radius: 5px; font-weight: bold;">
        Reset My Password
      </a>
    </p>
    <p style="color: #666; font-size: 0.9em;">
      This link expires in 30 minutes. If you did not request a password reset,
      you can safely ignore this email &mdash; your password will not be changed.
    </p>
    <p style="color: #999; font-size: 0.8em; word-break: break-all;">
      If the button doesn't work, copy this link into your browser:<br>
      {reset_url}
    </p>
  </div>
  <div style="background: #f5f5f5; padding: 15px; text-align: center; font-size: 0.8em; color: #999;">
    MTN MoMo Fraud Detection System &mdash; Protecting Your Mobile Money
  </div>
</body>
</html>"""

    text_body = f"""\
Password Reset — MTN MoMo Fraud Detection

We received a request to reset your password.

Reset your password here: {reset_url}

This link expires in 30 minutes.

If you did not request this, you can safely ignore this email.
"""

    if not _is_configured():
        logger.info(
            "[DEV] Password reset email (not sent — SMTP not configured):\n"
            "  To: %s\n  Reset URL: %s",
            email, reset_url,
        )
        return False

    return _send_smtp(email, subject, html_body, text_body)


def send_verification_email(email: str, full_name: str, token: str) -> bool:
    """Send an email verification link after registration."""
    cfg = _get_mail_config()
    frontend_url = cfg["frontend_url"]
    from urllib.parse import quote
    verify_url = f"{frontend_url}/verify-email?email={quote(email, safe='')}&token={quote(token, safe='')}"
    subject = "Verify Your Email — MTN MoMo Fraud Detection"

    html_body = f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
  <div style="background: #ffcc00; padding: 20px; text-align: center;">
    <h1 style="margin: 0; color: #333;">🛡️ MTN MoMo Fraud Detection</h1>
  </div>
  <div style="padding: 20px;">
    <h2>Welcome, {full_name}!</h2>
    <p>Please verify your email address to activate your account:</p>
    <p style="text-align: center; margin: 30px 0;">
      <a href="{verify_url}"
         style="background: #ffcc00; color: #333; padding: 12px 30px;
                text-decoration: none; border-radius: 5px; font-weight: bold;">
        Verify My Email
      </a>
    </p>
    <p style="color: #666; font-size: 0.9em;">
      This link expires in 24 hours. If you did not create this account,
      please ignore this email.
    </p>
    <p style="color: #999; font-size: 0.8em; word-break: break-all;">
      If the button doesn't work, copy this link into your browser:<br>
      {verify_url}
    </p>
  </div>
  <div style="background: #f5f5f5; padding: 15px; text-align: center; font-size: 0.8em; color: #999;">
    MTN MoMo Fraud Detection System &mdash; Protecting Your Mobile Money
  </div>
</body>
</html>"""

    text_body = f"""\
Welcome to MTN MoMo Fraud Detection, {full_name}!

Please verify your email address by visiting:
{verify_url}

This link expires in 24 hours.

If you did not create this account, please ignore this email.
"""

    if not _is_configured():
        logger.info(
            "[DEV] Verification email (not sent — SMTP not configured):\n"
            "  To: %s\n  Verify URL: %s",
            email, verify_url,
        )
        return False

    return _send_smtp(email, subject, html_body, text_body)
