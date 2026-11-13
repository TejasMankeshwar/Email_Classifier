"""
G-lassify Email Classifier
Uses Gemini 2.5 Flash with structured output to classify emails
into priority tiers with summaries and action items.

Sends all emails in a single (or few) batch calls to minimize API usage.
"""

import math
import random
import time
from dataclasses import dataclass
from typing import Literal

from google import genai
from pydantic import BaseModel, Field

from src.config import GEMINI_API_KEY, GEMINI_MODEL, EMAIL_BODY_MAX_CHARS, logger
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
            "internship/job decisions (rejections, acceptances, offers), internship action items "
            "(online assessments, interview invitations/scheduling, candidate verification), "
            "direct replies from recruiters/companies, or urgent personal/financial/security alerts; "
            "'Important & Not Urgent' for notable emails without urgent deadlines, including standard "
            "internship 'thanks for applying' / application received confirmations; "
            "'Not Important' for promotions, marketing, newsletters, social notifications, bulk digests."
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
Classify EACH email into one of three priority levels:
- "Important & Urgent"
- "Important & Not Urgent"
- "Not Important"

## CRITICAL RULES FOR CLASSIFICATION

### 1. "Important & Urgent"
Classify an email as "Important & Urgent" if it falls into ANY of these categories:

#### A. Internship & Job Applications (HIGH PRIORITY RULES):
- **Rejections:** ANY email stating an application was rejected, not selected, not moving forward, or closed (even if the subject politely begins with "Thanks for applying" or "Application Update"). The user MUST see rejections in Important & Urgent.
- **Acceptances & Offers:** Job/internship offers, offer letters, or advancement to subsequent interview rounds.
- **Action-Demanding Application Steps:** Emails requiring the user to take a specific action or meet a deadline:
  * Online Assessments / coding challenges / take-home tests (e.g. HackerRank, CodeSignal, LeetCode, HireVue).
  * Candidate portal setup or account verification (e.g. "Verify your candidate account within 24 hours").
  * Requests to submit transcripts, references, or work samples.
- **Interview Invitations & Scheduling:** Requests to schedule or confirm an interview, technical screen, or recruiter chat.
- **Company & Recruiter Direct Replies:** Any direct, personalized email or follow-up from a human recruiter, hiring manager, or company representative regarding the user's application.

#### B. General Urgent Personal Matters:
- Bank or financial alerts about transactions to verify/dispute or immediate payment deadlines.
- Account security alerts (new sign-ins, 2FA changes, password reset requests).
- Personally addressed emails with a real, specific deadline or required action within 24–48 hours where failing to act has real consequences.

---

### 2. "Important & Not Urgent"
Classify an email as "Important & Not Urgent" if it is important/relevant to the user, but does NOT require immediate action today:

#### A. Standard Internship "Thanks for Applying" / Application Received:
- **Routine Application Confirmations:** Automated emails confirming that an application was received or submitted successfully (e.g., "Thank you for applying to [Company]", "Application received for [Role]", "Got it! We received your application", "Application submitted successfully") where **NO rejection/acceptance decision is conveyed** and **NO assessment/interview action is demanded**.
- **RULE:** These emails are informative confirmations and belong in **"Important & Not Urgent"** (category: recruitment), NEVER in "Important & Urgent".

#### B. Other Important & Not Urgent Emails:
- Account/service confirmations (e.g. 2FA enabled, third-party app authorized).
- Financial statements, receipts, and balance reports.
- GitHub, Vercel, or cloud service notifications for the user's projects.
- Personal correspondence from real people that does not have an urgent deadline.

---

### 3. "Not Important" — Everything Else:
- Mass marketing and promotional emails, regardless of simulated urgency ("LAST CHANCE", "URGENT", "limited time", "expires tonight").
- Automated newsletters, weekly digests, and promotional roundups.
- Job board bulk emails and generic job listings ("10 new jobs matching your search").
- Social media notifications and network updates.
- University marketing, course promotions, and webinar invitations.
- Shipping and order tracking notifications (shipped, out for delivery).

---

## KEY DISTINCTIONS SUMMARY (AVOID THESE COMMON MISTAKES):
1. **Internship Confirmation vs. Rejection/Action:**
   - "Thank you for applying to Google" (pure acknowledgment, no action or decision) → **Important & Not Urgent**
   - "NATIONAL GRID - Thanks for applying! ... not progressing your application" → **Important & Urgent** (Rejection!)
   - "T-Mobile: Verify your candidate account" → **Important & Urgent** (Action required!)
   - "Amazon: Complete your Online Assessment within 5 days" → **Important & Urgent** (Action required!)
   - "Recruiter: We would love to set up a 15-minute phone screen" → **Important & Urgent** (Interview/Company reply!)
   - "Tesla: Congratulations, we would like to offer you..." → **Important & Urgent** (Acceptance/Offer!)
