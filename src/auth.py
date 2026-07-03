"""
G-lassify Gmail Authentication
Handles OAuth 2.0 flow and token management for the Gmail API.
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import SCOPES, CREDENTIALS_FILE, TOKEN_FILE, logger


def get_gmail_service():
    """
    Authenticate with Gmail and return an authorized API service object.

    On first run, opens a browser for OAuth consent and saves the token.
    On subsequent runs, uses the cached token (refreshing if expired).

    Returns:
        googleapiclient.discovery.Resource: Authorized Gmail API service.
    """
    creds = None

    # Load existing token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        logger.debug("Loaded cached credentials from token.json")

    # Refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_FILE}. "
                    "Download it from Google Cloud Console."
                )
            logger.info("Starting OAuth flow — a browser window will open...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save the token for future runs
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())
        logger.info("Credentials saved to token.json")

    service = build("gmail", "v1", credentials=creds)
    logger.info("Gmail API service ready")
    return service
