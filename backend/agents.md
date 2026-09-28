# Backend Engineering Rules

## Project

We are building a production-grade AI-powered email campaign management platform.

Technology:

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Redis
- Celery/background workers
- OpenAI API
- WebSockets

Primary backend priorities:

1. Correctness
2. Security
3. Reliability
4. Scalability
5. Observability
6. Maintainability
7. Performance

---

# 1. ARCHITECTURE

Use clear separation of concerns.

Recommended structure:

app/
    main.py

    api/
        auth.py
        smtp.py
        templates.py
        leads.py
        campaigns.py
        analytics.py
        tracking.py
        websocket.py

    core/
        config.py
        security.py
        database.py
        logging.py

    models/

    schemas/

    repositories/

    services/
        smtp_service.py
        template_service.py
        campaign_service.py
        lead_service.py
        openai_service.py
        tracking_service.py

    workers/
        celery_app.py
        email_tasks.py

    utils/

tests/

Do not put business logic directly inside route handlers.

Routes should primarily:

1. validate request
2. authenticate/authorize
3. call service
4. return response

---

# 2. DATABASE

Use PostgreSQL.

Use SQLAlchemy for database access.

Use Alembic for migrations.

Never manually modify production database schema.

Every schema change requires an Alembic migration.

Use:

- foreign keys
- unique constraints
- check constraints where useful
- indexes
- timestamps

Avoid N+1 queries.

Use transactions deliberately.

---

# 3. DATA MODEL

Core entities:

User

SMTPAccount

Template

Lead

Campaign

CampaignLead

CampaignEmail

EmailEvent

TrackedLink

SuppressionEntry

UnsubscribeEvent

Use JSONB for flexible custom lead fields.

Do not create database columns for every possible future CSV field.

---

# 4. MULTI-TENANCY / AUTHORIZATION

Every resource must belong to the authenticated user/tenant.

Never trust IDs supplied by the frontend.

For every request:

1. authenticate user
2. verify ownership/authorization
3. access resource

Prevent:

IDOR
cross-user data access
unauthorized campaign access
unauthorized SMTP access

---

# 5. API DESIGN

Use RESTful APIs.

Example:

POST   /api/v1/smtp
GET    /api/v1/smtp
GET    /api/v1/smtp/{id}
PATCH  /api/v1/smtp/{id}
DELETE /api/v1/smtp/{id}

POST   /api/v1/templates
GET    /api/v1/templates
PATCH  /api/v1/templates/{id}

POST   /api/v1/leads/import

POST   /api/v1/campaigns
GET    /api/v1/campaigns
GET    /api/v1/campaigns/{id}

POST   /api/v1/campaigns/{id}/start
POST   /api/v1/campaigns/{id}/pause
POST   /api/v1/campaigns/{id}/resume
POST   /api/v1/campaigns/{id}/cancel

GET    /api/v1/campaigns/{id}/analytics

Tracking endpoints:

GET /t/o/{token}.png
GET /t/c/{token}
GET /unsubscribe/{token}

Version APIs.

Use:

/api/v1/...

Do not expose internal database implementation details through API responses.

---

# 6. RESPONSE FORMAT

Use consistent API responses.

Success responses should have predictable structure.

Errors should contain:

- machine-readable error code
- human-readable message
- optional validation details

Do not expose stack traces to clients.

---

# 7. SMTP CREDENTIAL SECURITY

SMTP credentials are sensitive.

Never store passwords in plaintext.

Encrypt credentials before database storage.

Encryption keys must come from environment/configuration.

Never return SMTP passwords in API responses.

Never log SMTP passwords.

Never include secrets in exception messages.

---

# 8. EMAIL SENDING ARCHITECTURE

NEVER send large campaigns directly inside FastAPI request handlers.

Correct architecture:

API
 ↓
Database
 ↓
Redis
 ↓
Celery worker
 ↓
SMTP provider

The API creates/schedules work.

Workers perform sending.

---

# 9. IDEMPOTENCY

Email sending must be idempotent.

A worker retry must not accidentally send the same email twice.

Before sending:

- verify current email status
- acquire appropriate lock/claim
- transition state atomically

After successful SMTP submission:

- record send state atomically

Use database constraints and locking where appropriate.

---

# 10. CAMPAIGN STATE MACHINE

Campaign states:

DRAFT
QUEUED
RUNNING
PAUSED
COMPLETED
CANCELLED
FAILED

Email states:

