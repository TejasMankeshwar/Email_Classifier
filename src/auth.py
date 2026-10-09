"""
G-lassify Gmail Authentication
Handles OAuth 2.0 flow and token management for the Gmail API.
"""

import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import SCOPES, CREDENTIALS_FILE, TOKEN_FILE, logger


def get_gmail_service(token_file: str | Path | None = None):
    """
    Authenticate with Gmail and return an authorized API service object.

    On first run, opens a browser for OAuth consent and saves the token.
    On subsequent runs, uses the cached token (refreshing if expired).

    Args:
        token_file: Custom Path or filename for the OAuth token file. Defaults to TOKEN_FILE.

    Returns:
        googleapiclient.discovery.Resource: Authorized Gmail API service.
    """
    token_path = Path(token_file) if token_file else TOKEN_FILE
    creds = None

    # Load existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        logger.debug(f"Loaded cached credentials from {token_path.name}")

    # Refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info(f"Refreshing expired credentials for {token_path.name}...")
            from google.auth.exceptions import RefreshError
            try:
                creds.refresh(Request())
            except RefreshError as e:
                logger.error(f"Failed to refresh credentials: {e}")
                logger.error(
                    "This usually means the refresh token has expired or been revoked.\n"
                    "If your Google Cloud OAuth app is in 'Testing' mode, tokens expire after 7 days.\n"
                    "To fix this:\n"
                    "  1. Go to Google Cloud Console -> APIs & Services -> OAuth consent screen.\n"
                    "  2. Change publishing status to 'In Production' so tokens don't expire.\n"
                    "  3. Delete the token file and run setup_auth.py locally to generate a new token."
                )
                raise e
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_FILE}. "
                    "Download it from Google Cloud Console."
                )
            logger.info(f"Starting OAuth flow for {token_path.name} — a browser window will open...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save the token for future runs
        with open(token_path, "w") as tf:
            tf.write(creds.to_json())
        logger.info(f"Credentials saved to {token_path.name}")

    service = build("gmail", "v1", credentials=creds)
    logger.info("Gmail API service ready")
    return service

