"""
G-lassify Email Classifier
Uses Gemini 2.5 Flash with structured output to classify emails
into priority tiers with summaries and action items.

Sends all emails in a single (or few) batch calls to minimize API usage.
"""

import math
import time
from dataclasses import dataclass
from typing import Literal

from google import genai
from pydantic import BaseModel, Field

from src.config import GEMINI_API_KEY, EMAIL_BODY_MAX_CHARS, logger
from src.gmail_reader import EmailData


# ── Pydantic Schema for Structured Output ──────────────────────────────────

class SingleEmailClassification(BaseModel):
    """Classification result for one email, keyed by its index."""

    email_index: int = Field(
        description="The index number of the email being classified (from the input list)."
    )
    priority: Literal[
        "Important & Urgent",
        "Important & Not Urgent",
        "Not Important",
    ] = Field(
        description=(
            "Priority level: 'Important & Urgent' for emails requiring action today, "
            "'Important & Not Urgent' for notable emails without immediate deadlines, "
            "'Not Important' for promotions, newsletters, social notifications, etc."
        )
    )
    summary: str = Field(
        description="A concise one or two sentence summary of the email content."
    )
    action_items: list[str] = Field(
        default_factory=list,
        description=(
            "List of specific action items or deadlines extracted from the email. "
            "Empty list if no actions are needed."
        ),
    )
    category: str = Field(
        default="general",
        description=(
            "Sub-category for grouping, e.g., 'financial', 'recruitment', "
            "'promotion', 'newsletter', 'social', 'security', 'academic', 'general'."
        ),
    )


class BatchClassificationResponse(BaseModel):
    """Structured response containing classifications for all emails in a batch."""

    classifications: list[SingleEmailClassification]


# Keep this for compatibility with digest_builder
class EmailClassification(BaseModel):
    """Structured classification for a single email (used by digest builder)."""

    priority: Literal[
        "Important & Urgent",
        "Important & Not Urgent",
        "Not Important",
    ]
    summary: str
    action_items: list[str] = Field(default_factory=list)
    category: str = "general"


@dataclass
class ClassifiedEmail:
    """An email paired with its AI classification."""

    email: EmailData
    classification: EmailClassification


# ── Gemini Client ──────────────────────────────────────────────────────────

BATCH_PROMPT_HEADER = """\
You are an intelligent email assistant for a personal inbox. You will receive a list of emails.
Classify EACH email into one of three priority levels.

## CRITICAL RULES FOR CLASSIFICATION

### "Important & Urgent" — ONLY for emails that meet ALL of these criteria:
- The email is PERSONALLY addressed to the user (not a mass/bulk email)
- There is a REAL, SPECIFIC deadline or required action within 24-48 hours
- Failing to act would have REAL CONSEQUENCES (financial loss, missed appointment, security breach)

**Examples that ARE Important & Urgent:**
- A bank alert about a transaction YOU made (verify/dispute)
- An interview confirmation requiring YOUR response
- A tuition payment deadline with YOUR name and amount
- An account security alert (new sign-in, 2FA change) for YOUR account

**Examples that are NOT Important & Urgent (even if they use urgent language):**
- "LAST CHANCE to join..." → Marketing email, Not Important
- "URGENT: Your scholarship test starts in 15 mins" from a mass mailer → Not Important (promotional)
- "Last 10 days to apply for X Scholarship" → Promotion, Not Important
- "Download your file before it gets removed" from a service → Not Important (automated notification)
- "New jobs available" → Not Important (job board notification)
- "After tonight you're on your own" → Marketing scare tactic, Not Important
- "Order shipped/delivered/out for delivery" → Important & Not Urgent (automated tracking)
- File sharing notifications → Important & Not Urgent at most

### "Important & Not Urgent" — Personal or account-related, but no immediate deadline:
- Security notifications about YOUR accounts (new sign-in, 2FA enabled, app authorized)
- Financial statements or balance reports
- GitHub/Vercel/service notifications about YOUR projects
- Personal messages from real people you know
- Family link / device management alerts

### "Not Important" — Everything else:
- Marketing emails, regardless of how "urgent" the language is
- Newsletters, digests, and automated roundups
- Promotional offers, sales, and discount codes
- Job board bulk notifications
- University admissions marketing
- Course/webinar promotions
- Order tracking (shipped, delivered, out for delivery)
- App/product update announcements
- Social media notifications

## KEY DISTINCTION
The #1 mistake to avoid: DO NOT classify mass/bulk marketing emails as "Important & Urgent" just because they use urgency language like "LAST CHANCE", "URGENT", "limited time", "expires tonight", "don't miss out". These are MANUFACTURED urgency tactics. If the email was sent to thousands of people, it is NOT urgent for this specific user.

Think step by step: (1) Is this a mass/bulk email or personally directed? (2) Is there a real consequence for THIS user specifically? (3) Is the deadline real and imminent?

For each email, provide:
- email_index: The index number from the list below
- priority: One of the three levels above
- summary: A concise 1-2 sentence summary
- action_items: Specific deadlines or required actions (empty list if none)
- category: One of: financial, recruitment, promotion, newsletter, social, security, academic, general

Here are the emails to classify:

"""


# Rough estimate: ~500 chars per email summary sent to LLM
# Gemini 2.5 Flash has ~1M token context, but we stay conservative
MAX_EMAILS_PER_BATCH = 25  # Keep batches manageable


