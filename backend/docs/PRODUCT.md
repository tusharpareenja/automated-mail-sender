# AI Email Campaign Platform

## Product Overview

We are building an AI-powered email campaign management platform.

The platform allows users to connect SMTP accounts, upload lead data through CSV files, create reusable email templates, personalize emails using OpenAI, send campaigns through background workers, and monitor email activity through a real-time dashboard.

---

# Core User Flow

The main user journey is:

User
→ Add SMTP account
→ Create template
→ Upload CSV
→ Map CSV columns
→ Create campaign
→ Select leads
→ Select template
→ Configure AI personalization
→ Select SMTP account
→ Preview generated emails
→ Send test email
→ Review campaign
→ Launch
→ Monitor campaign

---

# Main Modules

## Dashboard

Shows:

- active campaigns
- total leads
- sent emails
- tracked open signals
- clicks
- failures
- bounce signals
- recent activity

---

## SMTP Accounts

Users can:

- add SMTP accounts
- edit accounts
- remove accounts
- test connection
- send test emails
- configure sending limits
- view account health

SMTP passwords must never be displayed after saving.

---

## Templates

Users can:

- create templates
- edit templates
- duplicate templates
- delete templates
- preview templates

Templates support:

{{first_name}}
{{last_name}}
{{company}}
{{title}}
{{industry}}
{{website}}

and dynamic custom fields from CSV data.

---

## Leads

Users can upload CSV files containing lead information.

The system dynamically maps CSV columns.

Example:

First Name → first_name

Company → company

Job Title → title

Email → email

Additional columns become custom fields.

---

## Campaigns

Campaigns connect:

- leads
- templates
- SMTP accounts
- AI personalization
- sending configuration
- tracking

Campaign states:

DRAFT
QUEUED
RUNNING
PAUSED
COMPLETED
CANCELLED
FAILED

---

# AI Personalization

OpenAI is used to generate controlled personalization based on available lead/company information.

The AI must not invent facts.

The system should prefer generating specific personalization fields instead of rewriting the entire email.

Generated content should be previewable before campaign launch.

---

# Email Sending

Email sending is asynchronous.

The API does not send large batches directly.

Campaign emails are queued and processed by workers.

The system respects:

- SMTP limits
- campaign limits
- configured delays
- suppression rules
- unsubscribe rules

---

# Tracking

Each outgoing email can contain a unique tracking pixel.

Tracked events include:

OPENED
CLICKED

Open tracking is considered a signal, not guaranteed proof that a person read the email.

Tracked events are stored in the backend.

WebSockets broadcast new events to the dashboard.

---

# Deliverability

The product does not guarantee inbox placement.

The platform should support responsible deliverability practices:

- SPF
- DKIM
- DMARC
- rate limiting
- controlled sending
- bounce handling
- suppression
- unsubscribe
- duplicate prevention
- sender/account health

The system must not attempt to bypass spam filters or provider controls.

---

# User Experience

The product should feel like a professional SaaS platform.

The interface should be:

- clean
- fast
- responsive
- accessible
- consistent
- predictable
- easy to understand

Every important action should provide clear feedback.

---

# Product Principle

The user should always understand:

1. What the system is doing
2. Why it is doing it
3. What will happen next
4. Whether the action succeeded
5. What they can do if something fails


# API Architecture

## Single API Base URL

The frontend MUST use an environment variable as the single source of truth for the backend API base URL.

Example:

NEXT_PUBLIC_API_BASE_URL=https://api.mindsoft.com/api/v1

For local development:

NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

The API base URL must NEVER be hard-coded inside:

- components
- pages
- hooks
- services
- utilities
- API functions
- WebSocket clients

If the API base URL changes in `.env`, the entire frontend must automatically use the new URL without requiring manual changes anywhere else.

---

## API Service Architecture

All backend communication must go through the `lib` directory.

Recommended structure:

lib/
  api/
    client.ts
    auth.ts
    smtp.ts
    templates.ts
    leads.ts
    campaigns.ts
    analytics.ts
    tracking.ts

  config/
    env.ts

No React component should directly use `fetch()` or `axios()` for backend API calls.

Bad:

```ts
fetch("https://api.mindsoft.com/api/v1/campaigns")