2. **Manufactured Urgency:**
   - If an email was sent to thousands of recipients promoting a product or course with "URGENT" in the subject, it is NOT urgent. Mark it **Not Important**.

For each email, provide:
- email_index: The index number from the list below
- priority: One of the three levels above
- summary: A concise 1-2 sentence summary
- action_items: Specific deadlines or required actions (empty list if none)
- category: One of: financial, recruitment, promotion, newsletter, social, security, academic, general

Here are the emails to classify:

"""


# Rough estimate: ~500 chars per email summary sent to LLM
# Gemini 2.5 Flash has ~1M token context, but we use a larger batch size
# of 50 to minimize multi-batch rate limiting issues on the free tier.
MAX_EMAILS_PER_BATCH = 50  # Keep batches manageable


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


FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]


def _is_transient_error(e: Exception) -> bool:
    """Check if an error from Gemini API is transient and retryable."""
    err_str = str(e).upper()
    transient_indicators = [
        "429",
        "RESOURCE_EXHAUSTED",
        "503",
        "UNAVAILABLE",
        "HIGH DEMAND",
        "500",
        "INTERNAL",
        "502",
        "BAD GATEWAY",
        "504",
        "DEADLINE_EXCEEDED",
        "TIMEOUT",
        "CONNECTION",
    ]
    return any(ind in err_str for ind in transient_indicators)


def _classify_batch_call(
    client: genai.Client,
    emails: list[EmailData],
    start_index: int,
    max_retries: int = 3,
) -> list[SingleEmailClassification]:
    """
    Send a batch of emails to Gemini in a single API call with automatic retries
    and fallback model support.

    Args:
        client: Initialized Gemini client.
        emails: List of emails in this batch.
        start_index: Starting index for email numbering.
        max_retries: Max retries per model on transient errors.

    Returns:
        List of classifications from the LLM.
    """
    # Build the batch prompt
    prompt = BATCH_PROMPT_HEADER
    for i, email in enumerate(emails):
        prompt += _format_email_for_batch(start_index + i, email)
    prompt += f"\n--- END OF EMAILS ---\nClassify all {len(emails)} emails above.\n"

    # Candidate models to try in order
    models_to_try = [GEMINI_MODEL]
    for fm in FALLBACK_MODELS:
        if fm not in models_to_try:
            models_to_try.append(fm)

    last_exception = None
    for model_index, model in enumerate(models_to_try):
        for attempt in range(max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": BatchClassificationResponse,
                    },
                )
                if response.parsed and response.parsed.classifications:
                    if model != GEMINI_MODEL:
                        logger.info(
                            f"  Successfully classified batch using fallback model {model}"
                        )
                    return response.parsed.classifications
                raise ValueError(f"Empty classifications response from model {model}")

            except Exception as e:
                last_exception = e
                error_str = str(e)

                if _is_transient_error(e) and attempt < max_retries:
                    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                        wait_time = _parse_retry_delay(
                            error_str, default=15.0 * (attempt + 1)
                        )
                    else:
                        wait_time = min(60.0, 5.0 * (2**attempt)) + random.uniform(
                            1.0, 3.0
                        )

                    logger.warning(
                        f"  Transient error on {model} (attempt {attempt + 1}/{max_retries + 1}): "
                        f"{error_str[:120]}... Waiting {wait_time:.1f}s before retry."
                    )
                    time.sleep(wait_time)
                else:
                    # Non-transient or exhausted retries on this model
                    if model_index < len(models_to_try) - 1:
                        next_model = models_to_try[model_index + 1]
                        logger.warning(
                            f"  Retries exhausted or non-retryable error on {model}. "
                            f"Falling back to {next_model}..."
                        )
                        break  # Break inner attempt loop to try next model
                    else:
                        raise e

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

    logger.info(f"Classifying {total} emails with {GEMINI_MODEL}...")
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
            logger.error(
                f"Batch {batch_num + 1}/{num_batches} failed after all retries and fallbacks: {e}"
            )
            # Graceful degraded fallback: create placeholder classifications so the digest
            # can still be generated and delivered rather than dropping the run.
            for i, email in enumerate(batch_emails):
                idx = start + i
                all_classifications[idx] = SingleEmailClassification(
                    email_index=idx,
                    priority="Important & Not Urgent",
                    summary=f"[Classification unavailable - Gemini service error] {email.snippet or email.subject}",
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
