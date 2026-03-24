"""
alerts.py — Email & SMS Alert Module
=====================================
Sends fraud alerts when a suspicious transaction is detected.

- Email alerts via Twilio SendGrid
- SMS   alerts via Twilio Programmable Messaging

All credentials are read from environment variables.
If any variable is missing the corresponding alert is skipped
(it will NOT crash your app).
"""

import os

# ── Read credentials from environment variables ──────────────────────
# Email (SendGrid)
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM", "")   # verified sender
ALERT_EMAIL_TO   = os.environ.get("ALERT_EMAIL_TO", "")

# SMS (Twilio)
TWILIO_ACCOUNT_SID  = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")  # e.g. +233...
ALERT_PHONE_TO      = os.environ.get("ALERT_PHONE_TO", "")      # recipient


# =====================================================================
# 1.  EMAIL ALERT  (SendGrid)
# =====================================================================

def send_email_alert(alert_data):
    """
    Send an email alert for a suspicious transaction.

    Parameters
    ----------
    alert_data : dict
        Must contain keys like 'amount', 'risk_level',
        'anomaly_score', 'timestamp', 'explanation'.
        Optional: 'suspicious_signals'.

    Returns
    -------
    bool
        True if the email was sent successfully, False otherwise.
    """

    # --- Check that all required env vars are set ---
    if not SENDGRID_API_KEY or not ALERT_EMAIL_FROM or not ALERT_EMAIL_TO:
        print("[Email] Skipped — SendGrid env vars not configured.")
        return False

    try:
        # Import SendGrid helpers (only when needed)
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        # --- Build the email subject ---
        subject = "Fraud Alert: Suspicious Mobile Money Transaction"

        # --- Build the email body with all important details ---
        body = (
            "A suspicious mobile money transaction has been detected.\n"
            "\n"
            f"  Timestamp:      {alert_data.get('timestamp', 'N/A')}\n"
            f"  Amount:         GHS {alert_data.get('amount', 0):.2f}\n"
            f"  Prediction:     {alert_data.get('prediction', 'N/A')}\n"
            f"  Risk Level:     {alert_data.get('risk_level', 'N/A')}\n"
            f"  Anomaly Score:  {alert_data.get('anomaly_score', 'N/A')}\n"
            f"  Explanation:    {alert_data.get('explanation', 'N/A')}\n"
        )

        # Add suspicious signals if they exist
        signals = alert_data.get("suspicious_signals")
        if signals:
            body += f"  Signals:        {signals}\n"

        body += "\n— Mobile Money Fraud Detection System\n"

        # --- Create the Mail object ---
        message = Mail(
            from_email=ALERT_EMAIL_FROM,
            to_emails=ALERT_EMAIL_TO,
            subject=subject,
            plain_text_content=body,
        )

        # --- Send the email ---
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        # Log success
        print(f"[Email] Fraud alert sent to {ALERT_EMAIL_TO}  "
              f"(status {response.status_code})")
        return True

    except Exception as exc:
        # Log the error but do NOT crash the app
        print(f"[Email] Failed to send alert: {exc}")
        return False


# =====================================================================
# 2.  SMS ALERT  (Twilio)
# =====================================================================

def send_sms_alert(alert_data):
    """
    Send an SMS alert for a suspicious transaction.

    Parameters
    ----------
    alert_data : dict
        Must contain keys like 'amount', 'risk_level',
        'anomaly_score', 'timestamp'.

    Returns
    -------
    bool
        True if the SMS was sent successfully, False otherwise.
    """

    # --- Check that all required env vars are set ---
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
            and TWILIO_PHONE_NUMBER and ALERT_PHONE_TO):
        print("[SMS] Skipped — Twilio env vars not configured.")
        return False

    try:
        # Import Twilio client (only when needed)
        from twilio.rest import Client

        # --- Build a short SMS message ---
        sms_body = (
            f"FRAUD ALERT\n"
            f"Amount: GHS {alert_data.get('amount', 0):.2f}\n"
            f"Risk: {alert_data.get('risk_level', 'N/A')}\n"
            f"Score: {alert_data.get('anomaly_score', 'N/A')}\n"
            f"Time: {alert_data.get('timestamp', 'N/A')}"
        )

        # --- Create a Twilio client and send the message ---
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=sms_body,
            from_=TWILIO_PHONE_NUMBER,
            to=ALERT_PHONE_TO,
        )

        # Log success
        print(f"[SMS] Fraud alert sent to {ALERT_PHONE_TO}  "
              f"(SID {message.sid})")
        return True

    except Exception as exc:
        # Log the error but do NOT crash the app
        print(f"[SMS] Failed to send alert: {exc}")
        return False
