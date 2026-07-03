# 📬 G-lassify — Personal AI Email Classifier

G-lassify is a local Python automation that reads your Gmail every morning, classifies emails into three priority tiers using **Gemini 2.5 Flash**, and delivers a clean HTML digest back to your inbox.

**No frontend. No database. No deployment. No server costs.**  
Runs entirely on your Mac. Your emails stay under your control.

---

## ✨ Features

- 🔐 **Gmail OAuth** — Secure access to your inbox (read-only + send)
- 🤖 **Gemini 2.5 Flash** — AI-powered classification with structured output
- 🚨 **Three Priority Tiers** — Urgent, Important, and Low Priority
- 📊 **Executive Summary** — Key stats and action items at a glance
- 📧 **Beautiful HTML Digest** — Professional email delivered to your inbox
- ⏰ **Scheduled via launchd** — Runs every morning at 7:00 AM
- 🏃 **Dry-run mode** — Test without sending

---

## 🏗️ Project Structure

```
Email_Classifier/
├── README.md                         # This file
├── requirements.txt                  # Python dependencies
├── .env                              # Your API keys (not committed)
├── .env.example                      # Template for .env
├── credentials.json                  # Google OAuth credentials (not committed)
├── token.json                        # OAuth token (auto-generated)
├── setup_auth.py                     # One-time OAuth setup
├── src/
│   ├── __init__.py
│   ├── main.py                       # Entry point / orchestrator
│   ├── config.py                     # Configuration & environment
│   ├── auth.py                       # Gmail OAuth authentication
│   ├── gmail_reader.py               # Fetch & parse emails
│   ├── classifier.py                 # Gemini 2.5 Flash classification
│   ├── digest_builder.py             # Build HTML digest
│   └── gmail_sender.py              # Send digest via Gmail
├── templates/
│   └── digest.html                   # Jinja2 email template
└── com.glassify.emaildigest.plist    # macOS launchd schedule
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Google Cloud Project** with Gmail API enabled
- **Gemini API Key** from [aistudio.google.com](https://aistudio.google.com)

### 1. Clone & Setup Virtual Environment

```bash
cd ~/Developer/Projects/Email_Classifier
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Your `.env` file should contain:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GMAIL_ADDRESS=mtejas619@gmail.com
EMAIL_BODY_MAX_CHARS=2000
LOG_LEVEL=INFO
```

### 3. Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or select an existing one)
3. Enable the **Gmail API** (API Library → search "Gmail API" → Enable)
4. Configure **OAuth Consent Screen** (External, add your email as test user)
5. Create **Credentials** → OAuth Client ID → Desktop App
6. Download `credentials.json` to the project root

### 4. First-Time Authentication

```bash
python setup_auth.py
```

This opens your browser for OAuth consent. After authorizing, `token.json` is saved automatically.

### 5. Test with Dry Run

```bash
# Classify last 24 hours, print to terminal (no email sent)
python -m src.main --dry-run

# Classify last 2 hours for a quick test
python -m src.main --dry-run --hours 2
```

### 6. Run for Real

```bash
python -m src.main
```

This classifies your emails and sends the digest to your inbox!

---

## ⏰ Schedule Daily Runs (macOS launchd)

### Setup

```bash
# Create the log directory
mkdir -p ~/Library/Logs/glassify

# Copy the plist to LaunchAgents
cp com.glassify.emaildigest.plist ~/Library/LaunchAgents/

# Load the schedule
launchctl load ~/Library/LaunchAgents/com.glassify.emaildigest.plist

# Verify it's loaded
launchctl list | grep glassify
```

### Manage

```bash
# Unload (stop scheduling)
launchctl unload ~/Library/LaunchAgents/com.glassify.emaildigest.plist

# Check logs
tail -f ~/Library/Logs/glassify/stdout.log
tail -f ~/Library/Logs/glassify/stderr.log
```

---

## 🎯 CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--hours N` | Look back N hours for emails | `24` |
| `--dry-run` | Print digest to terminal, don't send | `false` |

**Examples:**

```bash
python -m src.main                      # Normal run
python -m src.main --dry-run            # Preview without sending
python -m src.main --hours 48           # Last 48 hours
python -m src.main --dry-run --hours 2  # Quick test
```

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `credentials.json not found` | Download from Google Cloud Console → Credentials |
| `Token expired / invalid_grant` | Delete `token.json` and run `python setup_auth.py` again |
| `GEMINI_API_KEY not set` | Add your key to `.env` |
| `Gmail API not enabled` | Enable it in Google Cloud Console → API Library |
| `launchd not running` | Check `launchctl list \| grep glassify` and review logs |
| `Permission denied` | Ensure the venv Python path in the plist is correct |

---

## 📧 Example Digest

The digest email includes:

- **🚨 Important & Urgent** — Emails requiring action today (red cards)
- **📌 Important & Not Urgent** — Worth reviewing later (blue cards)
- **📨 Not Important** — Collapsed counts by category (gray)
- **📊 Executive Summary** — Stats bar + key action items
- **Branded footer** — Powered by Gemini 2.5 Flash

---

## 🔒 Privacy

- Emails are processed locally on your Mac
- Only email content is sent to Gemini for classification
- `credentials.json`, `token.json`, and `.env` are git-ignored
- No data is stored or logged beyond the current run

---

Built with ❤️ using Python, Gmail API, and Gemini 2.5 Flash