QUEUED
GENERATING
READY
SENDING
SENT
FAILED
BOUNCED

Engagement should be represented as events rather than blindly replacing delivery state.

Example:

SENT
+
OPENED event
+
CLICKED event

---

# 11. BACKGROUND WORKERS

Workers must be:

- retryable
- idempotent
- observable
- horizontally scalable

Transient errors:

- retry with exponential backoff

Permanent errors:

- mark failed
- do not endlessly retry

Worker crashes must not corrupt campaign state.

---

# 12. RATE LIMITING

Sending limits must be enforced server-side.

Support:

- per SMTP account hourly limit
- per SMTP account daily limit
- campaign-level limit
- optional global limits

Never rely on frontend validation for limits.

Multiple workers must not bypass limits.

Use Redis/database coordination where appropriate.

---

# 13. SMTP ROTATION

If a campaign has multiple SMTP accounts:

- select only active accounts
- respect per-account limits
- track usage atomically
- avoid unhealthy accounts
- stop selecting an account after configured limit
- recover accounts when appropriate

Do not implement naive:

account = accounts[index % len(accounts)]

because multiple workers can cause race conditions and limit violations.

---

# 14. EMAIL DELIVERABILITY

The system must be designed for responsible email delivery.

IMPORTANT:

No application can guarantee inbox placement.

The backend should support practices that reduce avoidable deliverability problems:

- SPF/DKIM/DMARC guidance
- configurable sending limits
- gradual sending
- bounce handling
- suppression lists
- unsubscribe handling
- duplicate prevention
- complaint-aware suppression
- domain/account health monitoring
- avoiding sudden sending spikes
- respecting SMTP/provider limits

Do not implement mechanisms intended to bypass provider spam controls.

Do not implement deceptive sender identity.

Do not fabricate personalization.

---

# 15. EMAIL CONTENT

AI-generated personalization must use only available/verified data.

The AI must NOT:

- invent company facts
- invent achievements
- claim to have spoken with someone
- claim to have visited a website unless actually done
- fabricate research
- fabricate metrics

If personalization generation fails:

use a safe fallback template.

---

# 16. OPENAI SERVICE

OpenAI calls must be isolated behind a service layer.

Example:

services/openai_service.py

The rest of the application should not directly depend on OpenAI SDK calls.

The service should handle:

- request construction
- structured output validation
- timeout
- retry strategy
- error handling
- usage logging
- model configuration

Never expose OpenAI API keys.

Do not make unnecessary OpenAI requests.

Cache/reuse generated content where appropriate.

---

# 17. TRACKING

Each outgoing email should receive a secure random tracking token.

Do not use predictable IDs as tracking tokens.

Open tracking:

GET /t/o/{token}.png

Click tracking:

GET /t/c/{token}

Validate tokens before processing.

Record events such as:

OPENED
CLICKED

Store:

- email_id
- event_type
- timestamp
- minimal useful metadata

Do not collect unnecessary personal information.

---

# 18. OPEN TRACKING LIMITATION

Open tracking is not definitive proof of human reading.

Email clients and privacy systems may:

- preload images
- proxy images
- cache tracking pixels
- suppress image loading

Therefore the system should call these:

"tracked open signals"

rather than treating them as guaranteed reads.

---

# 19. CLICK TRACKING

Tracked redirects must only redirect to URLs associated with the original email/link.

Prevent open redirect vulnerabilities.

Do not accept arbitrary redirect destinations from untrusted requests.

Validate stored destination URLs.

---

# 20. UNSUBSCRIBE / SUPPRESSION

Before sending every email:

1. check suppression list
2. check unsubscribe status
3. check campaign-level suppression
4. check lead validity

If suppressed:

do not send.

Unsubscribe must take effect immediately for future sends.

---

# 21. CSV IMPORT

CSV import should be asynchronous for large files.

Pipeline:

upload
 ↓
validate
 ↓
parse
 ↓
map columns
 ↓
deduplicate
 ↓
persist
 ↓
return import result

Do not load massive CSV files entirely into memory.

Validate:

- email syntax
- required fields
- duplicates
- malformed rows

Store custom fields in JSONB.

---

# 22. DATABASE PERFORMANCE

Use indexes for common query patterns.

Likely indexes:

leads(email)

campaigns(user_id, created_at)

campaign_emails(campaign_id, status)

campaign_emails(tracking_token)

email_events(email_id, created_at)

suppression_entries(email)

Do not add indexes blindly.

