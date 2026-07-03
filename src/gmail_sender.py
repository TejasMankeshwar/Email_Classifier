"""
G-lassify Gmail Sender
Sends the HTML digest email via the Gmail API.
"""

import base64
from email.mime.text import MIMEText

from src.config import logger


def send_digest(service, to: str, html_content: str, date_str: str) -> dict | None:
    """
    Send the digest email via Gmail API.

    Args:
        service: Authorized Gmail API service.
        to: Recipient email address.
        html_content: Complete HTML body of the digest.
        date_str: Formatted date string for the subject line.

    Returns:
        Gmail API response dict, or None on failure.
    """
    subject = f"Daily Email Summary – {date_str}"

    # Create MIME message
    message = MIMEText(html_content, "html")
    message["to"] = to
    message["subject"] = subject

    # Encode to base64url
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    body = {"raw": raw_message}

    try:
        result = service.users().messages().send(userId="me", body=body).execute()
        logger.info(f"✅ Digest sent to {to} (Message ID: {result['id']})")
        return result
    except Exception as e:
        logger.error(f"❌ Failed to send digest: {e}")
        return None
