# Frontend Engineering Rules

## Project

We are building a production-grade AI-powered email campaign management platform.

The frontend is responsible for:

- Authentication
- Dashboard
- SMTP account management
- Email template management
- CSV/lead management
- Campaign creation
- Campaign monitoring
- Real-time campaign analytics
- Settings
- Error/loading/empty states

Technology:

- Next.js
- TypeScript
- React
- Tailwind CSS
- Use the existing UI component system when available.

---

# 1. PRIMARY FRONTEND OBJECTIVE

The frontend must feel like a serious production SaaS product.

Priorities, in order:

1. Excellent UX
2. Clear information architecture
3. Visual consistency
4. Accessibility
5. Responsive behavior
6. Performance
7. Maintainability

Do not build generic-looking CRUD pages.

The UI should feel intentional, polished and professional.

---

# 2. DESIGN PRINCIPLES

Use:

- strong visual hierarchy
- consistent spacing
- predictable navigation
- clear typography
- restrained use of colors
- meaningful empty states
- meaningful loading states
- meaningful error states
- clear success feedback
- confirmation for destructive actions

Avoid:

- unnecessary gradients
- excessive rounded cards
- excessive animations
- huge headings
- inconsistent spacing
- random colors
- excessive shadows
- cluttered dashboards
- UI elements that look clickable but are not
- buttons that do nothing

Do not copy a design blindly from another product.

Use external design references only as inspiration and adapt them to this product.

---

# 3. RESPONSIVE DESIGN

Every page must work properly on:

- mobile
- tablet
- laptop
- desktop
- large desktop

Never design only for 1440px desktop.

Test important layouts at approximately:

- 320px
- 375px
- 768px
- 1024px
- 1280px
- 1440px+

Tables should have a deliberate responsive strategy.

Do NOT simply allow the entire page to overflow horizontally.

For complex tables:

- use horizontal scrolling inside the table container
- keep important columns visible where practical
- provide mobile-friendly alternatives when necessary

---

# 4. INTERACTION RULES

Every interactive element must clearly look interactive.

Clickable elements must have:

- `cursor-pointer`
- hover state
- focus state
- disabled state where applicable
- loading state where applicable

Do not add pointer cursor to elements that are not actually interactive.

Buttons must never appear clickable if they do nothing.

Every async action must communicate state.

Example:

Normal:

"Send Test Email"

Loading:

"Sending..."

Success:

"Test email sent"

Error:

"Failed to send"

---

# 5. ACCESSIBILITY

Follow accessible HTML and interaction patterns.

Use:

- semantic HTML
- labels for form controls
- accessible buttons
- keyboard navigation
- visible focus states
- appropriate ARIA attributes when required
- sufficient color contrast

Do not rely on color alone to communicate state.

For example:

Do not show only:

🟢 Sent

Prefer:

✓ Sent

with appropriate visual styling.

---

# 6. FORMS

Forms must have:

- clear labels
- useful placeholders
- validation
- error messages
- loading states
- success feedback
- disabled states

Do not hide important validation errors inside console logs.

For destructive actions:

- show confirmation
- clearly explain consequences

Example:

Deleting an SMTP account should explain whether existing campaigns are affected.

---

# 7. DASHBOARD

The main dashboard should quickly communicate:

- active campaigns
- total leads
- emails sent
- tracked opens
- clicks
- failures
- bounce signals
- recent campaign activity

Do not fill the dashboard with meaningless charts.

Every chart must answer a useful question.

---

# 8. CAMPAIGN UI

Campaign creation should be a guided workflow.

Recommended structure:

1. Campaign details
2. Select/upload leads
3. Map CSV columns
4. Select template
5. Configure AI personalization
6. Select sending account
7. Configure sending limits
8. Preview generated emails
9. Send test email
10. Review campaign
11. Launch

The user should always understand:

- where they are
- what remains
- what will happen next

Do not allow accidental campaign launch.

---

# 9. CSV EXPERIENCE

CSV upload should clearly show:

- selected file
- row count
- valid records
- invalid records
- duplicates
- column mapping
- preview rows

Column mapping must be visually obvious.

Example:

CSV column:

`First Name`

maps to:

`first_name`

Allow custom fields.

Do not assume CSV headers are fixed.

---

# 10. EMAIL TEMPLATE UI

Template editor should support:

