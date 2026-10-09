#!/usr/bin/env python3
"""
G-lassify — One-Time OAuth Setup
Run this script once to authenticate with Gmail and generate token.json.

Usage:
    python setup_auth.py
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import validate_config, logger, PROJECT_ROOT
from src.auth import get_gmail_service


def main():
    parser = argparse.ArgumentParser(
        description="G-lassify — Gmail OAuth Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        help="Account identifier/label (e.g. 'work' creates 'token_work.json')",
    )
    parser.add_argument(
        "--token-file",
        type=str,
        default=None,
        help="Custom filename or path for the OAuth token (default: token.json)",
    )
    args = parser.parse_args()

    token_filename = "token.json"
    if args.token_file:
        token_filename = args.token_file
    elif args.account:
        token_filename = f"token_{args.account}.json"

    token_path = Path(token_filename)
    if not token_path.is_absolute():
        token_path = PROJECT_ROOT / token_filename

    print()
    print("=" * 60)
    print("  G-lassify — Gmail OAuth Setup")
    print("=" * 60)
    print()
    print(f"Target token file: {token_path.name}")
    print("This will open your browser to authorize Gmail access.")
    print("Make sure you log into the correct Google Account in your browser!")
    print()

    # Validate configuration
    validate_config()

    # Run the auth flow
    service = get_gmail_service(token_file=token_path)

    # Verify it works by fetching the user's profile
    try:
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "unknown")
        total = profile.get("messagesTotal", 0)
        print()
        print(f"✅ Successfully authenticated as: {email}")
        print(f"   Total messages in mailbox: {total:,}")
        print(f"   Token saved to: {token_path.name}")
        print()
        print("You're all set! To run G-lassify for this account:")
        print(f"  python -m src.main --token-file {token_path.name}")
        print()
    except Exception as e:
        logger.error(f"Authentication succeeded but verification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

