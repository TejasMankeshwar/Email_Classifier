#!/usr/bin/env python3
"""
G-lassify — One-Time OAuth Setup
Run this script once to authenticate with Gmail and generate token.json.

Usage:
    python setup_auth.py
"""

import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import validate_config, logger
from src.auth import get_gmail_service


def main():
    print()
    print("=" * 60)
    print("  G-lassify — Gmail OAuth Setup")
    print("=" * 60)
    print()
    print("This will open your browser to authorize Gmail access.")
    print("Make sure you have credentials.json in the project root.")
    print()

    # Validate configuration
    validate_config()

    # Run the auth flow
    service = get_gmail_service()

    # Verify it works by fetching the user's profile
    try:
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "unknown")
        total = profile.get("messagesTotal", 0)
        print()
        print(f"✅ Successfully authenticated as: {email}")
        print(f"   Total messages in mailbox: {total:,}")
        print()
        print("You're all set! token.json has been saved.")
        print("Run the classifier with: python -m src.main --dry-run")
        print()
    except Exception as e:
        logger.error(f"Authentication succeeded but verification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
