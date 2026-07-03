"""
G-lassify — Main Entry Point
Orchestrates the full email classification pipeline:
  1. Authenticate with Gmail
  2. Fetch recent emails
  3. Classify with Gemini 2.5 Flash
  4. Build HTML digest
  5. Send digest to your inbox
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on the path when run as a module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import validate_config, GMAIL_ADDRESS, logger
from src.auth import get_gmail_service
from src.gmail_reader import fetch_recent_emails
from src.classifier import classify_batch
from src.digest_builder import build_digest
from src.gmail_sender import send_digest


def main():
    """Run the G-lassify email classification pipeline."""
    parser = argparse.ArgumentParser(
        description="G-lassify — Personal AI Email Classifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python -m src.main                  # Run normally (classify & send digest)
  python -m src.main --dry-run        # Print digest to stdout, don't send
  python -m src.main --hours 48       # Look back 48 hours instead of 24
  python -m src.main --dry-run --hours 2  # Quick test with last 2 hours
        """,
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Number of hours to look back for emails (default: 24)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the HTML digest to stdout instead of sending it",
    )
    args = parser.parse_args()

    # ── Banner ─────────────────────────────────────────────────────────────
    logger.info("=" * 50)
    logger.info("  G-lassify — Personal AI Email Classifier")
    logger.info("=" * 50)

    # ── Step 1: Validate config ────────────────────────────────────────────
    validate_config()

    # ── Step 2: Authenticate with Gmail ────────────────────────────────────
    logger.info("Authenticating with Gmail...")
    service = get_gmail_service()

    # ── Step 3: Fetch recent emails ────────────────────────────────────────
    logger.info(f"Fetching emails from the last {args.hours} hours...")
    emails = fetch_recent_emails(service, hours=args.hours)

    if not emails:
        logger.info("No emails found in the specified time window.")
        if not args.dry_run:
            # Send a "no emails" digest
            now = datetime.now()
            no_email_html = _build_no_email_digest(now)
            send_digest(service, GMAIL_ADDRESS, no_email_html, now.strftime("%B %d"))
            logger.info("Sent 'no new emails' digest.")
        return

    logger.info(f"Retrieved {len(emails)} emails. Starting classification...")

    # ── Step 4: Classify emails ────────────────────────────────────────────
    classified = classify_batch(emails)

    # ── Step 5: Build digest ───────────────────────────────────────────────
    now = datetime.now()
    html_digest = build_digest(classified, date=now)

    # ── Step 6: Send or print ──────────────────────────────────────────────
    if args.dry_run:
        logger.info("DRY RUN — Printing digest HTML to stdout")
        print("\n" + "=" * 60)
        print("  DIGEST PREVIEW (HTML)")
        print("=" * 60 + "\n")
        print(html_digest)
        print("\n" + "=" * 60)

        # Also print a text summary
        print("\n  CLASSIFICATION SUMMARY:\n")
        for ce in classified:
            icon = {"Important & Urgent": "🚨", "Important & Not Urgent": "📌", "Not Important": "📨"}.get(
                ce.classification.priority, "•"
            )
            print(f"  {icon} [{ce.classification.priority}]")
            print(f"     From: {ce.email.sender_name}")
            print(f"     Subject: {ce.email.subject}")
            print(f"     Summary: {ce.classification.summary}")
            if ce.classification.action_items:
                for action in ce.classification.action_items:
                    print(f"     → {action}")
            print()
    else:
        date_str = now.strftime("%B %d")
        result = send_digest(service, GMAIL_ADDRESS, html_digest, date_str)
        if result:
            logger.info(f"🎉 Daily digest sent to {GMAIL_ADDRESS}")
        else:
            logger.error("Failed to send the daily digest.")
            sys.exit(1)

    logger.info("G-lassify run complete.")


def _build_no_email_digest(date: datetime) -> str:
    """Build a simple digest for when no emails were found."""
    return f"""\
<!DOCTYPE html>
<html>
<body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f0f2f5; padding: 24px 0;">
<tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width: 640px;">
  <tr>
    <td style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); padding: 32px 40px; border-radius: 16px 16px 0 0;">
      <h1 style="margin: 0 0 8px 0; font-size: 28px; color: #fff;">📬 G-lassify</h1>
      <p style="margin: 0; font-size: 16px; color: #a0aec0;">Daily Email Summary – {date.strftime("%B %d, %Y")}</p>
    </td>
  </tr>
  <tr>
    <td style="background-color: #fff; padding: 40px; text-align: center; border-radius: 0 0 16px 16px;">
      <p style="font-size: 48px; margin: 0;">🎉</p>
      <h2 style="margin: 16px 0 8px 0; color: #1a202c;">Inbox Zero!</h2>
      <p style="color: #718096; font-size: 15px;">No new emails in the last 24 hours. Enjoy your morning!</p>
    </td>
  </tr>
</table>
</td></tr>
</table>
</body>
</html>"""


if __name__ == "__main__":
    main()
