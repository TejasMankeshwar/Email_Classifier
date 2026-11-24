"""
G-lassify Gmail Reader
Fetches and parses emails from the last N hours via the Gmail API.
"""

import base64
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from src.config import EMAIL_BODY_MAX_CHARS, logger


@dataclass
class EmailData:
    """Parsed email data ready for classification."""

    message_id: str
    sender: str
    subject: str
    timestamp: datetime
    body: str
    snippet: str = ""

    @property
    def sender_name(self) -> str:
        """Extract just the display name from the sender field."""
        if "<" in self.sender:
            return self.sender.split("<")[0].strip().strip('"')
        return self.sender

    @property
    def gmail_url(self) -> str:
        """Direct link to this email in Gmail web."""
        return f"https://mail.google.com/mail/u/0/#inbox/{self.message_id}"


def was_digest_sent_today(service, date_str: str, lookback_hours: int = 20) -> bool:
    """
    Check if a digest email for `date_str` was already sent recently.

    Prevents duplicate digests when multiple triggers (e.g., cron-job.org
    workflow_dispatch at 7:00 AM EST and backup GitHub Actions schedule) fire
    on the same day.
    """
    cutoff_epoch = int(time.time()) - (lookback_hours * 3600)
    query = f'subject:"Daily Email Summary – {date_str}" after:{cutoff_epoch}'
    try:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=1)
            .execute()
        )
        return len(results.get("messages", [])) > 0
    except Exception as e:
        logger.warning(f"Could not check for existing digest: {e}")
        return False


def get_last_digest_timestamp(service, max_lookback_hours: int = 168) -> int | None:
    """
    Find the Unix epoch timestamp (in seconds) of the most recently sent digest email.

    Caps the returned timestamp to at most `max_lookback_hours` ago (default: 7 days)
    to prevent fetching thousands of emails if the digest was paused for a long time.
    Returns None if no previous digest is found.
    """
    try:
        results = (
            service.users()
            .messages()
            .list(userId="me", q='in:sent subject:"Daily Email Summary –"', maxResults=1)
            .execute()
        )
        messages = results.get("messages", [])
        if not messages:
            return None

        msg = (
            service.users()
            .messages()
            .get(userId="me", id=messages[0]["id"], format="minimal")
            .execute()
        )
        internal_ms = msg.get("internalDate")
        if not internal_ms:
            return None

        last_epoch = int(internal_ms) // 1000
        min_epoch = int(time.time()) - (max_lookback_hours * 3600)
        if last_epoch < min_epoch:
            logger.info(
                f"Last digest was over {max_lookback_hours}h ago; capping lookback to {max_lookback_hours}h."
            )
            return min_epoch
        return last_epoch
    except Exception as e:
        logger.warning(f"Could not determine last digest timestamp: {e}")
        return None


def fetch_recent_emails(
    service,
    hours: int | None = 24,
    since_epoch: int | None = None,
) -> list[EmailData]:
    """
    Fetch all emails received since `since_epoch` or in the last `hours` hours.

    Args:
        service: Authorized Gmail API service object.
        hours: How many hours back to look if `since_epoch` is not provided (default: 24).
        since_epoch: Optional Unix epoch timestamp (seconds) of the last digest.

    Returns:
        List of EmailData objects with parsed content.
    """
    if since_epoch is not None:
        # +1s avoids re-matching the previous digest timestamp boundary
        cutoff_epoch = since_epoch + 1
        since_dt = datetime.fromtimestamp(cutoff_epoch, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
        desc = f"since last digest ({since_dt})"
    else:
        effective_hours = hours if hours is not None else 24
        cutoff_epoch = int(time.time()) - (effective_hours * 3600)
        desc = f"from the last {effective_hours} hours"

    query = f"after:{cutoff_epoch}"

    logger.info(f"Fetching emails {desc} (query: {query})")

    # Paginate through all matching messages
    message_ids = []
    page_token = None

    while True:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token)
            .execute()
        )
        messages = results.get("messages", [])
        message_ids.extend(msg["id"] for msg in messages)

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    logger.info(f"Found {len(message_ids)} emails {desc}")

    if not message_ids:
        return []

    # Fetch and parse each message
    emails = []
    for i, msg_id in enumerate(message_ids, 1):
        try:
            email_data = _fetch_and_parse_message(service, msg_id)
            if email_data:
                if email_data.subject.startswith("Daily Email Summary –"):
                    continue
                emails.append(email_data)
            if i % 10 == 0:
                logger.debug(f"Processed {i}/{len(message_ids)} emails...")
        except Exception as e:
            logger.warning(f"Failed to parse message {msg_id}: {e}")
            continue

    logger.info(f"Successfully parsed {len(emails)} emails")
    return emails


def _fetch_and_parse_message(service, msg_id: str) -> EmailData | None:
    """Fetch a single message by ID and parse its contents."""
    # Fetch raw MIME message
    raw_msg = (
        service.users()
        .messages()
        .get(userId="me", id=msg_id, format="raw")
        .execute()
    )

    snippet = raw_msg.get("snippet", "")

    # Decode base64url → bytes → email.message.Message
    msg_bytes = base64.urlsafe_b64decode(raw_msg["raw"].encode("ASCII"))
    mime_msg = message_from_bytes(msg_bytes)

    # Extract headers
    sender = mime_msg.get("From", "Unknown Sender")
    subject = mime_msg.get("Subject", "(No Subject)")

    # Parse timestamp
    date_str = mime_msg.get("Date", "")
    try:
        timestamp = parsedate_to_datetime(date_str)
    except Exception:
        timestamp = datetime.now(timezone.utc)

    # Extract body
    body = _extract_body(mime_msg)

    # Truncate body to limit LLM token usage
    if len(body) > EMAIL_BODY_MAX_CHARS:
        body = body[:EMAIL_BODY_MAX_CHARS] + "\n[... truncated]"

    return EmailData(
        message_id=msg_id,
        sender=sender,
        subject=subject,
        timestamp=timestamp,
        body=body,
        snippet=snippet,
    )


def _extract_body(mime_msg) -> str:
    """
    Extract the plain text body from a MIME message.
    Prefers text/plain, falls back to text/html (stripped via BeautifulSoup).
    """
    if not mime_msg.is_multipart():
        content_type = mime_msg.get_content_type()
        payload = mime_msg.get_payload(decode=True)
        if payload is None:
            return ""

        charset = mime_msg.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            text = payload.decode("utf-8", errors="replace")

        if content_type == "text/html":
            return _html_to_text(text)
        return text

    # For multipart messages, collect text/plain and text/html parts
    plain_parts = []
    html_parts = []

    for part in mime_msg.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition", ""))

        # Skip attachments
        if "attachment" in content_disposition:
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            text = payload.decode("utf-8", errors="replace")

        if content_type == "text/plain":
            plain_parts.append(text)
        elif content_type == "text/html":
            html_parts.append(text)

    # Prefer plain text
    if plain_parts:
        return "\n".join(plain_parts)

    # Fall back to HTML → stripped text
    if html_parts:
        return _html_to_text("\n".join(html_parts))

    return ""


def _html_to_text(html: str) -> str:
    """Convert HTML to clean plain text using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "head"]):
        element.decompose()

    text = soup.get_text(separator="\n")

    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    text = "\n".join(line for line in lines if line)

    return text
