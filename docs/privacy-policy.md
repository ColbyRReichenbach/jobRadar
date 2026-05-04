# AppTrail Privacy Policy

Last updated: May 4, 2026

This policy explains what AppTrail collects, how that information is used, and what choices users have when they use the dashboard, backend services, and Chrome extension.

## Scope

This policy applies to:

- the AppTrail web dashboard
- the AppTrail backend and worker services
- the AppTrail Chrome extension

## Information AppTrail Stores

### Account data

When a user signs in, AppTrail stores the basic account data required to run the product:

- name
- email address
- profile image, when provided by Google
- internal account identifiers

### Job search data

AppTrail stores the records that make the workflow usable:

- applications
- companies
- recruiter and contact details
- interview records and notes
- saved search results
- resume profile data
- extraction reports and feedback
- Opportunity Radar profiles, runs, signals, briefs, and actions

### Connected-service data

If a user connects Gmail, AppTrail stores the data needed to support the product workflow:

- Gmail tokens
- email metadata
- message snippets and message content needed for classification, threading, and draft context

AppTrail may also classify job-related URLs found in user-owned Gmail messages and applications. Raw application, scheduling, candidate-home, status, magic-login, and tokenized links remain user-private and are stored only in encrypted, user-scoped form when needed for the user's own workflow.

With explicit Source Intelligence consent, AppTrail may use sanitized job-source metadata derived from applications or Gmail messages to improve visible product features such as company job search, Opportunity Radar reports, and source-health checks. This shared metadata is limited to public provider/source information such as ATS provider type, public board or site identifiers, company domains when safely known, verification status, and redacted rule IDs. AppTrail does not share raw Gmail bodies, raw subjects, private links, query strings, tokens, scheduler links, candidate IDs, application IDs, cookies, or credentials as source intelligence.

### Extension data

The extension stores and may sync:

- supported job-page URLs
- extracted job fields
- career-page visit counts
- submission detections
- offline queue items
- the user-scoped API key used to connect the extension to the account

### Operational data

AppTrail also stores limited operational data for security and reliability:

- request timestamps
- rate-limit information
- basic logs and error records
- task metrics and audit data

## How AppTrail Uses That Information

AppTrail uses stored information to:

- authenticate users
- show and organize the application pipeline
- classify hiring-related email
- generate drafts and resume outputs when those features are enabled
- save jobs from the extension
- surface contact, interview, and follow-up context
- run product reports and activity history
- identify verified company career sources and reduce reliance on broad web search when Source Intelligence is enabled
- secure the service and investigate failures

AppTrail does not sell personal information.

## Consent And Optional Processing

Some AppTrail features depend on extra processing or outside services. The product includes explicit consent controls for:

- AI-assisted processing
- third-party enrichment
- public web research
- source intelligence from sanitized application and job-source metadata

If those features are turned off, AppTrail falls back to the product behavior that does not require them.

Gmail-derived source intelligence is treated as Google user data and is used only for visible AppTrail features with user consent. Human admin access to user-specific Gmail-derived evidence is prohibited by default. Admin views show redacted metadata, aggregate counts, rule IDs, source IDs, and provider health unless a user-authorized support, security abuse, or legal compliance exception applies.

## How Information Is Shared

AppTrail shares information only when needed to operate the product or comply with law. That may include infrastructure and service providers used for:

- hosting
- database and queue infrastructure
- Google sign-in and Gmail connectivity
- LLM-backed product tasks
- contact enrichment
- error reporting and monitoring

AppTrail does not use customer data for ad targeting.

## Data Retention

AppTrail keeps data for as long as it is needed to run the product and maintain the account, unless the user deletes that data or requests account deletion.

Some operational records may be retained longer when required for security, abuse prevention, or legal compliance.

## User Controls

Users can:

- disconnect Gmail
- rotate or revoke extension API keys
- delete saved jobs, contacts, notes, and other account records
- clear extension-local storage by resetting or uninstalling the extension
- request account deletion

## Security

AppTrail uses layered security controls that include:

- authenticated access
- user-scoped data access
- encrypted Gmail token storage
- transport security in production
- rate limiting
- structured logging with redaction

No system can promise perfect security, but AppTrail is designed to limit unnecessary exposure and keep sensitive flows scoped.

## Children

AppTrail is not intended for children under 13.

## Policy Changes

This policy may be updated as the product changes. The current version will always be posted with the latest update date.

## Contact

For privacy questions or data requests, contact `privacy@apptrail.com`.
