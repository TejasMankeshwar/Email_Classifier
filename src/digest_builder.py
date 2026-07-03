"""
G-lassify Digest Builder
Groups classified emails and renders them into a clean HTML digest.
"""

from collections import Counter
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

from src.classifier import ClassifiedEmail
from src.config import TEMPLATES_DIR, logger


def build_digest(classified_emails: list[ClassifiedEmail], date: datetime | None = None) -> str:
    """
    Build an HTML digest email from classified emails.

    Args:
        classified_emails: List of classified emails.
        date: Date for the digest header (defaults to today).

    Returns:
        Complete HTML string ready to send.
    """
    if date is None:
        date = datetime.now()

    # Group by priority
    urgent = [e for e in classified_emails if e.classification.priority == "Important & Urgent"]
    important = [e for e in classified_emails if e.classification.priority == "Important & Not Urgent"]
    not_important = [e for e in classified_emails if e.classification.priority == "Not Important"]

    # For "Not Important", collapse into category counts
    not_important_counts = Counter(e.classification.category for e in not_important)
    # Format category counts nicely
    not_important_summary = []
    category_labels = {
        "promotion": "promotional emails",
        "newsletter": "newsletters",
        "social": "social notifications",
        "security": "security alerts",
        "general": "other notifications",
        "financial": "financial notifications",
        "academic": "academic notifications",
        "recruitment": "recruitment emails",
    }
    for cat, count in not_important_counts.most_common():
        label = category_labels.get(cat, f"{cat} emails")
        not_important_summary.append({"count": count, "label": label})

    # Build executive summary
    total = len(classified_emails)
    urgent_count = len(urgent)
    important_count = len(important)
    not_important_count = len(not_important)

    # Identify the top action item
    top_actions = []
    for e in urgent:
        for action in e.classification.action_items:
            top_actions.append(action)
    for e in important:
        for action in e.classification.action_items:
            top_actions.append(action)

    executive_summary = _build_executive_summary(
        total, urgent_count, important_count, not_important_count, top_actions
    )

    # Render template
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    template = env.get_template("digest.html")

    html = template.render(
        date=date.strftime("%B %d, %Y"),
        date_short=date.strftime("%B %d"),
        urgent_emails=urgent,
        important_emails=important,
        not_important_summary=not_important_summary,
        not_important_count=not_important_count,
        total_count=total,
        urgent_count=urgent_count,
        important_count=important_count,
        executive_summary=executive_summary,
    )

    logger.info(
        f"Digest built: {urgent_count} urgent, {important_count} important, "
        f"{not_important_count} low-priority"
    )
    return html


def _build_executive_summary(
    total: int,
    urgent_count: int,
    important_count: int,
    not_important_count: int,
    top_actions: list[str],
) -> str:
    """Generate a human-readable executive summary paragraph."""
    parts = []

    parts.append(
        f"You received {total} email{'s' if total != 1 else ''} in the past 24 hours."
    )

    if urgent_count > 0:
        parts.append(
            f"{urgent_count} require{'s' if urgent_count == 1 else ''} immediate action"
        )
    if important_count > 0:
        parts.append(
            f"{',' if urgent_count > 0 else ''} {important_count} "
            f"{'is' if important_count == 1 else 'are'} worth reviewing later"
        )
    if not_important_count > 0:
        parts.append(
            f", and the remaining {not_important_count} "
            f"{'is' if not_important_count == 1 else 'are'} low priority"
        )

    summary = " ".join(parts).replace("  ", " ") + "."

    # Add top actions
    if top_actions:
        top = top_actions[:3]  # Limit to top 3
        if len(top) == 1:
            summary += f" The most important task is: {top[0]}."
        else:
            actions_text = "; ".join(top)
            summary += f" Key action items: {actions_text}."

    return summary