def _get_client() -> genai.Client:
    """Create a Gemini client."""
    return genai.Client(api_key=GEMINI_API_KEY)


def _format_email_for_batch(index: int, email: EmailData) -> str:
    """Format a single email as a numbered entry for the batch prompt."""
    # Truncate body more aggressively for batch mode
    body = email.body[:EMAIL_BODY_MAX_CHARS]
    return (
        f"--- EMAIL {index} ---\n"
        f"Sender: {email.sender}\n"
        f"Subject: {email.subject}\n"
        f"Date: {email.timestamp.strftime('%Y-%m-%d %H:%M')}\n"
        f"Body:\n{body}\n"
    )


def _classify_batch_call(
    client: genai.Client,
    emails: list[EmailData],
    start_index: int,
    max_retries: int = 3,
) -> list[SingleEmailClassification]:
    """
    Send a batch of emails to Gemini in a single API call.

    Args:
        client: Initialized Gemini client.
        emails: List of emails in this batch.
        start_index: Starting index for email numbering.
        max_retries: Max retries on rate-limit errors.

    Returns:
        List of classifications from the LLM.
    """
    # Build the batch prompt
    prompt = BATCH_PROMPT_HEADER
    for i, email in enumerate(emails):
        prompt += _format_email_for_batch(start_index + i, email)
    prompt += f"\n--- END OF EMAILS ---\nClassify all {len(emails)} emails above.\n"

    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": BatchClassificationResponse,
                },
            )
            return response.parsed.classifications

        except Exception as e:
            last_exception = e
            error_str = str(e)

            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait_time = _parse_retry_delay(error_str, default=20 * (attempt + 1))
                logger.info(
                    f"  Rate limited (attempt {attempt + 1}/{max_retries + 1}), "
                    f"waiting {wait_time:.0f}s..."
                )
                time.sleep(wait_time)
            else:
                raise

    if last_exception is not None:
        raise last_exception
    raise RuntimeError("Batch classification failed without raising any exceptions.")


def _parse_retry_delay(error_str: str, default: float = 20.0) -> float:
    """Extract the suggested retry delay from a Gemini 429 error message."""
    import re

    match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
    if match:
        return float(match.group(1)) + 2  # Add 2s buffer
    return default


def classify_batch(emails: list[EmailData]) -> list[ClassifiedEmail]:
    """
    Classify all emails using as few API calls as possible.

    Sends emails in batches of up to MAX_EMAILS_PER_BATCH in a single
    LLM call each. For typical inboxes (≤50 emails), this means 1-2 API calls
    instead of 50.

    Args:
        emails: List of parsed emails to classify.

    Returns:
        List of ClassifiedEmail objects.
    """
    if not emails:
        return []

    client = _get_client()
    total = len(emails)
    num_batches = math.ceil(total / MAX_EMAILS_PER_BATCH)

    logger.info(f"Classifying {total} emails with Gemini 2.5 Flash...")
    logger.info(f"Using {num_batches} batch call{'s' if num_batches > 1 else ''}")

    # Process in batches
    all_classifications: dict[int, SingleEmailClassification] = {}

    for batch_num in range(num_batches):
        start = batch_num * MAX_EMAILS_PER_BATCH
        end = min(start + MAX_EMAILS_PER_BATCH, total)
        batch_emails = emails[start:end]

        logger.info(
            f"Batch {batch_num + 1}/{num_batches}: "
            f"classifying emails {start + 1}-{end}..."
        )

        try:
            classifications = _classify_batch_call(
                client, batch_emails, start_index=start
            )

            for cls in classifications:
                all_classifications[cls.email_index] = cls

            logger.info(
                f"Batch {batch_num + 1}/{num_batches}: "
                f"received {len(classifications)} classifications"
            )

        except Exception as e:
            logger.error(f"Batch {batch_num + 1}/{num_batches} failed: {e}")
            # Mark all emails in this batch as failed
            for i in range(start, end):
                all_classifications[i] = SingleEmailClassification(
                    email_index=i,
                    priority="Not Important",
                    summary=f"Classification failed: {emails[i].snippet or emails[i].subject}",
                    action_items=[],
                    category="general",
                )

        # Brief pause between batches to respect rate limits
        if batch_num < num_batches - 1:
            time.sleep(15)

    # Assemble results in order
    results = []
    for i, email in enumerate(emails):
        cls = all_classifications.get(i)
        if cls:
            classification = EmailClassification(
                priority=cls.priority,
                summary=cls.summary,
                action_items=cls.action_items,
                category=cls.category,
            )
        else:
            # Email wasn't classified (missing from LLM response)
            classification = EmailClassification(
                priority="Not Important",
                summary=f"Not classified: {email.snippet or email.subject}",
                action_items=[],
                category="general",
            )
        results.append(ClassifiedEmail(email=email, classification=classification))

    # Log summary
    counts: dict[str, int] = {}
    for r in results:
        p = r.classification.priority
        counts[p] = counts.get(p, 0) + 1
    logger.info(f"Classification complete: {counts}")

    # Log individual results
    for r in results:
        icon = {
            "Important & Urgent": "🚨",
            "Important & Not Urgent": "📌",
            "Not Important": "📨",
        }.get(r.classification.priority, "•")
        logger.info(f"  {icon} {r.email.subject[:70]} → {r.classification.priority}")

    return results