- subject
- HTML body
- plain text
- variables
- AI personalization instructions
- preview

Show available variables clearly.

Example:

{{first_name}}
{{company}}
{{title}}

Custom CSV fields should also be available.

---

# 11. AI PERSONALIZATION UI

AI generation must not feel like a black box.

Show:

- source information
- generated personalization
- preview
- regeneration option
- failure state

Never silently replace user content.

If AI generation fails, explain what happened and provide a fallback.

---

# 12. CAMPAIGN MONITORING

Campaign detail page should show:

- campaign status
- progress
- sent
- queued
- failed
- bounce signals
- tracked opens
- clicks
- unsubscribes

Provide:

- pause
- resume
- cancel

with appropriate confirmation.

Real-time events should update the UI without requiring a page refresh.

---

# 13. REAL-TIME EVENTS

WebSocket events may include:

- EMAIL_SENT
- EMAIL_FAILED
- EMAIL_OPENED
- LINK_CLICKED
- EMAIL_BOUNCED
- EMAIL_UNSUBSCRIBED

The frontend must gracefully handle:

- connection
- reconnect
- disconnect
- stale connection
- authentication failure

Do not crash the dashboard if WebSocket connectivity fails.

The application should continue functioning using normal API requests.

---

# 14. LOADING STATES

Every page and major component must have intentional loading behavior.

Use:

- skeletons
- spinners where appropriate
- disabled buttons
- optimistic updates only where safe

Avoid blank white screens.

---

# 15. ERROR HANDLING

Errors must be understandable to users.

Bad:

"AxiosError 500"

Good:

"Unable to load SMTP accounts. Please try again."

Developer details may be logged separately.

---

# 16. API LAYER

Do not call backend APIs directly from random components.

Create a structured API/client layer.

Example:

lib/
  api/
    auth.ts
    smtp.ts
    templates.ts
    leads.ts
    campaigns.ts
    analytics.ts

Components should not contain duplicated API logic.

---

# 17. STATE MANAGEMENT

Do not introduce global state unnecessarily.

Use local state for local UI concerns.

Use server-state/data-fetching patterns for server data.

Global state should be reserved for genuinely global concerns such as:

- authentication/session
- global UI state
- notifications where appropriate

Do not turn every API response into global state.

---

# 18. PERFORMANCE

Avoid:

- unnecessary client components
- unnecessary re-renders
- fetching the same data repeatedly
- rendering huge datasets directly

Use:

- pagination
- virtualization when necessary
- caching
- debounced search
- lazy loading where appropriate

Do not sacrifice maintainability for micro-optimizations.

---

# 19. SECURITY

Never expose:

- SMTP passwords
- OpenAI API keys
- backend secrets
- internal credentials

The frontend must only receive data required for the UI.

Never trust frontend authorization.

The backend is the final authority.

---

# 20. COMPONENT ARCHITECTURE

Prefer reusable components.

Potential structure:

components/
  ui/
  layout/
  dashboard/
  campaigns/
  leads/
  templates/
  smtp/
  analytics/

Avoid giant components.

If a component becomes difficult to understand, break it into smaller components based on responsibility.

---

# 21. ROUTES

Expected routes:

/login
/register
/dashboard
/campaigns
/campaigns/new
/campaigns/[id]
/leads
/templates
/templates/[id]
/smtp
/settings

Adapt to the existing application structure instead of blindly recreating routes.

---

# 22. CODE QUALITY

Use strict TypeScript.

Avoid:

- `any`
- duplicated logic
- magic strings
- massive components
- unnecessary abstractions
- dead code
- commented-out old implementations

Prefer readable code over clever code.

---

# 23. BEFORE IMPLEMENTING A FEATURE

Before coding:

1. inspect the existing codebase
2. understand existing architecture
3. reuse existing components
4. identify API contracts
5. identify loading/error states
6. identify responsive behavior
7. implement the smallest clean solution

Do not rewrite working parts of the application without a reason.

---

# 24. DEFINITION OF DONE

A frontend feature is NOT complete until:

- desktop works
- mobile works
- loading state exists
- error state exists
- empty state exists where applicable
- buttons have correct interaction states
- keyboard interaction works
- API errors are handled
- no console errors remain
- no TypeScript errors remain
- no obvious layout overflow exists
- existing functionality still works

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
