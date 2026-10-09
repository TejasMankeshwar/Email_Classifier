# G-lassify: Employer-Friendly Project Explanation

## Project idea in one sentence
G-lassify is a personal email triage system that connects to Gmail, reads recent emails, uses Gemini AI to decide which ones matter most, and sends a clean daily summary email back to the user.

This project is useful because most people get too many emails every day. Instead of reading everything manually, the app filters the inbox into:

- Urgent and important
- Important but not urgent
- Low priority / noise

It then creates a digest email that helps the user focus on what really matters.

---

## Why this project is impressive
This project combines several real-world skills:

- Python programming
- Gmail API integration
- OAuth authentication
- AI/LLM prompt engineering
- Text parsing and email extraction
- HTML email generation
- Automation and scheduling on macOS
- API rate-limit handling and error management

From an employer perspective, this shows a person can build a practical automation tool that solves a real user problem using modern tools and APIs.

---

## High-level workflow
The system works like this:

1. The app loads configuration from environment variables and validates required setup.
2. It authenticates with Gmail using OAuth.
3. It fetches recent emails from the user’s inbox.
4. It extracts the sender, subject, date, and message body.
5. It sends those emails to Gemini 2.5 Flash with a classification prompt.
6. Gemini decides whether each email is urgent, important, or low priority.
7. The results are grouped and turned into a polished daily HTML email.
8. That digest is sent back to the user’s inbox.
9. On macOS, this can be scheduled automatically using launchd.

In simple terms: it reads the inbox, thinks like an assistant, and summarizes the important parts.

---

## How the app behaves in practice
When the script runs, it does not try to read the entire mailbox forever. It looks only at a time window, such as the last 24 hours.

For each email, it measures:

- Is this email personal and relevant?
- Is there a real action required?
- Is there a deadline or consequence?
- Is it just promotional or low-value noise?

Then it assigns one of the following labels:

- Important & Urgent
- Important & Not Urgent
- Not Important

This is a smart filtering system rather than a basic spam filter.

---

## File-by-file explanation of the src folder

### 1. src/__init__.py
This file is the package marker for the src folder. It does not do much logic by itself, but it tells Python that the folder is a package and can be imported as src.

In simple words: it makes the project importable and organizes the code into a reusable module.

---

### 2. src/config.py
This file handles the project configuration.

It does the following:

- loads environment variables from a .env file
- defines project paths like the root folder and templates folder
- stores the Gmail and Gemini settings
- defines the Gmail API scopes needed for login and sending email
- sets up logging so the program can print useful messages during execution
- validates that required configuration values are present before the app runs

In simple words: it is the project’s settings and safety check file.

---

### 3. src/auth.py
This file is responsible for Google authentication.

It does the following:

- checks whether a saved token already exists
- refreshes expired credentials if possible
- starts the OAuth login flow if the user has not previously authorized access
- saves the OAuth token to token.json so future runs are easier
- builds the Gmail API client service object that other files use

In simple words: this file logs into Gmail securely and gives the app permission to read and send emails.

---

### 4. src/gmail_reader.py
This file is the inbox reader.

It does the following:

- queries Gmail for messages received in the last N hours
- loops through matching emails
- fetches each message in raw MIME format
- decodes the email body
- extracts the sender, subject, date, and plain-text message content
- strips HTML from messages when needed
- removes unnecessary formatting so the AI can read it cleanly
- creates a simple EmailData object for each message

In simple words: this file reads the inbox and prepares each email for classification.

---

### 5. src/classifier.py
This is the AI brain of the project.

It defines structured schema models for the AI output and does the following:

- formats emails into a prompt for Gemini
- sends batches of emails to Gemini 2.5 Flash
- asks the model to classify each email into one of three priorities
- asks the model to produce a summary and action items
- handles retries if the API rate limits requests
- groups results back into a final list of classified emails

This file is important because it turns raw email content into decisions like:

- urgent and immediate action
- important but not urgent
- low priority marketing or noise

In simple words: this file decides which emails matter and which ones can be ignored.

---

### 6. src/digest_builder.py
This file turns the classified emails into a daily digest.

It does the following:

- groups emails by priority level
- counts how many are urgent, important, and low priority
- gathers action items from important emails
- creates a human-readable executive summary
- renders an HTML email template using Jinja2
- passes the data into templates/digest.html

In simple words: this file builds the final email the user receives every day.

---

### 7. src/gmail_sender.py
This file sends the final digest email.

It does the following:

- creates a MIME HTML email message
- adds the recipient and subject line
- encodes the message in the format Gmail expects
- calls the Gmail API to send the email

In simple words: this file delivers the summarized digest back to the user’s inbox.

---

### 8. src/main.py
This is the orchestrator or central controller of the project.

It does the following:

- parses command-line arguments like --hours and --dry-run
- validates the application configuration
- authenticates with Gmail
- fetches recent emails
- if no emails are found, builds an inbox-zero email
- classifies the emails
- builds the digest
- either prints the digest in dry-run mode or sends it to Gmail

In simple words: this is the main program flow that connects all the pieces together.

---

## End-to-end project flow
A simple way to explain the working of the project to an employer is:

1. User runs the automation.
2. The app reads the Gmail inbox for the last 24 hours.
3. Each email is parsed and cleaned.
4. Gemini AI decides which ones need action.
5. The app creates a custom HTML digest email.
6. That digest is sent to the user’s inbox.
7. The user gets a prioritized summary instead of reading every email individually.

The project is essentially an AI-powered personal inbox assistant.

---

## Supporting files outside src

### setup_auth.py
This file is a one-time setup script that helps the user log into Google and generate token.json.

It ensures authentication works before the main app runs.

### templates/digest.html
This file is the visual template for the digest email. It contains the HTML layout, styling, and sections for urgent, important, and low-priority emails.

It makes the result look like a polished business-style summary instead of raw text.

### README.md
This file explains setup instructions, prerequisites, and usage examples for the project.

---

## Why this is a strong portfolio project
This project demonstrates:

- API integration with real external systems
- AI-based decision-making
- practical automation for everyday productivity
- data cleaning and structured parsing
- secure authentication and environment-based configuration
- end-to-end product thinking from input to output

It is not just a demo script; it is a working personal productivity tool that solves a tangible problem.

---

## Short employer pitch
I built an AI-powered email assistant that reads a user’s Gmail account, classifies incoming emails based on urgency and relevance, and sends a clean daily digest summarizing the most important messages. The project uses Python, Gmail API, OAuth, and Gemini AI to turn a noisy inbox into a prioritized daily briefing that helps the user focus on what matters most.

---

## Summary
G-lassify is a practical AI workflow project that combines email automation, classification logic, secure authentication, and polished email output. It shows real-world software engineering skills and a strong understanding of building useful tools that connect different systems together.