Verify query patterns first.

Use EXPLAIN ANALYZE for performance investigation.

---

# 23. PAGINATION

Never return unlimited database rows.

Use pagination for:

- leads
- campaigns
- email history
- events
- SMTP accounts where appropriate

Prefer cursor/keyset pagination for very large datasets.

---

# 24. CONCURRENCY

Assume multiple workers may execute simultaneously.

Protect:

- sending limits
- email state transitions
- campaign state transitions
- SMTP account usage
- duplicate sending

Do not assume single-process execution.

---

# 25. WEBSOCKETS

WebSockets are for real-time event delivery to clients.

They are NOT responsible for detecting email opens.

Architecture:

Tracking endpoint
 ↓
record event
 ↓
publish event
 ↓
WebSocket
 ↓
frontend

WebSocket failures must not affect email tracking persistence.

---

# 26. OBSERVABILITY

Use structured logging.

Important events:

- campaign_created
- campaign_started
- campaign_paused
- campaign_completed
- email_queued
- email_sent
- email_failed
- email_opened
- email_clicked
- email_bounced
- unsubscribe_created
- ai_generation_failed

Never log:

- passwords
- API keys
- access tokens
- SMTP credentials

---

# 27. ERROR HANDLING

Use explicit exception types.

Distinguish:

- validation errors
- authorization errors
- not found
- rate limits
- provider errors
- transient infrastructure errors
- permanent email errors

Do not use broad:

except Exception:

unless it is at a deliberate application boundary with logging and safe recovery.

---

# 28. SECURITY

Implement:

- authentication
- authorization
- input validation
- rate limiting
- secure secrets
- encrypted SMTP credentials
- secure random tokens
- CSRF protection where applicable
- safe redirect validation
- SQL injection protection through ORM/query parameters
- secure CORS configuration

Never trust client-side validation.

---

# 29. ALEMBIC

All database changes must go through Alembic.

Before creating a migration:

1. understand current schema
2. modify SQLAlchemy models
3. generate/review migration
4. verify upgrade
5. verify downgrade where appropriate

Never blindly accept autogenerated migrations without reviewing them.

---

# 30. TESTING

Write tests for critical paths.

At minimum:

Authentication
Authorization
SMTP credential handling
CSV parsing
Lead deduplication
Campaign state transitions
Email idempotency
Rate limiting
Suppression checking
Unsubscribe
Open tracking
Click tracking
AI failure fallback
API validation

Critical business logic should have unit tests.

Important workflows should have integration tests.

---

# 31. SCALABILITY

Design stateless FastAPI API servers.

Multiple API instances should be able to run simultaneously.

Workers should be horizontally scalable.

Shared state belongs in:

- PostgreSQL
- Redis
- object storage where appropriate

Do not store critical application state in process memory.

---

# 32. API PERFORMANCE

Do not perform expensive operations synchronously inside normal API requests.

Examples:

Bad:

POST /campaign/start
    -> generate 10,000 AI emails
    -> send 10,000 emails
    -> return response

Good:

POST /campaign/start
    -> validate
    -> update campaign state
    -> enqueue work
    -> return

Workers handle expensive processing.

---

# 33. CONFIGURATION

Use environment variables.

Required examples:

DATABASE_URL
REDIS_URL
OPENAI_API_KEY
SECRET_KEY
ENCRYPTION_KEY
FRONTEND_URL
API_PUBLIC_URL

Provide:

.env.example

Never commit secrets.

---

# 34. CODE QUALITY

Use:

- type hints
- Pydantic schemas
- service layer
- repository pattern where justified
- dependency injection
- clear naming

Avoid:

- giant route handlers
- circular imports
- global mutable state
- duplicated business logic
- unnecessary abstractions
- hidden side effects

---

# 35. IMPLEMENTATION RULE

Before changing code:

1. inspect the existing repository
2. understand existing architecture
3. identify affected modules
4. identify database implications
5. identify API contract implications
6. identify concurrency implications
7. implement
8. test
9. run lint/type checks
10. verify existing functionality

Do not rewrite unrelated code.

---

# 36. DEFINITION OF DONE

A backend feature is complete only when:

- API works
- authentication works
- authorization works
- validation works
- database changes have migrations
- error handling exists
- concurrency is considered
- tests exist for critical behavior
- logs are appropriate
- secrets are protected
- no obvious N+1 queries exist
- API does not perform unnecessary blocking work
- existing functionality still works