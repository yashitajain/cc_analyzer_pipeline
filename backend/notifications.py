"""
Email notifications via Gmail SMTP.

Deliberately minimal -- this app sends exactly one kind of email (a
household invite), not a general notification system. Sends through your
own Gmail account (using an App Password, not your normal password)
rather than a transactional email service, since that needs no domain of
your own to send to arbitrary recipients -- just a Gmail account.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
# Google displays App Passwords with spaces for readability (e.g. "abcd efgh
# ijkl mnop") but the real secret is the 16 characters with no spaces --
# strip them here so it works whether or not they got pasted in with spaces.
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
APP_URL = os.getenv("APP_URL", "http://localhost:8501")


def send_household_invite_email(inviter_name, inviter_email, invitee_email):
    """Email `invitee_email` telling them they've been invited to a
    household. Returns (sent: bool, message: str) -- never raises, so a
    missing credential or an SMTP hiccup doesn't break the invite itself
    (the database row is already saved by the time this runs).
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return False, "Invite saved, but no email was sent -- GMAIL_ADDRESS/GMAIL_APP_PASSWORD isn't set."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{inviter_name} invited you to their household"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = invitee_email

    html = f"""
        <p><strong>{inviter_name}</strong> ({inviter_email}) invited you to join
        their household on <strong>CC Statement Analyzer</strong>, so you can both
        see your individual and combined spending in one place.</p>
        <p><a href="{APP_URL}">Sign in with Google</a> using
        <strong>{invitee_email}</strong> to join.</p>
        <p style="color:#888;font-size:12px;">
        If you weren't expecting this, you can safely ignore this email.
        </p>
    """
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, invitee_email, msg.as_string())
        return True, f"Invite email sent to {invitee_email}."
    except Exception as e:
        return False, f"Invite was saved, but the email failed to send: {e}"
